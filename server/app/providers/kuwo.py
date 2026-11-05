"""酷我元数据搜索与站内取链；不使用第三方替代线路。"""
import ast
import asyncio
import html
import json
import math
import re
from time import time
from uuid import uuid4
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError
from app.core.errors import CoreError, ErrorCode
from app.models import SongCandidate, TrackIdentity, SearchPage, ResolvedMedia, ResolveOptions, MediaRepresentation

SEARCH_URL = 'https://www.kuwo.cn/search/searchMusicBykeyWord'
RESOLVE_URL = 'https://www.kuwo.cn/api/v1/www/music/playUrl'
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def decode_response(content: bytes):
    """旧接口实际返回单引号字典；只解析字面量，绝不执行代码。"""
    try:
        text = content.decode('utf8')
        try:
            data = json.loads(text)
        except ValueError:
            data = ast.literal_eval(text)
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (ValueError, SyntaxError, UnicodeError, RecursionError, MemoryError):
        raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None


def candidate_from(raw: dict) -> SongCandidate | None:
    """MUSICRID去掉MUSIC_前缀后是录音ID；缺损记录不冒充完整结果。"""
    pid = raw.get('MUSICRID', raw.get('musicrid'))
    if isinstance(pid, bool) or not isinstance(pid, (str, int)):
        return None
    title = raw.get('SONGNAME') or raw.get('name') or raw.get('songName')
    if not isinstance(title, str) or not title.strip():
        return None
    artist = raw.get('ARTIST') or raw.get('artist')
    artists = tuple(s.strip() for s in re.split(r'&|;', html.unescape(artist)) if s.strip()) if isinstance(artist, str) else ()
    duration = raw.get('DURATION', raw.get('duration'))
    try:
        duration = float(duration) if duration is not None and not isinstance(duration, bool) else None
        if duration is not None and (not math.isfinite(duration) or duration < 0):
            duration = None
    except (TypeError, ValueError):
        duration = None
    cover = raw.get('hts_MVPIC') or raw.get('albumpic') or raw.get('pic')
    if not isinstance(cover, str) or not cover.startswith(('http://', 'https://')):
        cover = None
    album = raw.get('ALBUM') or raw.get('album')
    try:
        return SongCandidate(identity=TrackIdentity(providerId='kuwo', platformId=str(pid).removeprefix('MUSIC_')),
            title=html.unescape(title), artists=artists, album=html.unescape(album) if isinstance(album,str) and album else None,
            durationSeconds=duration, cover=cover)
    except ValidationError:
        return None


class KuwoProvider:
    id = 'kuwo'

    def __init__(self, client: httpx.AsyncClient):
        # Client由应用lifespan或独立验证脚本持有并关闭，Provider不私建连接池。
        self.client = client

    async def request(self, url, params):
        try:
            return await asyncio.wait_for(self._request(url, params), timeout=20)
        except (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError):
            raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None

    async def _request(self, url, params):
        try:
            async with self.client.stream('GET', url, params=params, headers={
                'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.kuwo.cn/'}) as response:
                if response.status_code in (401,403):
                    raise CoreError(ErrorCode.ACCESS_DENIED)
                if response.status_code == 404:
                    raise CoreError(ErrorCode.TRACK_NOT_FOUND)
                if response.status_code != 200:
                    raise CoreError(ErrorCode.UPSTREAM_FAILURE)
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            return decode_response(bytes(body))
        except (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError):
            raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None
        except httpx.HTTPError:
            raise CoreError(ErrorCode.UPSTREAM_FAILURE) from None

    async def search(self, query: str, limit: int, cursor: str | None = None) -> SearchPage:
        if not isinstance(query,str) or not 1 <= len(query.strip()) <= 80 or type(limit) is not int or not 1 <= limit <= 10:
            raise CoreError(ErrorCode.INVALID_INPUT)
        # 游标绑定页大小，防止续页时改变limit导致跳曲或重复；最多十页。
        page = 0
        if cursor is not None:
            if not isinstance(cursor,str) or not re.fullmatch(r'[1-9]:[1-9][0-9]?',cursor):
                raise CoreError(ErrorCode.INVALID_INPUT)
            page, previous_limit = map(int,cursor.split(':'))
            if previous_limit != limit:
                raise CoreError(ErrorCode.INVALID_INPUT)
        data = await self.request(SEARCH_URL, {'all':query.strip(),'ft':'music','client':'kt',
            'pn':page,'rn':limit,'rformat':'json','encoding':'utf8','mobi':'1'})
        if data.get('success') is False or data.get('code') not in (None,0,200,'0','200'):
            raise CoreError(ErrorCode.UPSTREAM_FAILURE)
        rows = data.get('abslist')
        if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        items = []
        seen = set()
        for raw in rows[:limit]:
            candidate = candidate_from(raw)
            if candidate and candidate.identity.key not in seen:
                seen.add(candidate.identity.key)
                items.append(candidate)
        total = data.get('TOTAL')
        more = bool(rows) and page < 9
        if isinstance(total,(str,int)) and not isinstance(total,bool) and str(total).isdigit():
            more = more and (page+1)*limit < int(total)
        return SearchPage(items=tuple(items),nextCursor=f'{page+1}:{limit}' if more else None)

    async def resolve(self, identity: TrackIdentity, options: ResolveOptions | None = None) -> ResolvedMedia:
        if identity.providerId != self.id:
            raise CoreError(ErrorCode.UNSUPPORTED_PROVIDER)
        options = options or ResolveOptions()
        if options.purpose != 'playback' or options.providerQualityId is not None:
            raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
        data = await self.request(RESOLVE_URL, {'mid':identity.platformId,'type':'music','httpsStatus':1})
        if data.get('success') is False or data.get('code') in (401,403,'401','403'):
            raise CoreError(ErrorCode.ACCESS_DENIED)
        if data.get('code') not in (0,200,'0','200'):
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        payload = data.get('data')
        if not isinstance(payload,dict):
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        url = payload.get('url')
        if not url:
            raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError()
            if parsed.path.lower().endswith('.m3u8'):
                raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
            # 后缀不作为编码证据；本期取链成功与媒体可播放、可完整下载分开。
            return ResolvedMedia(id=uuid4().hex, identity=identity,representation=MediaRepresentation(),
                resolvedAt=int(time()*1000), validUntil=None,upstreamUrl=url,
                headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.kuwo.cn/'})
        except (TypeError,ValueError,ValidationError):
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None
