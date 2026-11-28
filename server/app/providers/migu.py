"""咪咕原生异步适配；按contentId重建双ID上下文，不保留搜索缓存。"""
import asyncio
import json
import math
import re
from time import time
from urllib.parse import urljoin,urlsplit
from uuid import uuid4
import httpx
from pydantic import ValidationError
from app.models import TrackIdentity,SongCandidate,SearchPage,ResolveOptions,ResolvedMedia,MediaRepresentation
from app.download_quality import requested, qualify
from app.core.errors import CoreError,ErrorCode

SEARCH_URL='https://c.musicapp.migu.cn/v1.0/content/search_all.do'
DETAIL_URL='https://c.musicapp.migu.cn/v1.0/content/resourceinfo.do'
PLAYER_URL='https://c.musicapp.migu.cn/strategy/listen-url/h5/v2.4'
HEADERS={'User-Agent':'Mozilla/5.0','Accept':'application/json, text/plain, */*',
    'Origin':'https://h5.nf.migu.cn','Referer':'https://h5.nf.migu.cn/',
    'ua':'Android_migu','version':'6.8.8','channel':'014021I','subchannel':'014021I'}
# 这是平台响应的公开字节混淆参数，不是账号凭据或音频解密密钥。
RESPONSE_KEY=b'Jk8qzuePiJ1qE3mDYhLQ3T73DtDoAhLP'
MAGIC=b'\xab\xcd\x01'


def identifier(value,*,copyright=False):
    if type(value)is int and value>0:value=str(value)
    pattern=r'[A-Za-z0-9]{1,64}' if copyright else r'[1-9][0-9]{0,31}'
    return value if isinstance(value,str) and re.fullmatch(pattern,value) else None


def decode_response(raw,signature=None):
    try:
        if signature=='1' or raw.startswith(MAGIC):
            if len(raw)<5 or not raw.startswith(MAGIC):raise ValueError()
            seed=raw[3]
            raw=bytes((byte+seed-RESPONSE_KEY[i%len(RESPONSE_KEY)])&255 for i,byte in enumerate(raw[4:]))
        result=json.loads(raw)
        if not isinstance(result,dict):raise ValueError()
        return result
    except (ValueError,UnicodeError):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None


def candidate_from(raw):
    content=identifier(raw.get('contentId'))
    if not content:return None
    artists=raw.get('singers') or raw.get('singerList') or []
    albums=raw.get('albums') if isinstance(raw.get('albums'),list) else []
    images=raw.get('imgItems') if isinstance(raw.get('imgItems'),list) else []
    cover=next((i['img'] for i in reversed(images) if isinstance(i,dict) and isinstance(i.get('img'),str) and i['img']),None)
    cover=cover or raw.get('img3') or raw.get('img2') or raw.get('img1')
    duration=raw.get('duration')
    if type(duration) not in (int,float) or not math.isfinite(duration) or duration<0:duration=None
    try:
        return SongCandidate(identity=TrackIdentity(providerId='migu',platformId=content),
            title=raw.get('name') or raw.get('songName'),
            artists=tuple(a['name'] for a in artists if isinstance(a,dict) and isinstance(a.get('name'),str) and a['name']) if isinstance(artists,list) else (),
            album=raw.get('album') or ', '.join(a['name'] for a in albums if isinstance(a,dict) and isinstance(a.get('name'),str)) or None,
            cover=urljoin('https://d.musicapp.migu.cn',cover) if isinstance(cover,str) else None,durationSeconds=duration)
    except (ValidationError,ValueError):return None


