"""网易云GD协议、预算、正常API与请求绑定语义的脱敏测试。"""
import asyncio
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.providers.netease import NeteaseProvider
from app.providers.netease_resolvers import gdstudio
from app.core import media_probe
from app.models import TrackIdentity
from app.core.errors import CoreError,ErrorCode

TRACK=TrackIdentity(providerId='netease',platformId='167691')
URL='https://m801.music.126.net/synthetic'

def run(call,handler):
    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),cookies={'private':'secret'},headers={'Authorization':'private'},auth=('private','private')) as client:
            return await call(client)
    return asyncio.run(execute())

def test_request_and_url_only():
    def handler(r):
        assert r.url.host=='music-api.gdstudio.xyz'
        assert dict(r.url.params)=={'types':'url','id':'167691','source':'netease','br':'999'}
        assert 'authorization' not in r.headers and 'cookie' not in r.headers
        return httpx.Response(200,json={'url':URL,'br':1546,'size':5000})
    candidate=run(lambda c:gdstudio.resolve(c,'167691'),handler)
    assert candidate['evidence']=='request_bound' and 'synthetic' not in str(candidate)

@pytest.mark.parametrize('body',[[],{}, {'url':''},{'url':'file:///secret'},{'url':URL,'id':777}, {'url':URL,'id':True}])
def test_invalid_payload(body):
    with pytest.raises(CoreError):run(lambda c:gdstudio.resolve(c,'167691'),lambda r:httpx.Response(200,json=body))

@pytest.mark.parametrize('status,body,expected',[(403,{},ErrorCode.ACCESS_DENIED),(500,{},ErrorCode.UPSTREAM_FAILURE),
    (200,{'code':'403'},ErrorCode.ACCESS_DENIED),(200,{'code':500},ErrorCode.UPSTREAM_FAILURE)])
def test_errors(status,body,expected):
    with pytest.raises(CoreError) as error:run(lambda c:gdstudio.resolve(c,'167691'),lambda r:httpx.Response(status,json=body))
    assert error.value.code==expected

@pytest.mark.parametrize('order',[(),('native','native'),('unknown',),'native'])
def test_configuration(order):
    with pytest.raises(ValueError):NeteaseProvider(None,route_order=order)

def test_normal_api_without_dev_page_and_stop(monkeypatch):
    calls=[]
    monkeypatch.setenv('MUSIC_CORE_NETEASE_RESOLVER_ORDER','gdstudio-preview,native')
    async def trusted(*args):pass
    monkeypatch.setattr(media_probe,'validate_target',trusted)
    def upstream(r):
        calls.append(r.url.host)
        if r.url.host=='music-api.gdstudio.xyz':return httpx.Response(200,json={'url':URL})
        assert r.url.host=='m801.music.126.net'
        return httpx.Response(206,headers={'content-type':'audio/flac','content-range':'bytes 0-7/8'},stream=httpx.ByteStream(b'fLaCdata'))
    app=create_app(transport=httpx.MockTransport(upstream),target_check=trusted)
    with TestClient(app) as c:
        assert c.get('/dev/player').status_code==404
        response=c.post('/api/playback/open',json={'identity':TRACK.model_dump()})
        assert response.status_code==200 and calls==['music-api.gdstudio.xyz','m801.music.126.net']
        assert app.state.netease.last_resolution['identity']=='request_bound'
        assert response.json()['media']['representation']['sizeBytes']==8 and 'synthetic' not in response.text
        assert c.post(response.json()['streamUrl'].replace('/stream','/close')).status_code==204

def test_native_failure_fallback_and_permission_stop(monkeypatch):
    async def execute(deny):
        calls=[]
        async def trusted(*args):pass
        monkeypatch.setattr(media_probe,'validate_target',trusted)
        def upstream(r):
            calls.append(r.url.host)
            if r.url.host=='music.163.com':return httpx.Response(200,json={'code':200,'data':[{'id':167691,'code':403 if deny else -110,'url':None}]})
            if r.url.host=='music-api.gdstudio.xyz':return httpx.Response(200,json={'url':URL,'id':167691})
            return httpx.Response(206,headers={'content-type':'audio/flac','content-range':'bytes 0-7/8'},stream=httpx.ByteStream(b'fLaCdata'))
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            p=NeteaseProvider(client,route_order=('native','gdstudio-preview'))
            if deny:
                with pytest.raises(CoreError) as error:await p.resolve(TRACK)
                assert error.value.code==ErrorCode.ACCESS_DENIED and calls==['music.163.com']
            else:
                assert (await p.resolve(TRACK)).identity==TRACK
                assert calls==['music.163.com','music-api.gdstudio.xyz','m801.music.126.net']
    asyncio.run(execute(False));asyncio.run(execute(True))

