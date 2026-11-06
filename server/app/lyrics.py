"""歌词标准化和有界缓存；与媒体、租约和下载完全独立。"""
import asyncio
import base64
from collections import OrderedDict
from decimal import Decimal
import json
import ipaddress
import socket
import re
from time import monotonic
from typing import Literal
from urllib.parse import urlsplit
import httpx
from fastapi import APIRouter, Request
from app.models import DTO, TrackIdentity
from app.core.errors import CoreError, ErrorCode
from app.providers import provider_for


class LyricLine(DTO):
    startMs: int
    endMs: int | None = None
    text: str
    translation: str | None = None
    romanization: str | None = None


class LyricDocument(DTO):
    identity: TrackIdentity
    status: Literal['synced','plain','instrumental','unavailable']
    lines: tuple[LyricLine,...] = ()
    plainText: str | None = None
    sourceFormat: str | None = None
    unalignedTranslation: str | None = None


def parse_lrc(raw):
    if not isinstance(raw,str) or len(raw.encode('utf8'))>1024*1024:
        raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    offset=re.findall(r'\[offset:([+-]?\d{1,9})\]',raw,re.I)
    offset=int(offset[-1]) if offset else 0
    entries=[];plain=[]
    for row in raw.lstrip('\ufeff').splitlines():
        stamps=re.findall(r'\[(\d{1,4}):([0-5]\d)(?:\.(\d{1,6}))?\]',row)
        text=re.sub(r'\[[^\]]*\]','',row).strip()
        if stamps:
            for minute,second,fraction in stamps:
                ms=int(minute)*60000+int(second)*1000+int(Decimal('0.'+(fraction or '0'))*1000)
                entries.append((max(0,ms+offset),text))
        elif text:plain.append(text)
        if len(entries)>10000 or len(plain)>10000:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    # 同时刻内容合并，保留空行；结束边界只取下一个不同时间点。
    grouped={}
    for ms,text in sorted(entries):
        if text not in grouped.setdefault(ms,[]):grouped[ms].append(text)
    times=list(grouped)
    return tuple(LyricLine(startMs=ms,endMs=times[i+1] if i+1<len(times) else None,
        text='\n'.join(grouped[ms])) for i,ms in enumerate(times)), '\n'.join(plain) or None


def document(identity, raw='', translation='', instrumental=False):
    lines,plain=parse_lrc(raw)
    translated,_=parse_lrc(translation)
    used=set();merged=[]
    for line in lines:
        near=[(abs(t.startMs-line.startMs),i,t) for i,t in enumerate(translated) if i not in used and abs(t.startMs-line.startMs)<=20]
        near.sort(key=lambda v:v[0])
        if near and (len(near)==1 or near[0][0]<near[1][0]):
            _,i,t=near[0];used.add(i);line=line.model_copy(update={'translation':t.text})
        merged.append(line)
    return LyricDocument(identity=identity,status='synced' if lines else 'plain' if plain else 'instrumental' if instrumental else 'unavailable',
        lines=tuple(merged),plainText=plain,sourceFormat='lrc' if lines else 'text' if plain else None,
        unalignedTranslation=translation if translation and (not translated or len(used)!=len(translated)) else None)


async def fetch(client,url,*,params=None,data=None,text=False,headers=None):
    response=None
    try:
        request=httpx.Request('POST' if data is not None else 'GET',url,params=params,data=data,
            headers={'User-Agent':'Mozilla/5.0',**(headers or {})})
        response=await client.send(request,stream=True,follow_redirects=False,auth=None)
        if response.status_code in (401,403):raise CoreError(ErrorCode.ACCESS_DENIED)
        if response.status_code==404:raise CoreError(ErrorCode.TRACK_NOT_FOUND)
        if response.status_code!=200:raise CoreError(ErrorCode.UPSTREAM_FAILURE)
        body=bytearray()
        async for chunk in response.aiter_bytes(chunk_size=16384):
            body.extend(chunk)
            if len(body)>1024*1024:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        value=body.decode('utf-8-sig')
        if text:return value
        value=json.loads(value)
        if not isinstance(value,dict):raise ValueError()
        if value.get('code') in (401,403,301):raise CoreError(ErrorCode.ACCESS_DENIED)
        if value.get('code') not in (None,0,200,'000000'):raise CoreError(ErrorCode.UPSTREAM_FAILURE)
        return value
    except httpx.TimeoutException:raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None
    except httpx.HTTPError:raise CoreError(ErrorCode.UPSTREAM_FAILURE) from None
    except (ValueError,UnicodeError,KeyError,TypeError):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None
    finally:
        if response is not None:await response.aclose()