class MiguProvider:
    async def get_lyrics(self, identity):
        from app.lyrics import provider_lyrics
        return await provider_lyrics(self, identity)

    id='migu'

    def __init__(self,client: httpx.AsyncClient):self.client=client

    async def request_json(self,url,params,*,listen=False):
        async def execute():
            response=None
            try:
                headers=dict(HEADERS)
                if listen:headers.update({'Content-Type':'application/json;charset=UTF-8','birth':'h5page','signature':'1'})
                response=await self.client.send(httpx.Request('GET',url,params=params,headers=headers),stream=True,follow_redirects=False,auth=None)
                if response.status_code in (401,403):raise CoreError(ErrorCode.ACCESS_DENIED)
                if response.status_code==404:raise CoreError(ErrorCode.TRACK_NOT_FOUND)
                if response.status_code!=200:raise CoreError(ErrorCode.UPSTREAM_FAILURE)
                body=bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body)>2*1024*1024:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                data=decode_response(body,response.headers.get('signature'))
                code=data.get('code',data.get('returnCode'))
                if str(code) in ('401','403'):raise CoreError(ErrorCode.ACCESS_DENIED)
                if str(code) in ('404',):raise CoreError(ErrorCode.TRACK_NOT_FOUND)
                if code is not None and str(code) not in ('0','000000','200'):
                    raise CoreError(ErrorCode.UPSTREAM_FAILURE)
                return data
            finally:
                if response is not None:await response.aclose()
        try:return await asyncio.wait_for(execute(),20)
        except (asyncio.TimeoutError,httpx.TimeoutException):raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None
        except httpx.HTTPError:raise CoreError(ErrorCode.UPSTREAM_FAILURE) from None

    async def song_detail(self, content_id):
        return await self.request_json(DETAIL_URL, {'resourceId': content_id, 'resourceType': '2'})

    async def search(self,query: str,limit: int,cursor: str | None=None) -> SearchPage:
        if not isinstance(query,str) or not 1<=len(query.strip())<=80 or type(limit)is not int or not 1<=limit<=15:
            raise CoreError(ErrorCode.INVALID_INPUT)
        page=1
        if cursor is not None:
            if not isinstance(cursor,str) or not re.fullmatch(r'([2-9]|10):(1[0-5]|[1-9])',cursor):raise CoreError(ErrorCode.INVALID_INPUT)
            page,old_limit=map(int,cursor.split(':'))
            if old_limit!=limit:raise CoreError(ErrorCode.INVALID_INPUT)
        data=await self.request_json(SEARCH_URL,{'text':query.strip(),'pageNo':page,'pageSize':limit,
            'isCopyright':1,'sort':1,'searchSwitch':str({'song':1,'album':0,'singer':0,'tagSong':1,'mvSong':0,'bestShow':1})})
        result=data.get('songResultData')
        if not isinstance(result,dict):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        rows=result.get('result')
        if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        items=[];seen=set()
        for row in rows[:limit]:
            candidate=candidate_from(row)
            if candidate and candidate.identity.key not in seen:items.append(candidate);seen.add(candidate.identity.key)
        total=result.get('totalCount')
        if isinstance(total,str) and re.fullmatch(r'[0-9]{1,10}',total):total=int(total)
        more=bool(rows) and page<10 and (type(total)is not int or page*limit<total)
        return SearchPage(items=tuple(items),nextCursor=f'{page+1}:{limit}' if more else None)

    async def resolve(self,identity: TrackIdentity,options: ResolveOptions | None=None) -> ResolvedMedia:
        if identity.providerId!='migu':raise CoreError(ErrorCode.UNSUPPORTED_PROVIDER)
        options=options or ResolveOptions()
        quality=requested(options)
        if quality=='lossless':raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
        # 先按精确资源ID重新取得双ID及格式目录，绝不按歌名猜测录音。
        metadata=await self.song_detail(identity.platformId)
        rows=metadata.get('resource')
        if not isinstance(rows,list):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        if not rows:raise CoreError(ErrorCode.TRACK_NOT_FOUND)
        if len(rows)!=1 or not isinstance(rows[0],dict):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        raw=rows[0]
        if identifier(raw.get('contentId'))!=identity.platformId:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        copyright_id=identifier(raw.get('copyrightId'),copyright=True)
        if not copyright_id:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        if raw.get('needEncrypt') not in (None,0,'0',False):raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
        formats=[]
        for field in ('rateFormats','newRateFormats','audioFormats'):
            if isinstance(raw.get(field),list):formats.extend(raw[field])
        chosen=next((f for tone in (('PQ','LQ','HQ') if quality is None else ('HQ',) if quality=='high' else ('PQ',)) for f in formats if isinstance(f,dict) and f.get('formatType')==tone and identifier(f.get('resourceType'))),None)
        if chosen is None:raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
        data=await self.request_json(PLAYER_URL,{'contentId':identity.platformId,'copyrightId':copyright_id,
            'resourceType':str(chosen['resourceType']),'netType':'01','toneFlag':chosen['formatType'],
            'scene':'','lowerQualityContentId':identity.platformId},listen=True)
        body=data.get('data')
        if not isinstance(body,dict):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        song=body.get('song')
        if not isinstance(song,dict) or identifier(song.get('contentId'))!=identity.platformId or identifier(song.get('copyrightId'),copyright=True)!=copyright_id:
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        actual_format=body.get('audioFormatType')
        if actual_format is not None and actual_format not in ('PQ','LQ','HQ'):raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
        if body.get('freeListenType') not in (None,0,'0',False):raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
        url=body.get('url')
        if not url:raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
        try:
            if not isinstance(url,str):raise ValueError()
            if urlsplit(url).path.lower().endswith(('.m3u8','.mpd')):raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
            media=ResolvedMedia(id=uuid4().hex,identity=identity,resolvedAt=int(time()*1000),validUntil=None,
                upstreamUrl=url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://h5.nf.migu.cn/'},
                representation=MediaRepresentation(providerQualityId=actual_format))
            return await qualify(self.client,media,quality)
        except (ValueError,ValidationError):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None
