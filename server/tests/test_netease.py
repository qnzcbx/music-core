"""网易云离线协议与统一生命周期验收；人工样本不代表在线可用率。"""
import asyncio
from urllib.parse import parse_qs
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.models import TrackIdentity,ResolveOptions
from app.providers.netease import NeteaseProvider,candidate_from
from app.core.errors import CoreError,ErrorCode
from app.media_stream import validate_target

TRACK=TrackIdentity(providerId='netease',platformId='123')
ROW={'id':123,'name':'测试歌','dt':123456,'ar':[{'name':'甲'},{'name':'乙'}],
     'al':{'id':999,'name':'专辑','picUrl':'https://p1.music.126.net/cover.jpg'}}
MEDIA={'id':123,'code':200,'url':'https://m701.music.126.net/sample.mp3','br':128000,'size':123456,'expi':1200}


def run(call,handler):
    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),cookies={'secret':'private'},headers={'Authorization':'private'}) as client:
            return await call(NeteaseProvider(client))
    return asyncio.run(execute())


def response(row=MEDIA):return httpx.Response(200,json={'code':200,'data':[row]})


def test_search_identity_fields_and_no_resolution():
    calls=[]
    def handler(r):
        calls.append(r);assert r.url.path=='/api/cloudsearch/pc'
        assert parse_qs(r.content.decode())=={'s':['测试'],'type':['1'],'limit':['2'],'offset':['0']}
        assert 'cookie' not in r.headers and 'authorization' not in r.headers
        return httpx.Response(200,json={'code':200,'result':{'songs':[ROW,ROW],'songCount':10}})
    page=run(lambda p:p.search(' 测试 ',2),handler)
    assert len(calls)==1 and len(page.items)==1 and page.nextCursor=='2:2'
    song=page.items[0]
    assert song.identity==TRACK and song.artists==('甲','乙') and song.durationSeconds==123.456
    assert song.album=='专辑' and '999' not in song.model_dump_json()
    assert 'playable' not in song.model_dump()


@pytest.mark.parametrize('identifier',[123,'123'])
def test_numeric_identity(identifier):assert candidate_from({**ROW,'id':identifier}).identity==TRACK


@pytest.mark.parametrize('changes',[{'id':True},{'id':0},{'id':1.2},{'id':'01'},{'id':'x'},{'name':''},{'id':10**21}])
def test_invalid_candidate(changes):assert candidate_from({**ROW,**changes}) is None


def test_empty_optional_and_duration():
    assert not run(lambda p:p.search('空',1),lambda r:httpx.Response(200,json={'code':200,'result':{'songCount':0}})).items
    song=candidate_from({'id':123,'name':'歌','dt':True})
    assert song.durationSeconds is None and song.cover is None and not song.artists
    for dt in (-1,float('inf'),'120'):
        assert candidate_from({**ROW,'dt':dt}).durationSeconds is None


@pytest.mark.parametrize('query,limit,cursor',[('',1,None),(' '*2,1,None),('a'*81,1,None),('a',True,None),('a',11,None),('a',2,'2:1'),('a',2,'11:2'),('a',2,'bad')])
def test_invalid_search(query,limit,cursor):
    with pytest.raises(CoreError) as e:run(lambda p:p.search(query,limit,cursor),lambda r:pytest.fail('无效输入不应发请求'))
    assert e.value.code==ErrorCode.INVALID_INPUT


def test_pagination():
    def handler(r):
        assert parse_qs(r.content.decode())['offset']==['2']
        return httpx.Response(200,json={'code':200,'result':{'songs':[ROW],'songCount':3}})
    assert run(lambda p:p.search('歌',2,'2:2'),handler).nextCursor is None


@pytest.mark.parametrize('data',[{},[],{'code':200},{'code':200,'result':{}},{'code':200,'result':{'songs':{}}},{'code':200,'result':{'songs':[1]}}])
def test_bad_search_response(data):
    with pytest.raises(CoreError):run(lambda p:p.search('歌',1),lambda r:httpx.Response(200,json=data))


@pytest.mark.parametrize('purpose',['playback','download'])
def test_resolve_native_and_private_fields(purpose):
    def handler(r):
        assert r.url.path=='/api/song/enhance/player/url'
        assert parse_qs(r.content.decode())=={'ids':['[123]'],'br':['128000']}
        assert 'cookie' not in r.headers and 'authorization' not in r.headers
        return response()
    media=run(lambda p:p.resolve(TRACK,ResolveOptions(purpose=purpose)),handler)
    assert media.identity==TRACK and media.validUntil-media.resolvedAt==1200000
    assert media.representation.bitrateBps==128000 and media.representation.sizeBytes==123456
    assert media.representation.codec is None
    public=media.public_view().model_dump_json()
    assert 'music.126.net' not in public and 'headers' not in public and 'upstreamUrl' not in public


