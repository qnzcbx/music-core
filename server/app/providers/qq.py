"""QQ平台RPC的独立异步适配；不使用第三方解析或伪造账号身份。"""
import asyncio
import json
import math
import re
from http.cookies import SimpleCookie
from secrets import randbelow
from time import time
from urllib.parse import urljoin,urlsplit
from uuid import uuid4
import httpx
from pydantic import ValidationError
from app.models import TrackIdentity,SongCandidate,SearchPage,ResolveOptions,ResolvedMedia,MediaRepresentation
from app.core.errors import CoreError,ErrorCode

ENDPOINT='https://u.y.qq.com/cgi-bin/musicu.fcg'
SEARCH_URL='https://c.y.qq.com/soso/fcgi-bin/client_search_cp'
VKEY_MODULE='music.vkey.GetVkey'


def candidate_from(raw: dict) -> SongCandidate | None:
    mid=raw.get('mid') or raw.get('songmid')
    title=raw.get('title') or raw.get('songname') or raw.get('name')
    if not isinstance(mid,str) or not isinstance(title,str):return None
    album=raw.get('album') if isinstance(raw.get('album'),dict) else {}
    singers=raw.get('singer') if isinstance(raw.get('singer'),list) else []
    cover=None
    # 图片路径只在存在平台给出的专辑mid时构造，不从歌曲ID猜测封面。
    album_mid=album.get('mid') or raw.get('albummid')
    if isinstance(album_mid,str) and re.fullmatch(r'[A-Za-z0-9]{1,64}',album_mid):
        cover=f'https://y.gtimg.cn/music/photo_new/T002R500x500M000{album_mid}.jpg'
    duration=raw.get('interval')
    if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not math.isfinite(duration) or duration<0:duration=None
    try:
        return SongCandidate(identity=TrackIdentity(providerId='qq',platformId=mid),title=title,
            artists=tuple(s['name'] for s in singers if isinstance(s,dict) and isinstance(s.get('name'),str) and s['name']),
            album=album.get('title') or album.get('name') or raw.get('albumname') or None,
            durationSeconds=duration,cover=cover)
    except ValidationError:return None


