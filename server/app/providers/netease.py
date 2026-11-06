"""网易云原生匿名接口适配；搜索与取链分离，不使用外部解析或内置账号。"""
import asyncio
import json
import math
import re
from time import time
from uuid import uuid4
from urllib.parse import urlsplit
import httpx
from pydantic import ValidationError
from app.models import TrackIdentity,SongCandidate,SearchPage,ResolveOptions,ResolvedMedia,MediaRepresentation
from app.core.errors import CoreError,ErrorCode

SEARCH_URL='https://music.163.com/api/cloudsearch/pc'
PLAYER_URL='https://music.163.com/api/song/enhance/player/url'
HEADERS={'User-Agent':'Mozilla/5.0','Referer':'https://music.163.com/'}


def song_id(value):
    if type(value) is int and value>0:return str(value)
    if isinstance(value,str) and re.fullmatch(r'[1-9][0-9]{0,19}',value):return value
    return None


def candidate_from(raw):
    identifier=song_id(raw.get('id'))
    if not identifier:return None
    album=raw.get('al') if isinstance(raw.get('al'),dict) else {}
    artists=raw.get('ar') if isinstance(raw.get('ar'),list) else []
    duration=raw.get('dt')
    if type(duration) not in (int,float) or not math.isfinite(duration) or duration<0:duration=None
    try:
        return SongCandidate(identity=TrackIdentity(providerId='netease',platformId=identifier),title=raw.get('name'),
            artists=tuple(a['name'] for a in artists if isinstance(a,dict) and isinstance(a.get('name'),str) and a['name']),
            album=album.get('name'),cover=album.get('picUrl') or None,
            durationSeconds=duration/1000 if duration is not None else None)
    except ValidationError:return None


