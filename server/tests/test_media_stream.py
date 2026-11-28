"""可控上游字节流验证HTTP契约与取消释放；数据不是酷我录音。"""
import asyncio
import logging
import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from app.main import create_app,SafeAccessLog
from app.core.errors import CoreError,ErrorCode
from app.media_stream import proxy,validate_target,range_header
from test_media_lifecycle import media

DATA=bytes(range(256))*4


@pytest.mark.parametrize(('host', 'provider', 'bypass'), [
    ('isure.stream.qqmusic.qq.com', 'qq', False),
    ('m801.music.126.net', 'netease', False),
    ('isure.stream.qqmusic.qq.com', 'qq', True),
    ('isure.stream.qqmusic.qq.com.example.invalid', 'qq', False),
])
def test_media_probe_uses_actual_proxy_route(monkeypatch, host, provider, bypass):
    from app.core.media_probe import verify_media
    from app.media_stream import MediaClient

    async def exercise():
        requests = []

        async def forward(reader, writer):
            try:
                block = await reader.readuntil(b'\r\n\r\n')
                requests.append(block.splitlines()[0])
                writer.write(b'HTTP/1.1 206 Partial Content\r\nContent-Type: audio/mpeg\r\n'
                             b'Content-Range: bytes 0-3/4\r\nContent-Length: 4\r\nConnection: close\r\n\r\nID3x')
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        async with await asyncio.start_server(forward, '127.0.0.1', 0) as server:
            port = server.sockets[0].getsockname()[1]
            monkeypatch.setenv('HTTP_PROXY', f'http://127.0.0.1:{port}')
            monkeypatch.setenv('NO_PROXY', host if bypass else '')

            async def fake_dns(*args, **kwargs):
                return [(None,None,None,None,('198.18.3.4', 80))]

            monkeypatch.setattr(asyncio.get_running_loop(), 'getaddrinfo', fake_dns)
            async with MediaClient() as client:
                url = f'http://{host}/audio'
                if bypass or host.endswith('.invalid'):
                    with pytest.raises(CoreError) as error:
                        await verify_media(client, url, provider)
                    assert error.value.code == ErrorCode.UNTRUSTED_MEDIA
                    assert not requests
                else:
                    result = await verify_media(client, url, provider)
                    assert result.codec == 'mp3'
                    assert requests == [f'GET {url} HTTP/1.1'.encode()]

    asyncio.run(exercise())


async def allow_test_target(url):
    """仅测试依赖注入，生产始终进行目标白名单及DNS检查。"""


def upstream(request):
    value=request.headers.get('range')
    headers={'content-type':'audio/mpeg','accept-ranges':'bytes','etag':'"fixture"'}
    status=200;body=DATA
    if value:
        first,last=value[6:].split('-')
        start=int(first) if first else max(0,len(DATA)-int(last))
        end=min(int(last),len(DATA)-1) if first and last else len(DATA)-1
        if start>=len(DATA):
            return httpx.Response(416,headers={'content-range':f'bytes */{len(DATA)}','content-length':'0'},stream=httpx.ByteStream(b''))
        status=206;body=DATA[start:end+1];headers['content-range']=f'bytes {start}-{end}/{len(DATA)}'
    headers['content-length']=str(len(body))
    return httpx.Response(status,headers=headers,stream=httpx.ByteStream(body))


@pytest.fixture
def client():
    app=create_app(transport=httpx.MockTransport(upstream),target_check=allow_test_target)
    with TestClient(app) as c:
        item=app.state.media_store.put(media());key=app.state.playback_leases.create(item.id)
        yield c,app,item,key


@pytest.mark.parametrize('value,status,expected',[(None,200,DATA),('bytes=0-',206,DATA),
    ('bytes=100-199',206,DATA[100:200]),('bytes=-100',206,DATA[-100:]),('bytes=2000-',416,b'')])
def test_range_bytes_headers_and_refs(client,value,status,expected):
    c,app,item,key=client
    response=c.get(f'/api/playback/{key}/stream',headers={'Range':value} if value else {})
    assert response.status_code==status and response.content==expected
    assert int(response.headers['content-length'])==len(expected)
    assert not app.state.media_store.records[item.id].streams
    assert app.state.playback_leases.entries[key].state=='active'


def test_head_close_and_unknown(client):
    c,app,item,key=client
    response=c.head(f'/api/playback/{key}/stream',headers={'Range':'bytes=100-199'})
    assert response.status_code==206 and not response.content and response.headers['content-length']=='100'
    for _ in range(2):assert c.post(f'/api/playback/{key}/close').status_code==204
    assert c.get(f'/api/playback/{key}/stream').json()['error']['code']=='playback_closed'
    assert c.get('/api/playback/absent/stream').status_code==404
    assert c.post('/api/playback/absent/close').status_code==204


@pytest.mark.parametrize('value',['bytes=2-1','bytes=-0','bytes=-','bytes=0-1,2-3','items=0-1','bytes=x-1'])
def test_invalid_range(value):
    with pytest.raises(CoreError) as error:range_header(value)
    assert error.value.code==ErrorCode.INVALID_RANGE


def test_open_private_and_provider_selection():
    calls=[]
    class Provider:
        async def resolve(self,identity):
            calls.append(identity)
            return media()
    app=create_app(transport=httpx.MockTransport(upstream),target_check=allow_test_target)
    with TestClient(app) as c:
        app.state.kuwo=Provider()
        response=c.post('/api/playback/open',json={'identity':{'providerId':'kuwo','platformId':'1'}})
        assert response.status_code==200
        body=response.json()
        assert body['streamUrl'].startswith('/api/playback/') and 'kuwo.cn' not in response.text
        assert body['media']['id']!=body['playbackId']
        assert c.post('/api/playback/open',json={'identity':{'providerId':'bad','platformId':'1'}}).status_code==422
        assert c.post('/api/playback/open',json={'identity':{'providerId':'kuwo','platformId':'1'},'url':'http://127.0.0.1'}).status_code==422
        assert len(calls)==1


