"""仅供封面像素读取的受限通道，不接收任意媒体地址或平台凭据。"""
import asyncio
from contextlib import asynccontextmanager
import anyio
import ipaddress
import re
import socket
from urllib.parse import urlsplit, urljoin
import httpcore
import httpx
from fastapi import APIRouter, Request, Query
from fastapi.responses import Response, JSONResponse

MAX_BYTES = 2 * 1024 * 1024
PATHS = {
    'y.gtimg.cn': re.compile(r'/music/photo_new/T002R(150|300|500|800)x\1M000[A-Za-z0-9]{14}\.jpg'),
    'd.musicapp.migu.cn': re.compile(r'/data/oss/resource/[A-Za-z0-9]{2}/[A-Za-z0-9]{2}/[A-Za-z0-9]{2}/[a-f0-9]{32}\.(?:webp|jpg|jpeg|png)'),
}


class CoverRejected(Exception):
    def __init__(self, code='cover_rejected', status=400):
        self.code, self.status = code, status


def cover_url(value):
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None,443)
                or parsed.query or parsed.fragment or parsed.hostname not in PATHS
                or not PATHS[parsed.hostname].fullmatch(parsed.path)):
            raise CoverRejected()
        return 'https://' + parsed.hostname + parsed.path
    except ValueError: raise CoverRejected() from None


class CoverNetwork(httpcore.AsyncNetworkBackend):
    """校验全部 DNS 结果，并直接连接选定 IP；TLS 仍验证原域名。"""
    def __init__(self): self.backend = httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host not in PATHS or port != 443: raise CoverRejected()
        answers = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout or 3)
        addresses = list(dict.fromkeys(item[4][0] for item in answers))
        if not addresses or any(not ipaddress.ip_address(address).is_global or ipaddress.ip_address(address).is_multicast or ipaddress.ip_address(address).is_reserved for address in addresses):
            raise CoverRejected('cover_address_rejected', 403)
        # 优先 IPv4；不会把原域名交给连接层再次解析。
        addresses.sort(key=lambda value: ':' in value)
        stream = await self.backend.connect_tcp(addresses[0], port, timeout, local_address, socket_options)
        peer = stream.get_extra_info('server_addr')
        if not peer or ipaddress.ip_address(peer[0]) != ipaddress.ip_address(addresses[0]):
            await stream.aclose()
            raise CoverRejected('cover_address_rejected', 403)
        return stream

    async def sleep(self, seconds): await asyncio.sleep(seconds)


class CoverTransport(httpx.AsyncHTTPTransport):
    def __init__(self):
        super().__init__(trust_env=False, limits=httpx.Limits(max_connections=4, max_keepalive_connections=2), retries=0)
        # httpx 0.28.1 的公开传输层不暴露网络后端；仅此封面专用池需要固定地址。
        self._pool._network_backend = CoverNetwork()


def image_type(data):
    if data.startswith(b'\xff\xd8\xff'): return 'image/jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return 'image/png'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP': return 'image/webp'
    raise CoverRejected('cover_format_rejected', 415)


class CoverReader:
    def __init__(self, transport=None):
        self.client = httpx.AsyncClient(transport=transport if transport is not None else CoverTransport(),
            trust_env=False, timeout=httpx.Timeout(4, connect=3, pool=.2), follow_redirects=False)
        self.slots = asyncio.Semaphore(4)

    async def close(self): await self.client.aclose()

    async def read(self, url):
        target = cover_url(url)
        if self.slots.locked(): raise CoverRejected('cover_busy', 503)
        async with self.slots:
            return await asyncio.wait_for(self.fetch(target), 8)

    @asynccontextmanager
    async def response(self, target):
        response = await self.client.send(httpx.Request('GET', target, headers={'Accept':'image/jpeg,image/png,image/webp','Accept-Encoding':'identity'}), stream=True)
        self.client.cookies.clear()
        try: yield response
        finally:
            with anyio.CancelScope(shield=True): await response.aclose()

    async def fetch(self, target):
        for hop in range(3):
            # 独立请求，不合并 Cookie、认证头、Referer 或共享媒体客户端状态。
            async with self.response(target) as response:
                if response.status_code in (301,302,303,307,308):
                    if hop == 2 or not response.headers.get('location'): raise CoverRejected('cover_redirect_rejected', 502)
                    target = cover_url(urljoin(target, response.headers['location']))
                    continue
                if response.status_code != 200: raise CoverRejected('cover_upstream_failed', 502)
                if response.headers.get('content-encoding','identity').lower() != 'identity': raise CoverRejected('cover_format_rejected', 415)
                length = response.headers.get('content-length')
                if length is not None and (not re.fullmatch(r'\d{1,10}',length) or int(length)>MAX_BYTES): raise CoverRejected('cover_too_large', 413)
                data = bytearray()
                async for chunk in response.aiter_raw(chunk_size=65536):
                    data.extend(chunk)
                    if len(data)>MAX_BYTES: raise CoverRejected('cover_too_large', 413)
                kind = image_type(data)
                declared = response.headers.get('content-type','').split(';')[0].strip().lower()
                if declared not in ('image/jpeg','image/jpg','image/png','image/webp'): raise CoverRejected('cover_format_rejected', 415)
                return bytes(data),kind


def cover_router():
    router = APIRouter()
    @router.get('/api/covers', response_class=Response)
    async def cover(request: Request, url: str = Query(max_length=2048)):
        try:
            data, kind = await request.app.state.cover_reader.read(url)
            return Response(data, media_type=kind, headers={'Cache-Control':'private, max-age=3600','X-Content-Type-Options':'nosniff'})
        except CoverRejected as error:
            return JSONResponse(status_code=error.status, content={'error':{'code':error.code,'message':'封面暂时无法读取','retryable':error.status>=500}})
        except (httpx.HTTPError, OSError, asyncio.TimeoutError):
            return JSONResponse(status_code=502, content={'error':{'code':'cover_upstream_failed','message':'封面暂时无法读取','retryable':True}})
    return router