@pytest.mark.parametrize('changes,expected',[
    ({'id':456},ErrorCode.UPSTREAM_INVALID_RESPONSE),({'url':None},ErrorCode.MEDIA_UNAVAILABLE),
    ({'url':''},ErrorCode.MEDIA_UNAVAILABLE),({'url':'file:///secret'},ErrorCode.UPSTREAM_INVALID_RESPONSE),
    ({'url':'https://user:pass@host/a'},ErrorCode.UPSTREAM_INVALID_RESPONSE),
    ({'url':'https://m701.music.126.net/a.m3u8'},ErrorCode.CAPABILITY_UNSUPPORTED),
    ({'code':403},ErrorCode.ACCESS_DENIED),({'code':404},ErrorCode.TRACK_NOT_FOUND),
    ({'code':500},ErrorCode.UPSTREAM_FAILURE),({'freeTrialInfo':{'start':0,'end':30}},ErrorCode.CAPABILITY_UNSUPPORTED)])
def test_resolve_rejections(changes,expected):
    with pytest.raises(CoreError) as e:run(lambda p:p.resolve(TRACK),lambda r:response({**MEDIA,**changes}))
    assert e.value.code==expected


@pytest.mark.parametrize('data',[{},None,[],[MEDIA,MEDIA],[1]])
def test_malformed_resolve(data):
    with pytest.raises(CoreError):run(lambda p:p.resolve(TRACK),lambda r:httpx.Response(200,json={'code':200,'data':data}))


def test_unknown_metadata_is_not_invented():
    media=run(lambda p:p.resolve(TRACK),lambda r:response({**MEDIA,'expi':-1,'size':True,'br':0}))
    assert media.validUntil is None and media.representation.sizeBytes is None and media.representation.bitrateBps is None


@pytest.mark.parametrize('status,body,expected',[(403,{},ErrorCode.ACCESS_DENIED),(503,{},ErrorCode.UPSTREAM_FAILURE),
    (200,{'code':301},ErrorCode.ACCESS_DENIED),(200,{'code':500},ErrorCode.UPSTREAM_FAILURE)])
def test_platform_errors(status,body,expected):
    with pytest.raises(CoreError) as e:run(lambda p:p.resolve(TRACK),lambda r:httpx.Response(status,json=body))
    assert e.value.code==expected


@pytest.mark.parametrize('options',[ResolveOptions(providerQualityId='unsupported'),ResolveOptions(providerQualityId='lossless')])
def test_unsupported_options(options):
    with pytest.raises(CoreError) as e:run(lambda p:p.resolve(TRACK,options),lambda r:pytest.fail('不应发请求'))
    assert e.value.code==ErrorCode.CAPABILITY_UNSUPPORTED


def test_wrong_provider():
    with pytest.raises(CoreError):run(lambda p:p.resolve(TrackIdentity(providerId='kuwo',platformId='123')),lambda r:pytest.fail('不应发请求'))


def test_timeout_cancel_and_bad_body():
    calls=[]
    def handler(r):calls.append(r);raise httpx.ReadTimeout('不得泄漏')
    with pytest.raises(CoreError) as e:run(lambda p:p.resolve(TRACK),handler)
    assert e.value.code==ErrorCode.UPSTREAM_TIMEOUT and len(calls)==1
    for body in (b'<html>error</html>',b' '* (2*1024*1024+1)):
        with pytest.raises(CoreError):run(lambda p:p.resolve(TRACK),lambda r:httpx.Response(200,content=body))
    async def cancelled():
        entered=asyncio.Event()
        async def wait(r):entered.set();await asyncio.Event().wait()
        async with httpx.AsyncClient(transport=httpx.MockTransport(wait)) as client:
            task=asyncio.create_task(NeteaseProvider(client).resolve(TRACK));await entered.wait();task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
    asyncio.run(cancelled())