class NeteaseProvider:
    async def get_lyrics(self, identity):
        from app.lyrics import provider_lyrics
        return await provider_lyrics(self, identity)

    id='netease'

    def __init__(self,client: httpx.AsyncClient,*,route_order=('native',)):
        if not isinstance(route_order,(tuple,list)) or not route_order or any(r not in ('native','gdstudio-preview','jfjt') for r in route_order) or len(set(route_order))!=len(route_order):raise ValueError('Invalid Netease resolver order')
        self.client=client
        self.route_order=tuple(route_order)
        self.last_resolution=None

    async def request_json(self,url,form):
        async def execute():
            response=None
            try:
                # 显式Request隔离共享客户端的Cookie、认证和默认请求头。
                response=await self.client.send(httpx.Request('POST',url,data=form,headers=HEADERS),stream=True,follow_redirects=False)
                if response.status_code in (401,403):raise CoreError(ErrorCode.ACCESS_DENIED)
                if response.status_code!=200:raise CoreError(ErrorCode.UPSTREAM_FAILURE)
                body=bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body)>2*1024*1024:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                try:data=json.loads(body)
                except (ValueError,UnicodeError):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None
                if not isinstance(data,dict):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                if data.get('code') in (301,401,403):raise CoreError(ErrorCode.ACCESS_DENIED)
                if data.get('code')!=200:raise CoreError(ErrorCode.UPSTREAM_FAILURE)
                return data
            finally:
                if response is not None:await response.aclose()
        try:return await asyncio.wait_for(execute(),20)
        except (httpx.TimeoutException,asyncio.TimeoutError):raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None
        except httpx.HTTPError:raise CoreError(ErrorCode.UPSTREAM_FAILURE) from None

    async def search(self,query: str,limit: int,cursor: str | None=None) -> SearchPage:
        if not isinstance(query,str) or not 1<=len(query.strip())<=80 or type(limit)is not int or not 1<=limit<=10:
            raise CoreError(ErrorCode.INVALID_INPUT)
        page=1
        if cursor is not None:
            if not isinstance(cursor,str) or not re.fullmatch(r'([2-9]|10):([1-9]|10)',cursor):raise CoreError(ErrorCode.INVALID_INPUT)
            page,old_limit=map(int,cursor.split(':'))
            if old_limit!=limit:raise CoreError(ErrorCode.INVALID_INPUT)
        data=await self.request_json(SEARCH_URL,{'s':query.strip(),'type':'1','limit':str(limit),'offset':str((page-1)*limit)})
        result=data.get('result')
        if not isinstance(result,dict):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        rows=result.get('songs',[] if result.get('songCount')==0 else None)
        if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        items=[];seen=set()
        for row in rows[:limit]:
            candidate=candidate_from(row)
            if candidate and candidate.identity.key not in seen:items.append(candidate);seen.add(candidate.identity.key)
        total=result.get('songCount')
        more=bool(rows) and page<10 and (type(total)is not int or page*limit<total)
        return SearchPage(items=tuple(items),nextCursor=f'{page+1}:{limit}' if more else None)

    async def resolve(self,identity: TrackIdentity,options: ResolveOptions | None=None) -> ResolvedMedia:
        self.last_resolution=None
        if identity.providerId!='netease':raise CoreError(ErrorCode.UNSUPPORTED_PROVIDER)
        options=options or ResolveOptions()
        if options.providerQualityId is not None:raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
        async def execute():
            failure=None
            for route in self.route_order:
                try:
                    if route=='native':
                        value=await self._resolve_native(identity,options)
                        self.last_resolution={'resolver':'native','identity':'response_id_matched','scope':'normal'}
                        return value
                    from .netease_resolvers import gdstudio,jfjt
                    from app.core.media_probe import verify_media
                    adapter=gdstudio if route=='gdstudio-preview' else jfjt
                    candidate=await adapter.resolve(self.client,identity.platformId)
                    if route=='jfjt':
                        detail=await self.request_json('https://music.163.com/api/v3/song/detail',
                            {'c':json.dumps([{'id':int(identity.platformId),'v':0}])})
                        songs=detail.get('songs')
                        if not isinstance(songs,list) or len(songs)!=1 or not isinstance(songs[0],dict) or song_id(songs[0].get('id'))!=identity.platformId:
                            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                        title=candidate.get('title');artist=candidate.get('artist')
                        if not isinstance(title,str) or title.strip()!=str(songs[0].get('name','')).strip():raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                        artists=songs[0].get('ar')
                        if not isinstance(artists,list):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                        expected={a['name'].strip().casefold() for a in artists if isinstance(a,dict) and isinstance(a.get('name'),str)}
                        actual={a.strip().casefold() for a in re.split(r'[/,、，]',artist) if a.strip()} if isinstance(artist,str) else set()
                        if not actual or not actual<=expected:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                    representation=await verify_media(self.client,candidate['url'].get_secret_value(),'netease')
                    self.last_resolution={'resolver':route,'identity':candidate['evidence'],'scope':'configured_preview'}
                    return ResolvedMedia(id=uuid4().hex,identity=identity,resolvedAt=int(time()*1000),validUntil=None,
                        upstreamUrl=candidate['url'],headers={'User-Agent':'Mozilla/5.0'},representation=representation)
                except CoreError as error:
                    if error.code not in (ErrorCode.UPSTREAM_FAILURE,ErrorCode.UPSTREAM_TIMEOUT,ErrorCode.MEDIA_UNAVAILABLE):raise
                    failure=error
            raise failure
        try:return await asyncio.wait_for(execute(),25)
        except asyncio.TimeoutError:raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None

    async def _resolve_native(self,identity: TrackIdentity,options: ResolveOptions | None=None) -> ResolvedMedia:
        if identity.providerId!='netease':raise CoreError(ErrorCode.UNSUPPORTED_PROVIDER)
        options=options or ResolveOptions()
        if options.providerQualityId is not None:raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
        # 普通128kbps原生取链，不尝试第三方账号、高品质解锁或DRM处理。
        data=await self.request_json(PLAYER_URL,{'ids':json.dumps([int(identity.platformId)]),'br':'128000'})
        rows=data.get('data')
        if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        row=rows[0]
        if song_id(row.get('id'))!=identity.platformId:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        if row.get('code') in (301,401,403):raise CoreError(ErrorCode.ACCESS_DENIED)
        if row.get('code')==404:raise CoreError(ErrorCode.TRACK_NOT_FOUND)
        if row.get('code')!=200:
            error=CoreError(ErrorCode.UPSTREAM_FAILURE)
            error.platform_code=row.get('code') if type(row.get('code'))is int else None
            raise error
        if not row.get('url'):raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
        # 试听截取不能静默伪装成完整录音；不推断空URL的会员原因。
        if row.get('freeTrialInfo'):raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
        now=int(time()*1000)
        expiry=row.get('expi')
        valid_until=now+expiry*1000 if type(expiry)is int and 0<expiry<=86400 else None
        size=row.get('size');bitrate=row.get('br')
        try:
            if isinstance(row['url'],str) and urlsplit(row['url']).path.lower().endswith(('.m3u8','.mpd')):
                raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
            return ResolvedMedia(id=uuid4().hex,identity=identity,resolvedAt=now,validUntil=valid_until,
                upstreamUrl=row['url'],headers=HEADERS,
                representation=MediaRepresentation(providerQualityId='standard',
                    sizeBytes=size if type(size)is int and size>0 else None,
                    bitrateBps=bitrate if type(bitrate)is int and bitrate>0 else None))
        except (ValueError,ValidationError):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None
