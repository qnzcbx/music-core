"""jfjt协议与Native无媒体、GD503后的正常API回退；网络均为脱敏Fixture。"""
import asyncio
from urllib.parse import parse_qs
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.providers.netease_resolvers import jfjt
from app.core import media_probe
from app.core.errors import CoreError,ErrorCode

SONG='167691';URL='https://m801.music.126.net/synthetic'
DATA={'id':SONG,'name':'测试歌','ar_name':'甲','url':URL}

def run(call,handler):
    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),cookies={'private':'secret'},auth=('private','secret')) as c:return await call(c)
    return asyncio.run(execute())

def test_protocol_identity_and_credentials():
    def upstream(r):
        assert r.url.host=='dm.jfjt.cc' and r.method=='POST'
        assert parse_qs(r.content.decode())=={'url':[SONG],'level':['standard'],'type':['json']}
        assert 'cookie' not in r.headers and 'authorization' not in r.headers
        return httpx.Response(200,json={'success':True,'data':DATA})
    result=run(lambda c:jfjt.resolve(c,SONG),upstream)
    assert result['evidence']=='response_id_matched' and result['title']=='测试歌' and 'synthetic' not in str(result)

@pytest.mark.parametrize('data,code',[
    ({**DATA,'id':'other'},ErrorCode.UPSTREAM_INVALID_RESPONSE),
    ({**DATA,'url':''},ErrorCode.MEDIA_UNAVAILABLE),
    ({**DATA,'url':'file:///private'},ErrorCode.UPSTREAM_INVALID_RESPONSE)])
def test_rejections(data,code):
    with pytest.raises(CoreError) as e:run(lambda c:jfjt.resolve(c,SONG),lambda r:httpx.Response(200,json={'success':True,'data':data}))
    assert e.value.code==code

def test_url_only_is_not_protocol_error():
    result=run(lambda c:jfjt.resolve(c,SONG),lambda r:httpx.Response(200,json={'success':True,'data':{'url':URL}}))
    assert result['evidence']=='request_bound'

@pytest.mark.parametrize('status,body,code',[(503,{},ErrorCode.UPSTREAM_FAILURE),(403,{},ErrorCode.ACCESS_DENIED),
    (200,{'success':False},ErrorCode.UPSTREAM_FAILURE),(200,[],ErrorCode.UPSTREAM_INVALID_RESPONSE)])
def test_errors(status,body,code):
    with pytest.raises(CoreError) as e:run(lambda c:jfjt.resolve(c,SONG),lambda r:httpx.Response(status,json=body))
    assert e.value.code==code

@pytest.mark.parametrize('wrong_metadata',[False,True])
def test_real_api_chain_native_empty_gd_503_jfjt(monkeypatch,wrong_metadata):
    monkeypatch.setenv('MUSIC_CORE_NETEASE_RESOLVER_ORDER','native,gdstudio-preview,jfjt')
    calls=[]
    async def trusted(*args):pass
    monkeypatch.setattr(media_probe,'validate_target',trusted)
    def upstream(r):
        calls.append(r.url.host)
        if r.url.path.endswith('/player/url'):return httpx.Response(200,json={'code':200,'data':[{'id':167691,'code':-110,'url':None}]})
        if r.url.host=='music-api.gdstudio.xyz':return httpx.Response(503)
        if r.url.host=='dm.jfjt.cc':return httpx.Response(200,json={'success':True,'data':DATA})
        if r.url.path.endswith('/song/detail'):return httpx.Response(200,json={'code':200,'songs':[{'id':167691,'name':'其他版本' if wrong_metadata else '测试歌','ar':[{'name':'甲'}]}]})
        return httpx.Response(206,headers={'content-type':'audio/mpeg','content-range':'bytes 0-7/8'},stream=httpx.ByteStream(b'ID3audio'))
    app=create_app(transport=httpx.MockTransport(upstream),target_check=trusted)
    with TestClient(app) as c:
        response=c.post('/api/playback/open',json={'identity':{'providerId':'netease','platformId':SONG}})
        assert response.status_code==(502 if wrong_metadata else 200)
        assert calls[:4]==['music.163.com','music-api.gdstudio.xyz','dm.jfjt.cc','music.163.com']
        if not wrong_metadata:
            assert app.state.netease.last_resolution['resolver']=='jfjt'
            assert response.json()['media']['representation']['sizeBytes']==8
            c.post(response.json()['streamUrl'].replace('/stream','/close'))
        else:assert 'm801.music.126.net' not in calls

def test_cancel_and_timeout():
    def timeout(r):raise httpx.ReadTimeout('private')
    with pytest.raises(CoreError) as e:run(lambda c:jfjt.resolve(c,SONG),timeout)
    assert e.value.code==ErrorCode.UPSTREAM_TIMEOUT
    async def execute():
        entered=asyncio.Event();closed=[]
        class Waiting(httpx.AsyncByteStream):
            async def __aiter__(self):yield b'{';entered.set();await asyncio.Event().wait()
            async def aclose(self):closed.append(True)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,stream=Waiting()))) as c:
            task=asyncio.create_task(jfjt.resolve(c,SONG));await entered.wait();task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            assert closed==[True]
    asyncio.run(execute())
