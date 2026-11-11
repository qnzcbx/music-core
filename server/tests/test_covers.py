"""封面通道边界测试；所有上游均由进程内传输夹具提供。"""
import asyncio
from types import SimpleNamespace
import httpx
import pytest
from fastapi.testclient import TestClient
from app.covers import CoverReader, CoverRejected, CoverNetwork, MAX_BYTES, cover_url
from app.main import create_app

class Body(httpx.AsyncByteStream):
    def __init__(self, data): self.data=data
    async def __aiter__(self): yield self.data


QQ='https://y.gtimg.cn/music/photo_new/T002R500x500M000004RbL3b0BDIe2.jpg'
MIGU='https://d.musicapp.migu.cn/data/oss/resource/00/2s/dd/8e7c277729a24232a767f8b281aaa3e2.webp'


@pytest.mark.parametrize('url',[
    'http://y.gtimg.cn/music/photo_new/T002R500x500M000004RbL3b0BDIe2.jpg',
    'http://127.0.0.1/private', 'https://192.168.1.1/image.jpg','https://example.com/a.jpg',
    QQ+'?token=private',QQ+'#fragment',QQ.replace('y.gtimg.cn','user:password@y.gtimg.cn'),
    QQ.replace('y.gtimg.cn','y.gtimg.cn.evil.test'),QQ.replace('y.gtimg.cn','y.gtimg.cn:444'),
    QQ.replace('/music/photo_new/','/../'),QQ.replace('.jpg','.svg'),
    QQ.replace('500x500','500x800'),MIGU.replace('/data/oss/resource/','/other/'),
])
def test_url_is_not_arbitrary_proxy(url):
    with pytest.raises(CoverRejected):cover_url(url)


def test_real_platform_path_shapes():
    assert cover_url(QQ)==QQ and cover_url(MIGU)==MIGU


def test_shared_endpoint_and_no_cookie_forwarding():
    requests=[]
    def upstream(request):
        requests.append(request)
        assert not any(name in request.headers for name in ('cookie','authorization','referer'))
        return httpx.Response(200,headers={'content-type':'image/webp','set-cookie':'private=secret'},stream=Body(b'RIFF0000WEBPdata'))
    app=create_app(cover_transport=httpx.MockTransport(upstream))
    with TestClient(app) as client:
        for url in (QQ,MIGU):
            response=client.get('/api/covers',params={'url':url},headers={'Cookie':'platform=private','Authorization':'Bearer private'})
            assert response.status_code==200 and response.headers['content-type']=='image/webp'
            assert response.headers['x-content-type-options']=='nosniff'
            assert 'private' not in response.text
    assert len(requests)==2


@pytest.mark.parametrize('location',['https://127.0.0.1/x.jpg','https://10.0.0.1/x.jpg','https://evil.test/x.jpg',QQ+'?credential=secret'])
def test_redirect_rechecked(location):
    def upstream(request):return httpx.Response(302,headers={'location':location})
    with TestClient(create_app(cover_transport=httpx.MockTransport(upstream))) as client:
        response=client.get('/api/covers',params={'url':QQ})
        assert response.status_code==400 and 'credential' not in response.text


@pytest.mark.parametrize('body,headers,expected',[
    (b'<svg/>',{'content-type':'image/svg+xml'},415),
    (b'<html>not image</html>',{'content-type':'image/jpeg'},415),
    (b'\xff\xd8\xfffake',{'content-type':'text/html'},415),
    (b'\xff\xd8\xfffake',{'content-type':'image/jpeg','content-length':str(MAX_BYTES+1)},413),
    (b'\xff\xd8\xfffake',{'content-type':'image/jpeg','content-encoding':'gzip'},415),
])
def test_format_length_and_encoding_limits(body,headers,expected):
    with TestClient(create_app(cover_transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=Body(body),headers=headers)))) as client:
        assert client.get('/api/covers',params={'url':QQ}).status_code==expected


def test_stream_limit_and_response_cleanup():
    closed=[]
    class Bytes(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(33):yield b'x'*65536
        async def aclose(self):closed.append(True)
    with TestClient(create_app(cover_transport=httpx.MockTransport(lambda request:httpx.Response(200,headers={'content-type':'image/jpeg'},stream=Bytes())))) as client:
        assert client.get('/api/covers',params={'url':QQ}).status_code==413
    assert closed


def test_redirect_capacity_and_network_failure():
    with TestClient(create_app(cover_transport=httpx.MockTransport(lambda request:httpx.Response(302,headers={'location':QQ})) )) as client:
        assert client.get('/api/covers',params={'url':QQ}).status_code==502
    def timeout(request):raise httpx.ReadTimeout('夹具超时')
    with TestClient(create_app(cover_transport=httpx.MockTransport(timeout))) as client:
        assert client.get('/api/covers',params={'url':QQ}).status_code==502


@pytest.mark.parametrize('addresses',[['127.0.0.1'],['10.0.0.1'],['169.254.169.254'],['::1'],['224.0.0.1'],['8.8.8.8','192.168.1.1']])
def test_dns_special_addresses_never_connect(addresses):
    async def check():
        loop=asyncio.get_running_loop();original=loop.getaddrinfo
        async def answers(*args,**kwargs):return [(None,None,None,None,(address,443)) for address in addresses]
        loop.getaddrinfo=answers
        network=CoverNetwork()
        try:
            with pytest.raises(CoverRejected):await network.connect_tcp('y.gtimg.cn',443,timeout=.1)
        finally:loop.getaddrinfo=original
    asyncio.run(check())


def test_public_connection_is_pinned_and_peer_checked():
    async def check():
        loop=asyncio.get_running_loop();original=loop.getaddrinfo;calls=[];closed=[]
        async def answers(*args,**kwargs):return [(None,None,None,None,('8.8.8.8',443))]
        loop.getaddrinfo=answers
        class Stream:
            peer='8.8.8.8'
            def get_extra_info(self,key):return (self.peer,443)
            async def aclose(self):closed.append(True)
        stream=Stream()
        async def connect(host,*args):calls.append(host);return stream
        network=CoverNetwork();network.backend=SimpleNamespace(connect_tcp=connect)
        try:
            await network.connect_tcp('y.gtimg.cn',443)
            assert calls==['8.8.8.8']
            stream.peer='127.0.0.1'
            with pytest.raises(CoverRejected):await network.connect_tcp('y.gtimg.cn',443)
            assert closed
        finally:loop.getaddrinfo=original
    asyncio.run(check())


def test_concurrency_is_bounded():
    async def check():
        release=asyncio.Event();started=0
        class Bytes(httpx.AsyncByteStream):
            async def __aiter__(self):await release.wait();yield b'\xff\xd8\xfftest'
        async def handle(request):
            nonlocal started
            started+=1
            return httpx.Response(200,headers={'content-type':'image/jpeg'},stream=Bytes())
        reader=CoverReader(httpx.MockTransport(handle));tasks=[asyncio.create_task(reader.read(QQ)) for _ in range(4)]
        try:
            for _ in range(100):
                if started==4:break
                await asyncio.sleep(.001)
            with pytest.raises(CoverRejected) as error:await reader.read(QQ)
            assert error.value.code=='cover_busy'
            release.set();await asyncio.gather(*tasks)
        finally:release.set();await reader.close()
    asyncio.run(check())
