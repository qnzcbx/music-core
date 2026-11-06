"""QQ外部协议适配；实现状态不等于服务使用资格。"""
import asyncio
import json
import re
from dataclasses import dataclass,field
from urllib.parse import urlsplit
import httpx
from pydantic import SecretStr
from app.core.errors import CoreError,ErrorCode


@dataclass(frozen=True)
class RouteResult:
    route_id: str
    url: SecretStr=field(repr=False)
    response_mid: str | None=None
    title: str | None=None
    artist: str | None=None

    @property
    def evidence(self):
        return 'confirmed' if self.response_mid is not None else 'request_bound'


def result(route,mid,payload):
    if not isinstance(payload,dict):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    echoed=payload.get('song_mid') or payload.get('mid')
    if echoed is not None and echoed!=mid:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    url=payload.get('url')
    if not url:raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
    try:
        if not isinstance(url,str):raise ValueError()
        parsed=urlsplit(url)
        if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:raise ValueError()
        if parsed.path.lower().endswith(('.m3u8','.mpd')):raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
    except ValueError:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None
    return RouteResult(route,SecretStr(url),echoed,
        payload.get('song_name'),payload.get('singer_name'))


def check_mid(mid):
    if not isinstance(mid,str) or not re.fullmatch(r'[A-Za-z0-9]{1,64}',mid):raise CoreError(ErrorCode.INVALID_INPUT)


async def request_json(client,request):
    async def execute():
        response=None
        try:
            response=await client.send(request,stream=True,follow_redirects=False,auth=None)
            if response.status_code in (401,403):raise CoreError(ErrorCode.ACCESS_DENIED)
            if response.status_code!=200:raise CoreError(ErrorCode.UPSTREAM_FAILURE)
            raw=bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw)>2*1024*1024:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            try:data=json.loads(raw)
            except (ValueError,UnicodeError):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None
            if not isinstance(data,dict):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            if data.get('code') in (401,403,'401','403'):raise CoreError(ErrorCode.ACCESS_DENIED)
            if data.get('code') not in (None,0,200,'0','200'):raise CoreError(ErrorCode.UPSTREAM_FAILURE)
            return data
        finally:
            if response is not None:await response.aclose()
    try:return await asyncio.wait_for(execute(),10)
    except (asyncio.TimeoutError,httpx.TimeoutException):raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None
    except httpx.HTTPError:raise CoreError(ErrorCode.UPSTREAM_FAILURE) from None
