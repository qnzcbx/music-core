"""人工合成平台响应通过MockTransport验证，不连接公网。"""
import asyncio
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.providers.kuwo import KuwoProvider, decode_response, candidate_from
from app.models import TrackIdentity, ResolveOptions
from app.core.errors import CoreError, ErrorCode

ROW = {'MUSICRID':'MUSIC_123','SONGNAME':'测试歌','ARTIST':'甲&乙','DURATION':'120','ALBUM':'测试专辑'}


def run(call, handler):
    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await call(KuwoProvider(client))
    return asyncio.run(execute())


def test_metadata_and_cursor():
    def handler(request):
        assert request.url.params['pn']=='0' and request.url.params['rn']=='2'
        return httpx.Response(200,text=repr({'abslist':[ROW,ROW],'TOTAL':'10'}))
    result=run(lambda p:p.search('歌',2),handler)
    assert len(result.items)==1 and result.nextCursor=='1:2'
    assert result.items[0].identity.platformId=='123'
    assert result.items[0].artists==('甲','乙')
    assert result.items[0].durationSeconds==120
    assert 'playable' not in result.model_dump_json()


@pytest.mark.parametrize('raw',[{}, {**ROW,'MUSICRID':'bad'}, {**ROW,'SONGNAME':''}, {**ROW,'MUSICRID':True}])
def test_invalid_rows(raw):
    assert candidate_from(raw) is None


def test_unknown_metadata():
    value=candidate_from({'MUSICRID':'MUSIC_1','SONGNAME':'歌'})
    assert value.durationSeconds is None and value.album is None and value.cover is None
    assert candidate_from({**ROW,'ARTIST':'甲&amp;乙'}).artists==('甲','乙')


@pytest.mark.parametrize('body',[{'abslist':[],'TOTAL':'0'},{'abslist':[ROW]*12,'TOTAL':'1'}])
def test_limit_and_exhaustion(body):
    result=run(lambda p:p.search('歌',1),lambda r:httpx.Response(200,json=body))
    assert len(result.items)<=1 and result.nextCursor is None


@pytest.mark.parametrize('query,limit,cursor',[('',1,None),(' '*3,1,None),('x'*81,1,None),('歌',11,None),
    ('歌',True,None),('歌',1,'1:2'),('歌',1,'10:1'),('歌',1,'bad')])
def test_invalid_input_no_network(query,limit,cursor):
    def unexpected(r):
        pytest.fail('输入错误不应发出请求')
    with pytest.raises(CoreError) as e:
        run(lambda p:p.search(query,limit,cursor),unexpected)
    assert e.value.code==ErrorCode.INVALID_INPUT


def test_next_page():
    def handler(r):
        assert r.url.params['pn']=='1'
        return httpx.Response(200,json={'abslist':[ROW],'TOTAL':'2'})
    assert run(lambda p:p.search('歌',1,'1:1'),handler).nextCursor is None


@pytest.mark.parametrize('body,code',[([],ErrorCode.UPSTREAM_INVALID_RESPONSE),
    ({'abslist':{}},ErrorCode.UPSTREAM_INVALID_RESPONSE),({'abslist':[1]},ErrorCode.UPSTREAM_INVALID_RESPONSE),
    ({'code':500},ErrorCode.UPSTREAM_FAILURE),({'success':False},ErrorCode.UPSTREAM_FAILURE)])
def test_search_structure(body,code):
    with pytest.raises(CoreError) as e:
        run(lambda p:p.search('歌',1),lambda r:httpx.Response(200,json=body))
    assert e.value.code==code


@pytest.mark.parametrize('status,code',[(401,ErrorCode.ACCESS_DENIED),(403,ErrorCode.ACCESS_DENIED),
    (404,ErrorCode.TRACK_NOT_FOUND),(500,ErrorCode.UPSTREAM_FAILURE),(302,ErrorCode.UPSTREAM_FAILURE)])
def test_http_status(status,code):
    with pytest.raises(CoreError) as e:
        run(lambda p:p.search('歌',1),lambda r:httpx.Response(status))
    assert e.value.code==code


