"""人工短歌词验证标准化、平台映射和独立缓存，不访问公网。"""
import asyncio
import base64
from types import SimpleNamespace
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.lyrics import document,parse_lrc,LyricsCache,provider_lyrics
from app.models import TrackIdentity
from app.core.errors import CoreError

TRACK=TrackIdentity(providerId='netease',platformId='1')


def test_parser():
    lines,plain=parse_lrc('\ufeff[ar:测试]\r\n[offset:500]\n[01:03.25]乙\n[00:12.0][00:16.520]甲\n[00:12.00]甲\n[00:20.001]\n[00:99]无效')
    assert [l.startMs for l in lines]==[12500,17020,20501,63750]
    assert lines[0].endMs==17020 and lines[-1].endMs is None and lines[2].text==''
    assert plain=='无效'
    assert document(TRACK,'文本').status=='plain'
    assert document(TRACK).status=='unavailable'
    assert document(TRACK,instrumental=True).status=='instrumental'
    assert document(TRACK,'[00:01]甲','[00:01.010]译').lines[0].translation=='译'
    assert document(TRACK,'[00:01]甲','[00:02]译').unalignedTranslation
    with pytest.raises(CoreError):parse_lrc('x'*1048577)


@pytest.mark.parametrize('provider',['kuwo','qq','netease','migu'])
def test_provider_mapping(provider,monkeypatch):
    async def scenario():
        async def dns(*a,**k):return [(2,1,6,'',('1.1.1.1',443))]
        monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',dns)
        identity=TrackIdentity(providerId=provider,platformId='1')
        def handle(request):
            assert 'cookie' not in request.headers and 'authorization' not in request.headers
            if provider=='kuwo':return httpx.Response(200,json={'data':{'lrclist':[{'time':'1.5','lineLyric':'人工'}]}})
            if provider=='qq':return httpx.Response(200,json={'code':0,'lyric':base64.b64encode('[00:01.500]人工'.encode()).decode()})
            if provider=='netease':return httpx.Response(200,json={'code':200,'lrc':{'lyric':'[00:01.500]人工'},'tlyric':{'lyric':'[00:01.500]翻译'}})
            if request.url.host=='d.musicapp.migu.cn':return httpx.Response(200,text='[00:01.500]人工')
            return httpx.Response(200,json={'data':{'lrcUrl':'https://d.musicapp.migu.cn/test.lrc'}})
        async def detail(*args):return {'resource':[{'contentId':'1','copyrightId':'test'}]}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle),cookies={'secret':'private'},auth=('a','b')) as client:
            value=await provider_lyrics(SimpleNamespace(id=provider,client=client,request_json=detail),identity)
            assert value.lines[0].startMs==1500 and value.status=='synced'
    asyncio.run(scenario())


@pytest.mark.parametrize('status',[403,404,429,503])
def test_http_errors(status):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(status))) as client:
            with pytest.raises(CoreError):await provider_lyrics(SimpleNamespace(id='netease',client=client),TRACK)
    asyncio.run(scenario())


def test_cache_api_and_lifecycle():
    async def scenario():
        now=[0];calls=[]
        async def get(identity):calls.append(identity);await asyncio.sleep(.01);return document(identity,'[00:01]人工')
        provider=SimpleNamespace(get_lyrics=get);cache=LyricsCache(ttl=1,capacity=1,clock=lambda:now[0])
        await asyncio.gather(*(cache.get(TRACK,provider) for _ in range(5)))
        assert len(calls)==1 and not cache.locks
        now[0]=2;await cache.get(TRACK,provider);assert len(calls)==2
        await cache.get(TrackIdentity(providerId='netease',platformId='2'),provider)
        assert len(cache.entries)==1
    asyncio.run(scenario())
    with TestClient(create_app()) as client:
        async def get(identity):return document(identity,'[00:01]人工')
        client.app.state.netease.get_lyrics=get
        assert client.get('/api/lyrics?providerId=netease&platformId=1').json()['status']=='synced'
        assert not client.app.state.media_store.records and not client.app.state.playback_leases.entries
        assert client.get('/api/lyrics?providerId=bad&platformId=1').status_code==422


@pytest.mark.parametrize('raw,expected',[('[00:01.1]甲',1100),('[00:01.12]甲',1120),('[00:01.123]甲',1123),('[offset:-2000]\n[00:01]甲',0)])
def test_precision(raw,expected):assert parse_lrc(raw)[0][0].startMs==expected


@pytest.mark.parametrize('case',['timeout','structure','oversize','cancel'])
def test_request_failures(case):
    async def scenario():
        async def handle(request):
            if case=='timeout':raise httpx.ReadTimeout('敏感上下文')
            if case=='cancel':raise asyncio.CancelledError()
            return httpx.Response(200,content=b'x'*1048577 if case=='oversize' else b'{}')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(asyncio.CancelledError if case=='cancel' else CoreError):
                await provider_lyrics(SimpleNamespace(id='netease',client=client),TRACK)
    asyncio.run(scenario())
