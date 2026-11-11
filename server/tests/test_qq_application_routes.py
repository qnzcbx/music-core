"""通过正常播放API验收开发试听，禁止把请求绑定伪装成正式确认。"""
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.core import media_probe as media
from test_qq import response

BODY=b'fLaCdata'

@pytest.mark.parametrize('dev_page',[False,True])
@pytest.mark.parametrize('route',['vkeys','tang','xunhuisi'])
def test_development_normal_api_route_and_representation(monkeypatch,route,dev_page):
    calls=[]
    monkeypatch.setenv('MUSIC_CORE_QQ_RESOLVER_ORDER',f'{route},official')
    async def trusted(*args):pass
    monkeypatch.setattr(media,'validate_target',trusted)
    def upstream(r):
        calls.append(r.url.host)
        if r.url.host=='api.vkeys.cn':return httpx.Response(200,json={'code':0,'data':{'url':'https://aqqmusic.tc.qq.com/sample'}})
        if r.url.host=='api.xunhuisi.store':return httpx.Response(200,json={'code':200,'title':'test','singer':'artist','music_url':'https://aqqmusic.tc.qq.com/sample'})
        if r.url.host=='tang.api.s01s.cn':return httpx.Response(200,json={'song_mid':'ABC','song_name':'测试','singer_name':'甲','song_play_url_pq':'https://aqqmusic.tc.qq.com/sample'})
        assert r.url.host=='aqqmusic.tc.qq.com' and 'cookie' not in r.headers
        return httpx.Response(206,headers={'content-type':'audio/flac','content-range':'bytes 0-7/8'},stream=httpx.ByteStream(BODY))
    app=create_app(transport=httpx.MockTransport(upstream),target_check=trusted,dev_player=dev_page)
    with TestClient(app) as client:
        opened=client.post('/api/playback/open',json={'identity':{'providerId':'qq','platformId':'ABC'}})
        assert opened.status_code==200
        value=opened.json();rep=value['media']['representation']
        assert rep['container']=='flac' and rep['codec']=='flac' and rep['sizeBytes']==8
        assert 'aqqmusic' not in opened.text
        assert 'u.y.qq.com' not in calls and len(calls)==2
        assert app.state.qq.last_resolution['identity']==('request_bound' if route in ('vkeys','xunhuisi') else 'confirmed')
        assert app.state.qq.last_resolution['scope']=='configured_preview'
        assert client.get(value['streamUrl']).content==BODY
        assert client.post(value['streamUrl'].replace('/stream','/close')).status_code==204

def test_explicit_official_only_does_not_unlock_external(monkeypatch):
    monkeypatch.setenv('MUSIC_CORE_QQ_RESOLVER_ORDER','official')
    calls=[]
    def upstream(r):
        calls.append(r.url.host)
        return response({'midurlinfo':[{'songmid':'ABC','purl':''}]})
    with TestClient(create_app(transport=httpx.MockTransport(upstream))) as client:
        result=client.post('/api/playback/open',json={'identity':{'providerId':'qq','platformId':'ABC'}})
        assert result.status_code==409 and calls==['u.y.qq.com']

def test_development_explicit_denial_does_not_fallback(monkeypatch):
    monkeypatch.setenv('MUSIC_CORE_QQ_RESOLVER_ORDER','vkeys,tang,official')
    calls=[]
    def upstream(r):calls.append(r.url.host);return httpx.Response(403)
    with TestClient(create_app(transport=httpx.MockTransport(upstream),dev_player=True)) as client:
        result=client.post('/api/playback/open',json={'identity':{'providerId':'qq','platformId':'ABC'}})
        assert result.status_code==403 and calls==['api.vkeys.cn']


def test_application_default_fallback_orders(monkeypatch):
    monkeypatch.delenv('MUSIC_CORE_QQ_RESOLVER_ORDER',raising=False)
    monkeypatch.delenv('MUSIC_CORE_NETEASE_RESOLVER_ORDER',raising=False)
    app=create_app()
    with TestClient(app):
        assert app.state.qq.route_order==('official','vkeys','tang','xunhuisi')
        assert app.state.netease.route_order==('native','gdstudio-preview','jfjt')
