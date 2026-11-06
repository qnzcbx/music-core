"""有界内存字节代理；能力验证由API完成，不存请求历史。"""
import asyncio
import ipaddress
import re
import socket
from time import time
from urllib.parse import urlsplit,urljoin
import anyio
import httpx
from starlette.responses import StreamingResponse
from app.core.errors import CoreError,ErrorCode

SAFE_HEADERS = ('content-type','content-length','content-range','accept-ranges','etag','last-modified')
MEDIA_DOMAINS={'kuwo':('kuwo.cn',),'qq':('stream.qqmusic.qq.com','aqqmusic.tc.qq.com'),
    'netease':('m701.music.126.net','m801.music.126.net','m10.music.126.net'),'migu':('freetyst.nf.migu.cn',)}


async def validate_target(url,provider_id='kuwo'):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        port = parsed.port
    except ValueError:
        raise CoreError(ErrorCode.UNTRUSTED_MEDIA) from None
    if (parsed.scheme not in ('http','https') or parsed.username or parsed.password
            or port not in (None,80,443) or not any(host==domain or provider_id!='migu' and host.endswith('.'+domain) for domain in MEDIA_DOMAINS.get(provider_id,()))):
        raise CoreError(ErrorCode.UNTRUSTED_MEDIA)
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(host,parsed.port or (443 if parsed.scheme=='https' else 80),type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise CoreError(ErrorCode.UNTRUSTED_MEDIA)
    except OSError:
        raise CoreError(ErrorCode.UPSTREAM_FAILURE) from None


def range_header(value):
    if value is None:
        return None
    match = re.fullmatch(r'bytes=(\d{0,20})-(\d{0,20})',value)
    if not match or not any(match.groups()):
        raise CoreError(ErrorCode.INVALID_RANGE)
    start,end = match.groups()
    if start and end and int(start)>int(end) or not start and int(end)==0:
        raise CoreError(ErrorCode.INVALID_RANGE)
    return value


class OwnedStream(StreamingResponse):
    def __init__(self, *args, cleanup, **kwargs):
        super().__init__(*args,**kwargs)
        self.cleanup = cleanup

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope,receive,send)
        finally:
            await self.cleanup()


async def proxy(request, media, client, release, target_check=validate_target):
    upstream = None
    closed = False

    async def cleanup():
        nonlocal closed
        if closed:
            return
        closed=True
        try:
            with anyio.CancelScope(shield=True):
                if upstream is not None:
                    await upstream.aclose()
        finally:
            release()

    try:
        if media.validUntil is not None and media.validUntil <= int(time()*1000):
            raise CoreError(ErrorCode.UPSTREAM_MEDIA_EXPIRED)
        requested = range_header(request.headers.get('range'))
        url = media.upstreamUrl.get_secret_value()
        # 浏览器Cookie/Authorization/Host均不透传；当前酷我只需普通UA/Referer。
        headers={k:v.get_secret_value() for k,v in media.headers.items() if k.lower() in ('user-agent','referer')}
        headers['Accept-Encoding']='identity'
        if requested:
            headers['Range']=requested
            condition=request.headers.get('if-range')
            if condition and len(condition)<=200 and not condition.startswith('W/'):
                headers['If-Range']=condition
        for redirect in range(4):
            if target_check is validate_target:await target_check(url,media.identity.providerId)
            else:await target_check(url)
            # 直接建Request防止共享Client自动合并Cookie和默认认证头。
            upstream = await client.send(httpx.Request(request.method,url,headers=headers),stream=True)
            if upstream.status_code not in (301,302,303,307,308):
                break
            location=upstream.headers.get('location')
            await upstream.aclose()
            if not location or redirect==3:
                raise CoreError(ErrorCode.UPSTREAM_FAILURE)
            url=urljoin(url,location)
            headers={k:v for k,v in headers.items() if k.lower() not in ('referer','authorization','cookie')}
        status=upstream.status_code
        if status in (401,403):
            raise CoreError(ErrorCode.ACCESS_DENIED)
        if status in (404,410):
            raise CoreError(ErrorCode.UPSTREAM_MEDIA_EXPIRED)
        if status not in (200,206,416):
            raise CoreError(ErrorCode.UPSTREAM_FAILURE)
        mime=upstream.headers.get('content-type','').lower()
        if status!=416 and ('html' in mime or 'json' in mime):
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        if upstream.headers.get('content-encoding','identity').lower()!='identity':
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        length=upstream.headers.get('content-length')
        expected_bytes=int(length) if length is not None and length.isdigit() else None
        if length is not None and not length.isdigit():
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        if status==206:
            match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+|\*)',upstream.headers.get('content-range',''))
            if not match or int(match[2])<int(match[1]):
                raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            expected=int(match[2])-int(match[1])+1
            expected_bytes=expected
            if (length is not None and int(length)!=expected) or (match[3]!='*' and int(match[2])>=int(match[3])):
                raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            if requested:
                first,last=requested[6:].split('-')
                if first and int(match[1])!=int(first):
                    raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                if last and first and int(match[2])>int(last):
                    raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                if not first and match[3]!='*' and int(match[1])!=max(0,int(match[3])-int(last)):
                    raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        if status==416 and 'content-range' in upstream.headers and not re.fullmatch(r'bytes \*/\d+',upstream.headers['content-range']):
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)

        async def body():
            received=0
            try:
                if request.method!='HEAD':
                    async for chunk in upstream.aiter_raw():
                        received+=len(chunk)
                        if expected_bytes is not None and received>expected_bytes:
                            raise RuntimeError('上游媒体长度超出声明')
                        yield chunk
                    if expected_bytes is not None and received!=expected_bytes:
                        raise RuntimeError('上游媒体传输不完整')
            except httpx.HTTPError:
                raise RuntimeError('上游媒体传输中断') from None
            finally:
                await cleanup()

        response_headers={k:upstream.headers[k] for k in SAFE_HEADERS if k in upstream.headers}
        if status==200:
            response_headers.pop('content-range',None)
        response_headers.update({'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'})
        return OwnedStream(body(),status_code=status,headers=response_headers,cleanup=cleanup)
    except BaseException as error:
        await cleanup()
        if isinstance(error,httpx.TimeoutException):
            raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None
        if isinstance(error,httpx.HTTPError):
            raise CoreError(ErrorCode.UPSTREAM_FAILURE) from None
        raise
