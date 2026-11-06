"""GD网易云URL接口；请求绑定与响应身份分别处理，不缓存媒体。"""
import asyncio
import json
import re
from urllib.parse import urlsplit
import httpx
from pydantic import SecretStr
from app.core.errors import CoreError,ErrorCode


async def resolve(client,song_id):
    if not isinstance(song_id,str) or not re.fullmatch(r'[1-9][0-9]{0,19}',song_id):raise CoreError(ErrorCode.INVALID_INPUT)
    async def execute():
        response=None
        try:
            request=httpx.Request('GET','https://music-api.gdstudio.xyz/api.php',
                params={'types':'url','id':song_id,'source':'netease','br':999},headers={'User-Agent':'Mozilla/5.0'})
            response=await client.send(request,stream=True,follow_redirects=False,auth=None)
            if response.status_code in (401,403):raise CoreError(ErrorCode.ACCESS_DENIED)
            if response.status_code!=200:raise CoreError(ErrorCode.UPSTREAM_FAILURE)
            body=bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body)>2*1024*1024:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            try:data=json.loads(body)
            except (ValueError,UnicodeError):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None
            if not isinstance(data,dict):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            if data.get('code') in (401,403,'401','403'):raise CoreError(ErrorCode.ACCESS_DENIED)
            if data.get('code') not in (None,0,200,'0','200'):raise CoreError(ErrorCode.UPSTREAM_FAILURE)
            echoed=data.get('id')
            if echoed is not None and (type(echoed) not in (int,str) or str(echoed)!=song_id):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            url=data.get('url')
            if not url:raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
            try:
                if not isinstance(url,str):raise ValueError()
                p=urlsplit(url)
                if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:raise ValueError()
                if p.path.lower().endswith(('.m3u8','.mpd')):raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
            except ValueError:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None
            return {'url':SecretStr(url),'evidence':'response_id_matched' if echoed is not None else 'request_bound'}
        finally:
            if response is not None:await response.aclose()
    try:return await asyncio.wait_for(execute(),10)
    except (asyncio.TimeoutError,httpx.TimeoutException):raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None
    except httpx.HTTPError:raise CoreError(ErrorCode.UPSTREAM_FAILURE) from None