def test_timeout_and_cancel():
    def timeout(r):raise httpx.ReadTimeout('private')
    with pytest.raises(CoreError) as error:run(lambda c:gdstudio.resolve(c,'167691'),timeout)
    assert error.value.code==ErrorCode.UPSTREAM_TIMEOUT
    async def execute():
        entered=asyncio.Event();closed=[]
        class Waiting(httpx.AsyncByteStream):
            async def __aiter__(self):yield b'{';entered.set();await asyncio.Event().wait()
            async def aclose(self):closed.append(True)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,stream=Waiting()))) as client:
            p=NeteaseProvider(client,route_order=('gdstudio-preview','native'))
            task=asyncio.create_task(p.resolve(TRACK));await entered.wait();task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            assert closed==[True]
    asyncio.run(execute())

def test_total_budget_cancels_current_route(monkeypatch):
    import app.providers.netease as module
    original=asyncio.wait_for;closed=[];calls=[]
    async def wait_native(*args):
        calls.append('native')
        try:await asyncio.Event().wait()
        finally:closed.append(True)
    async def short_budget(awaitable,timeout):
        assert timeout==25
        return await original(awaitable,.01)
    p=NeteaseProvider(None,route_order=('native','gdstudio-preview'))
    monkeypatch.setattr(p,'_resolve_native',wait_native)
    monkeypatch.setattr(module.asyncio,'wait_for',short_budget)
    with pytest.raises(CoreError) as error:asyncio.run(p.resolve(TRACK))
    assert error.value.code==ErrorCode.UPSTREAM_TIMEOUT and closed==[True] and calls==['native']


@pytest.mark.parametrize('failure,continues', [
    ('timeout', True), ('server_error', True), ('no_media', True),
    ('endpoint_challenge', True), ('unknown_403', False), ('permission_json', False),
    ('json_with_challenge_header', False), ('html_without_challenge_header', False),
])
@pytest.mark.parametrize('quality', [None, 'high', 'lossless'])
def test_gd_fault_scope_and_jfjt_fallback(monkeypatch, failure, continues, quality):
    from app.models import ResolveOptions
    from urllib.parse import parse_qs
    calls = []

    async def trusted(*args):
        pass
    monkeypatch.setattr(media_probe, 'validate_target', trusted)
    block = bytearray(34)
    block[10:18] = ((44100 << 44) | (1 << 41) | (15 << 36) | 44100).to_bytes(8, 'big')
    raw = b'fLaC' + b'\x80' + (34).to_bytes(3, 'big') + block

    def upstream(request):
        host = request.url.host
        calls.append(host)
        if host == 'music.163.com':
            if request.url.path.endswith('/detail'):
                return httpx.Response(200, json={'code':200,'songs':[{'id':167691,'name':'宿敌','ar':[{'name':'许嵩'}]}]})
            return httpx.Response(200, json={'code':200,'data':[{'id':167691,'code':-110,'url':None}]})
        if host == 'music-api.gdstudio.xyz':
            if failure == 'timeout':
                raise httpx.ReadTimeout('fixture endpoint timeout')
            if failure == 'server_error':
                return httpx.Response(503)
            if failure == 'no_media':
                return httpx.Response(200, json={'id':167691,'url':''})
            if failure == 'endpoint_challenge':
                return httpx.Response(403, headers={'cf-mitigated':'challenge','content-type':'text/html; charset=UTF-8'}, text='<title>Just a moment...</title>')
            if failure == 'html_without_challenge_header':
                return httpx.Response(403, headers={'content-type':'text/html'}, text='Access denied')
            if failure == 'json_with_challenge_header':
                return httpx.Response(403, headers={'cf-mitigated':'challenge'}, json={'code':403})
            if failure == 'permission_json':
                return httpx.Response(200, json={'code':403,'id':167691})
            return httpx.Response(403)
        if host == 'dm.jfjt.cc':
            form = parse_qs(request.content.decode())
            assert form['url'] == ['167691']
            assert form['level'] == [{'high':'exhigh','lossless':'lossless'}.get(quality, 'standard')]
            return httpx.Response(200, json={'success':True,'data':{'id':167691,'name':'宿敌','ar_name':'许嵩','url':URL}})
        assert host == 'm801.music.126.net'
        return httpx.Response(206, headers={'content-range':f'bytes 0-{len(raw)-1}/{len(raw)}'}, stream=httpx.ByteStream(raw))

    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            provider = NeteaseProvider(client, route_order=('native','gdstudio-preview','jfjt'))
            options = ResolveOptions(purpose='download', providerQualityId=quality)
            if continues:
                media = await provider.resolve(TRACK, options)
                assert media.identity == TRACK and provider.last_resolution['resolver'] == 'jfjt'
                assert media.representation.codec == 'flac'
                assert 'dm.jfjt.cc' in calls
            else:
                with pytest.raises(CoreError) as error:
                    await provider.resolve(TRACK, options)
                assert error.value.code == ErrorCode.ACCESS_DENIED
                assert calls == ['music.163.com','music-api.gdstudio.xyz']
    asyncio.run(execute())
