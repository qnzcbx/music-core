"""发布前的有界媒体检查，按来源使用现有目标规则。"""
from urllib.parse import urljoin
import re
import httpx
from app.media_stream import validate_target
from app.core.errors import CoreError,ErrorCode
from app.models import MediaRepresentation


async def verify_media(client,url,provider_id='qq',*,detail=False,headers=None):
    limit=65536 if detail else 4096
    try:
        for hop in range(4):
            await validate_target(url,provider_id)
            response=await client.send(httpx.Request('GET',url,headers={**(headers or {}),'Range':f'bytes=0-{limit-1}',
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
                    if not match or int(match[2])<=0 or int(match[1])!=min(limit-1,int(match[2])-1):
                        raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                    expected=int(match[1])+1
                mime=response.headers.get('content-type','').lower()
                if any(t in mime for t in ('html','json')) or response.headers.get('content-encoding','identity')!='identity':
                    raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                prefix=bytearray()
                async for chunk in response.aiter_raw(chunk_size=limit):
                    prefix.extend(chunk[:limit-len(prefix)])
                    if len(prefix)>=limit:break
                raw=bytes(prefix)
                if expected is not None and len(raw)!=expected:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                if not (raw.startswith((b'ID3',b'fLaC',b'OggS')) or raw[4:8]==b'ftyp' or len(raw)>1 and raw[0]==255 and raw[1]&224==224):
                    raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                kind='flac' if raw.startswith(b'fLaC') else 'mpeg-audio' if raw.startswith(b'ID3') or len(raw)>1 and raw[0]==255 and raw[1]&224==224 else 'ogg' if raw.startswith(b'OggS') else 'mp4'
                size=int(match[2]) if expected is not None else None
                length=response.headers.get('content-length','')
                if size is None and re.fullmatch(r'[0-9]{1,20}',length) and int(length)>0:size=int(length)
                if detail:
                    from app.download_quality import inspect_audio
                    return inspect_audio(raw).model_copy(update={'sizeBytes':size,'contentType':mime.split(';')[0] or None})
                return MediaRepresentation(container=kind,codec='flac' if kind=='flac' else 'mp3' if kind=='mpeg-audio' else None,
                    contentType=mime.split(';')[0] or None,sizeBytes=size,lossless=True if kind=='flac' else None)
            finally:await response.aclose()
    except httpx.TimeoutException:raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None
    except httpx.HTTPError:raise CoreError(ErrorCode.UPSTREAM_FAILURE) from None