async def provider_lyrics(provider,identity):
    if identity.providerId!=provider.id:raise CoreError(ErrorCode.UNSUPPORTED_PROVIDER)
    async def execute():
        c=provider.client;pid=identity.platformId
        if provider.id=='netease':
            value=await fetch(c,'https://interface3.music.163.com/api/song/lyric',data={'id':pid,'lv':'0','tv':'0','rv':'0','cp':'false','kv':'0','yv':'0','ytv':'0','yrv':'0'})
            if not any(k in value for k in ('lrc','nolyric','uncollected')):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            return document(identity,value.get('lrc',{}).get('lyric',''),value.get('tlyric',{}).get('lyric',''),value.get('nolyric') is True)
        if provider.id=='qq':
            value=await fetch(c,'https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg',params={'songmid':pid,'g_tk':'5381','loginUin':'0','hostUin':'0','format':'json','inCharset':'utf8','outCharset':'utf-8','platform':'yqq'},headers={'Referer':'https://y.qq.com/portal/player.html'})
            if 'lyric' not in value:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            def decode(v):return base64.b64decode(v,validate=True).decode('utf8') if v else ''
            return document(identity,decode(value['lyric']),decode(value.get('trans','')))
        if provider.id=='kuwo':
            value=await fetch(c,'https://m.kuwo.cn/newh5/singles/songinfoandlrc',params={'musicId':pid,'reqId':'','plat':'web','from':''},headers={'Referer':'https://m.kuwo.cn/'})
            if value.get('status') not in (None,200):raise CoreError(ErrorCode.UPSTREAM_FAILURE)
            rows=value.get('data',{}).get('lrclist')
            if not isinstance(rows,list):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            parts=[]
            for row in rows:
                seconds=Decimal(str(row['time']))
                if not seconds.is_finite() or seconds<0:raise ValueError()
                ms=int(seconds*1000);parts.append(f'[{ms//60000:02d}:{ms//1000%60:02d}.{ms%1000:03d}]'+row['lineLyric'])
            return document(identity,'\n'.join(parts))
        from app.providers.migu import DETAIL_URL
        detail=await provider.request_json(DETAIL_URL,{'resourceId':pid,'resourceType':'2'})
        rows=detail.get('resource')
        if not isinstance(rows,list) or len(rows)!=1 or str(rows[0].get('contentId'))!=pid:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        copyright=rows[0].get('copyrightId')
        if not copyright:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        url=rows[0].get('lrcUrl')
        if not url:return document(identity)
        # 固定歌词CDN且不跟随跳转，不允许平台响应变成任意URL代理。
        parsed=urlsplit(url)
        if parsed.scheme not in ('https','http') or parsed.hostname!='d.musicapp.migu.cn' or parsed.username or parsed.password or parsed.port not in (None,80,443):raise CoreError(ErrorCode.UNTRUSTED_MEDIA)
        addresses=await asyncio.get_running_loop().getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=='https' else 80),type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):raise CoreError(ErrorCode.UNTRUSTED_MEDIA)
        return document(identity,await fetch(c,url,text=True,headers={'Referer':'https://y.migu.cn/'}))
    try:return await asyncio.wait_for(execute(),12)
    except asyncio.TimeoutError:raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None
    except OSError:raise CoreError(ErrorCode.UPSTREAM_FAILURE) from None
    except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None


class LyricsCache:
    def __init__(self,ttl=600,capacity=128,clock=monotonic):
        self.ttl,self.capacity,self.clock=ttl,capacity,clock
        self.entries=OrderedDict();self.locks={}

    async def get(self,identity,provider):
        key=identity.key
        if key not in self.locks:
            if len(self.locks)>=128:raise CoreError(ErrorCode.MEDIA_CAPACITY)
            self.locks[key]=[asyncio.Lock(),0]
        item=self.locks[key];item[1]+=1
        try:
            async with item[0]:
                now=self.clock()
                for k,(expiry,_) in list(self.entries.items()):
                    if expiry<=now:self.entries.pop(k)
                if key in self.entries:return self.entries[key][1]
                value=await provider.get_lyrics(identity)
                if value.identity!=identity:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                self.entries[key]=(self.clock()+self.ttl,value)
                while len(self.entries)>self.capacity:self.entries.popitem(last=False)
                return value
        finally:
            item[1]-=1
            if not item[1]:self.locks.pop(key,None)


def lyrics_router():
    router=APIRouter()
    @router.get('/api/lyrics',response_model=LyricDocument)
    async def lyrics(request: Request,providerId: str,platformId: str):
        try:identity=TrackIdentity(providerId=providerId,platformId=platformId)
        except ValueError:raise CoreError(ErrorCode.INVALID_INPUT) from None
        return await request.app.state.lyrics_cache.get(identity,provider_for(request.app.state,providerId))
    return router
