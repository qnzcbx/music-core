"""人工短响应检验巡回寺协议，不访问公网。"""
import asyncio
import httpx
import pytest
from app.providers.qq_resolvers.xunhuisi import resolve
from app.core.errors import CoreError

@pytest.mark.parametrize('changes,error',[
    ({},False),({'mid':'wrong'},True),({'music_url':''},True),({'link':'https://y.qq.com/n/ryqq/songDetail/wrong'},True),
    ({'title':None},True),({'title':'人工 Live'},True),({'music_url':'file:///bad'},True)])
def test_responses(changes,error):
    async def scenario():
        def handle(r):
            assert r.url.params['mid']=='ABC' and r.url.params['type']=='json'
            assert 'cookie' not in r.headers and 'authorization' not in r.headers
            return httpx.Response(200,json={'code':200,'title':'人工歌曲','singer':'人工歌手','music_url':'https://aqqmusic.tc.qq.com/sample',**changes})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle),cookies={'secret':'private'}) as c:
            if error:
                with pytest.raises(CoreError):await resolve(c,'ABC')
            else:
                value=await resolve(c,'ABC');assert value.response_mid is None and value.evidence=='request_bound'
    asyncio.run(scenario())

@pytest.mark.parametrize('failure',['http','timeout','cancel','json'])
def test_failures(failure):
    async def scenario():
        def handle(r):
            if failure=='timeout':raise httpx.ReadTimeout('敏感信息')
            if failure=='cancel':raise asyncio.CancelledError()
            return httpx.Response(403 if failure=='http' else 200,content=b'not-json')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as c:
            with pytest.raises(asyncio.CancelledError if failure=='cancel' else CoreError):await resolve(c,'ABC')
    asyncio.run(scenario())


def test_configured_fallback_without_page(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from test_qq import response
    monkeypatch.setenv('MUSIC_CORE_QQ_RESOLVER_ORDER','xunhuisi,official')
    calls=[]
    def handle(r):
        calls.append(r.url.host)
        if r.url.host=='api.xunhuisi.store':return httpx.Response(503)
        return response({'midurlinfo':[{'songmid':'ABC','purl':''}]})
    with TestClient(create_app(transport=httpx.MockTransport(handle))) as c:
        assert c.get('/dev/player').status_code==404
        assert c.post('/api/playback/open',json={'identity':{'providerId':'qq','platformId':'ABC'}}).status_code==409
        assert calls==['api.xunhuisi.store','u.y.qq.com']
