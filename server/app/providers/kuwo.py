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
from app.download_quality import requested, qualify
from app.core.errors import CoreError, ErrorCode
from app.models import SongCandidate, TrackIdentity, SearchPage, ResolvedMedia, ResolveOptions, MediaRepresentation

SEARCH_URL = 'https://www.kuwo.cn/search/searchMusicBykeyWord'
RESOLVE_URL = 'https://www.kuwo.cn/api/v1/www/music/playUrl'
MOBI_URL = 'https://mobi.kuwo.cn/mobi.s'
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
    cover = next((value for field in ('hts_MVPIC', 'albumpic', 'pic')
                  if isinstance(value := raw.get(field), str) and value.startswith(('http://', 'https://'))), None)
    album = raw.get('ALBUM') or raw.get('album')
    short = raw.get('web_albumpic_short')
    if cover is None and isinstance(short, str) and re.fullmatch(
        r'[0-9]{1,4}/[A-Za-z0-9]{1,24}/[0-9]{1,8}/[0-9]{1,24}\.jpg', short
    ):
        cover = f'https://img1.kuwo.cn/star/albumcover/{short}'
    try:
        return SongCandidate(identity=TrackIdentity(providerId='kuwo', platformId=str(pid).removeprefix('MUSIC_')),
            title=html.unescape(title), artists=artists, album=html.unescape(album) if isinstance(album,str) and album else None,
            durationSeconds=duration, cover=cover)
    except ValidationError:
        return None


class KuwoProvider:
    async def get_lyrics(self, identity):
        from app.lyrics import provider_lyrics
        return await provider_lyrics(self, identity)

    id = 'kuwo'

    def __init__(self, client: httpx.AsyncClient):
        # Client由应用lifespan或独立验证脚本持有并关闭，Provider不私建连接池。
        self.client = client

    async def request(self, url, params, *, raw=False, headers=None):
        try:
            return await asyncio.wait_for(self._request(url, params, raw=raw, headers=headers), timeout=20)
        except (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError):
            raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None

    async def _request(self, url, params, *, raw=False, headers=None):
        try:
            async with self.client.stream('GET', url, params=params, headers={
                **({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.kuwo.cn/'} if headers is None else headers)}) as response:
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
            return bytes(body) if raw else decode_response(bytes(body))
        except (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError):
            raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None
        except httpx.HTTPError:
            raise CoreError(ErrorCode.UPSTREAM_FAILURE) from None

    async def search(self, query: str, limit: int, cursor: str | None = None) -> SearchPage:
        if not isinstance(query,str) or not 1 <= len(query.strip()) <= 80 or type(limit) is not int or not 1 <= limit <= 15:
            raise CoreError(ErrorCode.INVALID_INPUT)
        # 游标绑定页大小，防止续页时改变limit导致跳曲或重复；最多十页。
        page = 0
        if cursor is not None:
            if not isinstance(cursor,str) or not re.fullmatch(r'[1-9]:[1-9][0-9]?',cursor):
                raise CoreError(ErrorCode.INVALID_INPUT)
            page, previous_limit = map(int,cursor.split(':'))
            if previous_limit != limit:
                raise CoreError(ErrorCode.INVALID_INPUT)
        # 旧搜索携带vipver；实测遗漏它会使同词原版录音不进入上游结果。
        data = await self.request(SEARCH_URL, {'all':query.strip(),'ft':'music','client':'kt','vipver':'1',
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
        quality=requested(options)
        data = await self.request(RESOLVE_URL, {'mid':identity.platformId,'type':'music','httpsStatus':1})
        # 仅已实测的接口级请求拒绝可切到同平台mobi；权限码、超时、取消均不重试。
        if (data.get('success') is False and data.get('code') is None
                and data.get('message') == 'The request is illegal!'):
            return await qualify(self.client,await self.resolve_mobi(identity,quality),quality)
        if data.get('success') is False or data.get('code') in (401,403,'401','403'):
            raise CoreError(ErrorCode.ACCESS_DENIED)
        if data.get('code') not in (0,200,'0','200'):
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        payload = data.get('data')
        if not isinstance(payload,dict):
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        if quality:
            return await qualify(self.client,await self.resolve_mobi(identity,quality),quality)
        url = payload.get('url')
        if not url:
            raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
        return self.media_from_url(identity, url)

    async def resolve_mobi(self, identity: TrackIdentity, quality=None) -> ResolvedMedia:
        if identity.providerId != self.id:
            raise CoreError(ErrorCode.UNSUPPORTED_PROVIDER)
        content = await self.request(MOBI_URL, {'user':'0','corp':'kuwo',
            'source':'kwplayer_ar_5.1.0.0_B_jiakong_vh.apk','p2p':'1',
            'type':'convert_url2','sig':'0','format':'flac' if quality=='lossless' else 'mp3','rid':identity.platformId,
            **({'br':'320k' if quality=='high' else '128k'} if quality in ('standard','high') else {})},
            raw=True,headers={'User-Agent':'okhttp/3.10.0'})
        try:
            lines = content.decode('utf8').splitlines()
            fields = {}
            for line in lines:
                if '=' not in line:
                    continue
                key,value = line.split('=',1)
                if key in fields:
                    raise ValueError()
                fields[key] = value.strip()
        except (UnicodeError,ValueError):
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None
        if fields.get('rid') != identity.platformId:
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        if not fields.get('url'):
            raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
        # format/bitrate只是平台声明，未经过字节检测，保持通用表示字段未知。
        return self.media_from_url(identity, fields['url'], headers={'User-Agent':'okhttp/3.10.0'})

    @staticmethod
    def media_from_url(identity, url, headers=None):
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError()
            if parsed.path.lower().endswith('.m3u8'):
                raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
            # 后缀不作为编码证据；本期取链成功与媒体可播放、可完整下载分开。
            return ResolvedMedia(id=uuid4().hex, identity=identity,representation=MediaRepresentation(),
                resolvedAt=int(time()*1000), validUntil=None,upstreamUrl=url,
                headers=headers if headers is not None else {'User-Agent':'Mozilla/5.0','Referer':'https://www.kuwo.cn/'})
        except (TypeError,ValueError,ValidationError):
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None
