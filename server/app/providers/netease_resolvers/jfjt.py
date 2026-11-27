"""jfjt原生ID表单协议；只使用本次返回地址，不迁入原库品质循环。"""
import asyncio
import json
import re
from urllib.parse import urlsplit
import httpx
from pydantic import SecretStr
from app.core.errors import CoreError, ErrorCode, UnsupportedRouteFormat, check_access


async def resolve(client,song_id,*,quality=None):
    if not isinstance(song_id,str) or not re.fullmatch(r'[1-9][0-9]{0,19}',song_id):raise CoreError(ErrorCode.INVALID_INPUT)
    async def execute():
        response=None
        try:
            request=httpx.Request('POST','https://dm.jfjt.cc/Song_V1',
                data={'url':song_id,'level':{'standard':'standard','high':'exhigh','lossless':'lossless'}.get(quality,'standard'),'type':'json'},headers={'User-Agent':'Mozilla/5.0','Referer':'https://dm.jfjt.cc/'})
            response=await client.send(request,stream=True,follow_redirects=False,auth=None)
            if response.status_code in (401,403):raise CoreError(ErrorCode.ACCESS_DENIED)
            if response.status_code!=200:raise CoreError(ErrorCode.UPSTREAM_FAILURE)
            raw=bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw)>2*1024*1024:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            try:body=json.loads(raw)
            except (ValueError,UnicodeError):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None
            if not isinstance(body,dict):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            check_access(body)
            if body.get('success') is not True:raise CoreError(ErrorCode.UPSTREAM_FAILURE)
            data=body.get('data')
            if not isinstance(data,dict):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            check_access(data)
            echoed=data.get('id')
            if echoed is not None and (type(echoed) not in (str,int) or str(echoed)!=song_id):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            url=data.get('url')
            if not url:raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
            try:
                if not isinstance(url,str):raise ValueError()
                parsed=urlsplit(url)
                if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:raise ValueError()
                if parsed.path.lower().endswith('.ncm'):raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
                if parsed.path.lower().endswith(('.m3u8','.mpd')):raise UnsupportedRouteFormat()
            except ValueError:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None
            return {'url':SecretStr(url),'evidence':'response_id_matched' if echoed is not None else 'request_bound',
                'title':data.get('name'),'artist':data.get('ar_name')}
        finally:
            if response is not None:await response.aclose()
    try:return await asyncio.wait_for(execute(),10)
    except (asyncio.TimeoutError,httpx.TimeoutException):raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None
    except httpx.HTTPError:raise CoreError(ErrorCode.UPSTREAM_FAILURE) from None