@pytest.mark.parametrize('status,headers,code',[(403,{},'access_denied'),(410,{},'upstream_media_expired'),
    (500,{},'upstream_failure'),(200,{'content-type':'text/html'},'upstream_invalid_response'),
    (200,{'content-encoding':'gzip'},'upstream_invalid_response'),
    (206,{'content-range':'bytes 0-9/10','content-length':'5'},'upstream_invalid_response')])
def test_upstream_errors_release(status,headers,code):
    app=create_app(transport=httpx.MockTransport(lambda r:httpx.Response(status,headers=headers,stream=httpx.ByteStream(b''))),target_check=allow_test_target)
    with TestClient(app) as c:
        item=app.state.media_store.put(media());key=app.state.playback_leases.create(item.id)
        result=c.get(f'/api/playback/{key}/stream')
        assert result.json()['error']['code']==code
        assert not app.state.media_store.records[item.id].streams


def test_ignores_range_and_header_allowlist():
    def handler(r):
        assert r.headers['range']=='bytes=100-199' and r.headers['if-range']=='"fixture"'
        assert 'cookie' not in r.headers and 'authorization' not in r.headers
        return httpx.Response(200,headers={'content-length':str(len(DATA)),'content-type':'audio/mpeg',
            'set-cookie':'private','x-private':'no','content-range':'invalid'},stream=httpx.ByteStream(DATA))
    app=create_app(transport=httpx.MockTransport(handler),target_check=allow_test_target)
    with TestClient(app) as c:
        item=app.state.media_store.put(media());key=app.state.playback_leases.create(item.id)
        result=c.get(f'/api/playback/{key}/stream',headers={'Range':'bytes=100-199','If-Range':'"fixture"',
            'Cookie':'private','Authorization':'private'})
        assert result.status_code==200 and result.content==DATA
        assert 'set-cookie' not in result.headers and 'content-range' not in result.headers


@pytest.mark.parametrize('url',['http://127.0.0.1/a','file:///private','https://evil.example/a',
    'http://private.kuwo.cn:8080/a','https://user:password@media.kuwo.cn/a'])
def test_target_rejects_untrusted(url):
    with pytest.raises(CoreError):asyncio.run(validate_target(url))


def test_dns_private_address(monkeypatch):
    async def run():
        async def fake(*args,**kwargs):return [(None,None,None,None,('127.0.0.1',80))]
        monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',fake)
        await validate_target('http://media.kuwo.cn/audio')
    with pytest.raises(CoreError):asyncio.run(run())


@pytest.mark.parametrize('failure',['cancel','send','read','truncated'])
def test_response_failure_always_closes(failure):
    closed=[];released=[]
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'ID3'
            if failure=='read':raise httpx.ReadError('私有地址')
        async def aclose(self):closed.append(True)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,
                headers={'content-type':'audio/mpeg','content-length':'9' if failure=='truncated' else '3'},stream=Stream()))) as client:
            request=Request({'type':'http','method':'GET','headers':[], 'path':'/test'})
            response=await proxy(request,media(),client,lambda:released.append(True),allow_test_target)
            async def send(event):
                if failure=='cancel':raise asyncio.CancelledError()
                if failure=='send':raise OSError('浏览器断开')
            async def receive():return {'type':'http.disconnect'}
            scope={'type':'http','method':'GET','asgi':{'spec_version':'2.4'}}
            with pytest.raises(BaseException):await response(scope,receive,send)
    asyncio.run(run())
    assert closed and len(released)==1


def test_access_logs_hide_capability():
    record=logging.LogRecord('uvicorn.access',20,'',1,'message',('client','GET','/api/playback/secret/stream','1.1',206),None)
    SafeAccessLog().filter(record)
    assert 'secret' not in str(record.args)


def test_redirect_target_checked_before_second_request():
    calls=[]
    def handler(r):
        calls.append(r)
        return httpx.Response(302,headers={'Location':'http://127.0.0.1/private'})
    async def check(url):
        if '127.0.0.1' in url:raise CoreError(ErrorCode.UNTRUSTED_MEDIA)
    app=create_app(transport=httpx.MockTransport(handler),target_check=check)
    with TestClient(app) as c:
        item=app.state.media_store.put(media());key=app.state.playback_leases.create(item.id)
        result=c.get(f'/api/playback/{key}/stream')
        assert result.json()['error']['code']=='untrusted_media'
        assert len(calls)==1 and not app.state.media_store.records[item.id].streams


def test_known_upstream_expiry_no_network():
    calls=[]
    app=create_app(transport=httpx.MockTransport(lambda r:calls.append(r)),target_check=allow_test_target)
    with TestClient(app) as c:
        expired=media().model_copy(update={'validUntil':2})
        item=app.state.media_store.put(expired);key=app.state.playback_leases.create(item.id)
        result=c.get(f'/api/playback/{key}/stream')
        assert result.json()['error']['code']=='upstream_media_expired' and not calls


def test_dev_page_opt_in():
    with TestClient(create_app()) as c:assert c.get('/dev/player').status_code==404
    with TestClient(create_app(dev_player=True)) as c:assert c.get('/dev/player').status_code==200