class QQProvider:
    id='qq'

    def __init__(self,client: httpx.AsyncClient,*,cookie='',route_order=('official',),resolve_timeout=25,continue_on_transient=True,enabled_external_routes=(),development_preview=False):
        if not isinstance(route_order,(list,tuple)) or not route_order or any(r not in ('official','vkeys','qqovo','tang') for r in route_order) or len(set(route_order))!=len(route_order):raise ValueError('QQ resolver order invalid')
        if type(resolve_timeout) not in (int,float) or not math.isfinite(resolve_timeout) or not 0<resolve_timeout<=60:raise ValueError('QQ resolve timeout invalid')
        if type(continue_on_transient)is not bool:raise ValueError('QQ continuation policy invalid')
        if not isinstance(enabled_external_routes,(tuple,list)) or any(r not in ('vkeys','qqovo','tang') for r in enabled_external_routes):raise ValueError('External route selection invalid')
        if enabled_external_routes:self.available_routes=('official',*enabled_external_routes)
        if type(development_preview)is not bool:raise ValueError('Development preview invalid')
        self.development_preview=development_preview
        self.last_resolution=None
        if development_preview:self.available_routes=('official','vkeys','tang')
        self.route_order=tuple(route_order)
        self.resolve_timeout=resolve_timeout
        self.continue_on_transient=continue_on_transient
        self.client=client
        self._cookie=cookie
        parsed=SimpleCookie()
        try:parsed.load(cookie)
        except Exception:raise CoreError(ErrorCode.INVALID_INPUT) from None
        self._uin=next((parsed[k].value for k in ('musicid','uin') if k in parsed and parsed[k].value.isdigit()),'0')
        self._key=next((parsed[k].value for k in ('musickey','qqmusic_key') if k in parsed),'')

    async def rpc(self,module: str,method: str,param: dict) -> dict:
        comm={'ct':24,'cv':0,'format':'json','uin':self._uin}
        if self._key:comm.update({'qq':self._uin,'authst':self._key,'tmeLoginType':'2'})
        payload={'comm':comm,'req_0':{'module':module,'method':method,'param':param}}
        headers={'User-Agent':'Mozilla/5.0','Referer':'https://y.qq.com/','Accept':'application/json'}
        if self._cookie:headers['Cookie']=self._cookie
        # 匿名web使用GET data；登录上下文只进POST正文，绝不进入URL。
        request=httpx.Request('POST',ENDPOINT,json=payload,headers=headers) if self._cookie else httpx.Request(
            'GET',ENDPOINT,params={'data':json.dumps(payload,separators=(',',':'),ensure_ascii=False)},headers=headers)
        data=await self.request_json(request)
        result=data.get('req_0')
        if not isinstance(result,dict):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        if result.get('code') in (401,403):raise CoreError(ErrorCode.ACCESS_DENIED)
        if result.get('code') in (1000,104009):
            error=CoreError(ErrorCode.PROVIDER_CONTEXT_REJECTED)
            error.platform_code=result['code']
            raise error
        if result.get('code')!=0:raise CoreError(ErrorCode.UPSTREAM_FAILURE)
        if not isinstance(result.get('data'),dict):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        return result['data']

    async def request_json(self,request: httpx.Request) -> dict:
        async def execute():
            response=None
            try:
                response=await self.client.send(request,stream=True,follow_redirects=False)
                if response.status_code in (401,403):raise CoreError(ErrorCode.ACCESS_DENIED)
                if response.status_code!=200:raise CoreError(ErrorCode.UPSTREAM_FAILURE)
                body=bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body)>2*1024*1024:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                try:data=json.loads(body)
                except (ValueError,UnicodeError):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None
                if not isinstance(data,dict):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                if data.get('code') in (401,403):raise CoreError(ErrorCode.ACCESS_DENIED)
                if data.get('code') not in (0,None):raise CoreError(ErrorCode.UPSTREAM_FAILURE)
                return data
            finally:
                if response is not None:await response.aclose()
        try:return await asyncio.wait_for(execute(),20)
        except (httpx.TimeoutException,asyncio.TimeoutError):raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None
        except httpx.HTTPError:raise CoreError(ErrorCode.UPSTREAM_FAILURE) from None

    async def search(self,query: str,limit: int,cursor: str | None = None) -> SearchPage:
        if not isinstance(query,str) or not 1<=len(query.strip())<=80 or type(limit)is not int or not 1<=limit<=10:
            raise CoreError(ErrorCode.INVALID_INPUT)
        page=1
        if cursor is not None:
            if not isinstance(cursor,str) or not re.fullmatch(r'([2-9]|10):([1-9]|10)',cursor):raise CoreError(ErrorCode.INVALID_INPUT)
            page,old_limit=map(int,cursor.split(':'))
            if old_limit!=limit:raise CoreError(ErrorCode.INVALID_INPUT)
        headers={'User-Agent':'Mozilla/5.0','Referer':'https://y.qq.com/'}
        if self._cookie:headers['Cookie']=self._cookie
        # 已实测的QQ自身搜索接口，不在空结果时无限切换其他服务。
        data=await self.request_json(httpx.Request('GET',SEARCH_URL,headers=headers,params={
            'w':query.strip(),'p':page,'n':limit,'format':'json','t':0,'platform':'yqq.json','new_json':1}))
        body=data.get('data')
        song=body.get('song') if isinstance(body,dict) else None
        rows=song.get('list') if isinstance(song,dict) else None
        if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        items=[];seen=set()
        for row in rows[:limit]:
            candidate=candidate_from(row)
            if candidate and candidate.identity.key not in seen:items.append(candidate);seen.add(candidate.identity.key)
        total=song.get('totalnum')
        more=bool(rows) and page<10 and (not isinstance(total,int) or page*limit<total)
        return SearchPage(items=tuple(items),nextCursor=f'{page+1}:{limit}' if more else None)

    # 默认只启用官方；外部资格需由调用方核实服务条件，顺序配置不能自行解禁。
    available_routes=('official',)

    async def resolve(self,identity: TrackIdentity,options: ResolveOptions | None = None) -> ResolvedMedia:
        self.last_resolution=None
        if identity.providerId!='qq':raise CoreError(ErrorCode.UNSUPPORTED_PROVIDER)
        options=options or ResolveOptions()
        if options.providerQualityId is not None:raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
        async def execute():
            failure=None
            for route in self.route_order:
                if route not in self.available_routes:continue
                try:
                    result=await self._resolve_route(route,identity,options)
                    if result.identity!=identity:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                    if route=='official':self.last_resolution={'resolver':'official','identity':'official_mid_matched','protocol':'success','media':'upstream_unprobed','scope':'normal'}
                    return result
                except CoreError as error:
                    if not self.continue_on_transient or error.code not in (ErrorCode.UPSTREAM_TIMEOUT,ErrorCode.UPSTREAM_FAILURE,ErrorCode.MEDIA_UNAVAILABLE):raise
                    failure=error
            raise failure or CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
        try:return await asyncio.wait_for(execute(),self.resolve_timeout)
        except asyncio.TimeoutError:raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None

    async def _resolve_route(self,route,identity,options):
        if route=='official':return await self._resolve_official(identity)
        from .qq_resolvers import vkeys,qqovo,tang
        adapter={'vkeys':vkeys,'qqovo':qqovo,'tang':tang}[route]
        result=await adapter.resolve(self.client,identity.platformId)
        if result.response_mid is None and not self.development_preview:raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
        if result.response_mid is not None and result.response_mid!=identity.platformId:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        from .qq_resolvers.media import verify_media
        representation=await verify_media(self.client,result.url.get_secret_value())
        self.last_resolution={'resolver':route,'identity':result.evidence,'protocol':'success','media':'prefix_verified',
            'scope':'development_preview' if self.development_preview else 'normal'}
        return ResolvedMedia(id=uuid4().hex,identity=identity,resolvedAt=int(time()*1000),validUntil=None,
            upstreamUrl=result.url,headers={'User-Agent':'Mozilla/5.0'},representation=representation)

    async def _resolve_official(self,identity: TrackIdentity) -> ResolvedMedia:
        # 不构造猜测文件名，让平台按songmid选择当前允许访问的普通媒体表示。
        data=await self.rpc(VKEY_MODULE,'UrlGetVkey',{'songmid':[identity.platformId],'songtype':[0],
            'guid':str(randbelow(9_000_000_000)+1_000_000_000),'uin':self._uin,'loginflag':1 if self._key else 0,'platform':'20'})
        rows=data.get('midurlinfo')
        if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        row=rows[0]
        if row.get('songmid')!=identity.platformId:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        if row.get('result') in (401,403):raise CoreError(ErrorCode.ACCESS_DENIED)
        purl=row.get('purl') or row.get('wifiurl')
        if not purl:raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
        sip=data.get('sip')
        base=next((s for s in sip if isinstance(s,str) and s.startswith(('http://','https://'))),None) if isinstance(sip,list) else None
        if not isinstance(purl,str) or (not base and not purl.startswith(('http://','https://'))):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        url=urljoin(base or '',purl)
        try:
            parsed=urlsplit(url)
            if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError()
            if parsed.path.lower().endswith(('.m3u8','.mgg','.mflac')):raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
            return ResolvedMedia(id=uuid4().hex,identity=identity,representation=MediaRepresentation(),
                resolvedAt=int(time()*1000),validUntil=None,upstreamUrl=url,
                headers={'User-Agent':'Mozilla/5.0','Referer':'https://y.qq.com/'})
        except (ValueError,ValidationError):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None