def test_timeout(monkeypatch):
    def handler(r):
        raise httpx.ReadTimeout('synthetic-sensitive')
    with pytest.raises(CoreError) as e:
        run(lambda p:p.search('歌',1),handler)
    assert e.value.code==ErrorCode.UPSTREAM_TIMEOUT
    assert 'synthetic-sensitive' not in str(e.value)
    async def expired(coro,timeout):
        coro.close()
        raise asyncio.TimeoutError()
    monkeypatch.setattr(asyncio,'wait_for',expired)
    with pytest.raises(CoreError) as e:
        run(lambda p:p.search('歌',1),handler)
    assert e.value.code==ErrorCode.UPSTREAM_TIMEOUT


def test_cancel():
    async def execute():
        started=asyncio.Event()
        async def handler(r):
            started.set()
            await asyncio.Event().wait()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            task=asyncio.create_task(KuwoProvider(client).search('歌',1))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    asyncio.run(execute())


def test_bounded_parser():
    for data in [b'not data',b'__import__("os")',b'[]']:
        with pytest.raises(CoreError):
            decode_response(data)
    with pytest.raises(CoreError):
        run(lambda p:p.search('歌',1),lambda r:httpx.Response(200,content=b'x'*(2*1024*1024+1)))


def test_resolve_identity_and_private_projection():
    def handler(r):
        assert r.url.params['mid']=='123' and 'all' not in r.url.params
        return httpx.Response(200,json={'code':200,'data':{'url':'https://example.invalid/private.mp3'}})
    media=run(lambda p:p.resolve(TrackIdentity(providerId='kuwo',platformId='123')),handler)
    assert media.identity.platformId=='123'
    assert media.representation.codec is None and media.representation.sizeBytes is None
    assert media.validUntil is None
    assert 'example.invalid' not in media.public_view().model_dump_json()+repr(media)


@pytest.mark.parametrize('body,code',[({'success':False},ErrorCode.ACCESS_DENIED),
    ({'code':200,'data':{}},ErrorCode.MEDIA_UNAVAILABLE),({'code':200,'data':[]},ErrorCode.UPSTREAM_INVALID_RESPONSE),
    ({'code':200,'data':{'url':'file:///secret'}},ErrorCode.UPSTREAM_INVALID_RESPONSE),
    ({'code':200,'data':{'url':'https://example.invalid/a.m3u8'}},ErrorCode.CAPABILITY_UNSUPPORTED),
    ({'changed':True},ErrorCode.UPSTREAM_INVALID_RESPONSE)])
def test_resolve_failures(body,code):
    with pytest.raises(CoreError) as e:
        run(lambda p:p.resolve(TrackIdentity(providerId='kuwo',platformId='123')),lambda r:httpx.Response(200,json=body))
    assert e.value.code==code


def test_wrong_provider_and_options():
    for identity,options in [(TrackIdentity(providerId='qq',platformId='ABC'),None),
        (TrackIdentity(providerId='kuwo',platformId='1'),ResolveOptions(providerQualityId='lossless'))]:
        with pytest.raises(CoreError):
            run(lambda p:p.resolve(identity,options),lambda r:pytest.fail('不应请求'))


def test_search_api_and_selection():
    calls=[]
    def handler(r):
        calls.append(r)
        return httpx.Response(200,json={'abslist':[ROW],'TOTAL':'1'})
    app=create_app(transport=httpx.MockTransport(handler))
    with TestClient(app) as c:
        assert c.post('/api/search',json={'providerId':'kuwo','query':'歌','limit':1}).status_code==200
        for pid,status in [('migu',501),('bad',400)]:
            assert c.post('/api/search',json={'providerId':pid,'query':'歌'}).status_code==status
        assert len(calls)==1
        assert c.post('/api/search',json={'providerId':'kuwo','query':' '}).status_code==422
        assert 'upstreamUrl' not in c.get('/openapi.json').text
        client=app.state.kuwo.client
    assert client.is_closed


def test_api_upstream_sanitization():
    def handler(r):
        raise httpx.ConnectError('synthetic-sensitive')
    with TestClient(create_app(transport=httpx.MockTransport(handler))) as c:
        response=c.post('/api/search',json={'providerId':'kuwo','query':'歌'})
        assert response.status_code==502
        assert 'synthetic-sensitive' not in response.text