def test_unified_api_reopen_and_cleanup():
    calls=[]
    class Bytes(httpx.AsyncByteStream):
        async def __aiter__(self):yield b'ID3x'
    async def trusted(url):pass
    def handler(r):
        calls.append(r)
        if r.url.path=='/api/cloudsearch/pc':return httpx.Response(200,json={'code':200,'result':{'songs':[ROW],'songCount':1}})
        if r.url.path=='/api/song/enhance/player/url':return response()
        assert 'cookie' not in r.headers and 'authorization' not in r.headers
        return httpx.Response(206,stream=Bytes(),headers={'content-type':'audio/mpeg','content-range':'bytes 0-3/4'})
    with TestClient(create_app(transport=httpx.MockTransport(handler),target_check=trusted)) as client:
        page=client.post('/api/search',json={'providerId':'netease','query':'歌','limit':1}).json()
        assert page['items'][0]['identity']==TRACK.model_dump() and len(calls)==1
        first=client.post('/api/playback/open',json={'identity':TRACK.model_dump()}).json()
        second=client.post('/api/playback/open',json={'identity':TRACK.model_dump()}).json()
        assert first['playbackId']!=second['playbackId'] and first['media']['id']!=second['media']['id']
        assert 'music.126.net' not in str(first)
        assert client.get(first['streamUrl'],headers={'Range':'bytes=0-3'}).content==b'ID3x'
        for opened in (first,second):
            assert client.post(opened['streamUrl'].replace('/stream','/close')).status_code==204
            assert client.get(opened['streamUrl']).status_code==410
        store=client.app.state.media_store
        assert all(not record.leases and not record.streams for record in store.records.values())
        now=store.clock();store.clock=lambda:now+301
        client.app.state.playback_leases.sweep()
        assert not client.app.state.media_store.records


@pytest.mark.parametrize('url,provider',[
    ('https://m701.music.126.net/a','qq'),('https://m701.music.126.net/a','kuwo'),
    ('https://aqqmusic.tc.qq.com/a','netease'),('https://music.163.com/a','netease'),
    ('https://evil.music.126.net/a','netease'),('https://m701.music.126.net.evil.test/a','netease'),
    ('http://127.0.0.1/a','netease'),('https://m701.music.126.net:8443/a','netease')])
def test_target_boundaries(url,provider):
    with pytest.raises(CoreError) as e:asyncio.run(validate_target(url,provider))
    assert e.value.code==ErrorCode.UNTRUSTED_MEDIA


@pytest.mark.parametrize('address,allowed',[('8.8.8.8',True),('127.0.0.1',False),('10.0.0.1',False),('::1',False)])
def test_target_dns(monkeypatch,address,allowed):
    async def execute():
        async def dns(*args,**kwargs):return [(None,None,None,None,(address,443))]
        monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',dns)
        if allowed:
            await validate_target('https://m701.music.126.net/a','netease')
            await validate_target('https://m801.music.126.net/a','netease')
        else:
            with pytest.raises(CoreError):await validate_target('https://m701.music.126.net/a','netease')
    asyncio.run(execute())


def test_redirect_target_and_other_provider_lifecycle():
    from test_media_lifecycle import media
    async def guard(url):
        if httpx.URL(url).host!='m701.music.126.net':raise CoreError(ErrorCode.UNTRUSTED_MEDIA)
    def handler(r):
        if r.url.host=='music.163.com':return response()
        return httpx.Response(302,headers={'location':'http://127.0.0.1/private'})
    app=create_app(transport=httpx.MockTransport(handler),target_check=guard)
    with TestClient(app) as client:
        kw=app.state.media_store.put(media());kw_key=app.state.playback_leases.create(kw.id)
        opened=client.post('/api/playback/open',json={'identity':TRACK.model_dump()}).json()
        assert client.get(opened['streamUrl']).status_code==502
        client.post(opened['streamUrl'].replace('/stream','/close'))
        assert app.state.playback_leases.use(kw_key).identity.providerId=='kuwo'
        assert not any(record.streams for record in app.state.media_store.records.values())


@pytest.mark.parametrize('operation',['search','resolve'])
def test_response_closed_on_cancel_and_timeout(operation):
    async def cancellation_only():
        entered=asyncio.Event();closed=[]
        class Waiting(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'{'
                entered.set();await asyncio.Event().wait()
            async def aclose(self):closed.append(True)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,stream=Waiting()))) as client:
            provider=NeteaseProvider(client)
            task=asyncio.create_task(provider.search('歌',1) if operation=='search' else provider.resolve(TRACK))
            await entered.wait();task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            assert closed==[True]
    asyncio.run(cancellation_only())
    def timeout(r):raise httpx.ReadTimeout('不得泄漏')
    with pytest.raises(CoreError) as error:run(lambda p:p.search('歌',1) if operation=='search' else p.resolve(TRACK),timeout)
    assert error.value.code==ErrorCode.UPSTREAM_TIMEOUT
