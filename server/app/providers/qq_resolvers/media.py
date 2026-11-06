"""外部结果发布前的有限媒体检查，沿用QQ媒体目标规则。"""
from urllib.parse import urljoin
import re
import httpx
from app.media_stream import validate_target
from app.core.errors import CoreError,ErrorCode


async def verify_media(client,url):
    try:
        for hop in range(4):
            await validate_target(url,'qq')
            response=await client.send(httpx.Request('GET',url,headers={'Range':'bytes=0-4095',
                'Accept-Encoding':'identity','User-Agent':'Mozilla/5.0'}),stream=True,follow_redirects=False,auth=None)
            try:
                if response.status_code in (301,302,303,307,308):
                    location=response.headers.get('location')
                    if not location or hop==3:raise CoreError(ErrorCode.UPSTREAM_FAILURE)
                    url=urljoin(url,location);continue
                if response.status_code in (401,403):raise CoreError(ErrorCode.ACCESS_DENIED)
                if response.status_code not in (200,206):raise CoreError(ErrorCode.UPSTREAM_FAILURE)
                expected=None
                if response.status_code==206:
                    match=re.fullmatch(r'bytes 0-([0-9]{1,20})/([0-9]{1,20})',response.headers.get('content-range',''))
                    if not match or int(match[2])<=0 or int(match[1])!=min(4095,int(match[2])-1):
                        raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                    expected=int(match[1])+1
                mime=response.headers.get('content-type','').lower()
                if any(t in mime for t in ('html','json')) or response.headers.get('content-encoding','identity')!='identity':
                    raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                prefix=bytearray()
                async for chunk in response.aiter_raw(chunk_size=4096):
                    prefix.extend(chunk[:4096-len(prefix)])
                    if len(prefix)>=4096:break
                raw=bytes(prefix)
                if expected is not None and len(raw)!=expected:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                if not (raw.startswith((b'ID3',b'fLaC',b'OggS')) or raw[4:8]==b'ftyp' or len(raw)>1 and raw[0]==255 and raw[1]&224==224):
                    raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                return
            finally:await response.aclose()
    except httpx.TimeoutException:raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None
    except httpx.HTTPError:raise CoreError(ErrorCode.UPSTREAM_FAILURE) from None
