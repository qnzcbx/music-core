"""巡回寺公开匿名接口；链接回显不冒充独立MID字段。"""
import re
from urllib.parse import urlsplit
import httpx
from app.core.errors import CoreError,ErrorCode
from . import check_mid,request_json,result


async def resolve(client,mid):
    check_mid(mid)
    data=await request_json(client,httpx.Request('GET','https://api.xunhuisi.store/API/QQMusic/Song.php',
        params={'mid':mid,'type':'json'},headers={'User-Agent':'Mozilla/5.0'}))
    title,artist=data.get('title'),data.get('singer')
    if not isinstance(title,str) or not title.strip() or not isinstance(artist,str) or not artist.strip():
        raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    if any(word in title.casefold() for word in ('伴奏','翻唱','伴唱','live')):
        raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    link=data.get('link')
    if link is not None:
        if not isinstance(link,str):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        parsed=urlsplit(link)
        matched=re.fullmatch(r'/n/ryqq/songDetail/([A-Za-z0-9]+)',parsed.path)
        if parsed.hostname!='y.qq.com' or not matched or matched[1]!=mid:
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    return result('xunhuisi',mid,{**data,'url':data.get('music_url'),'song_name':title,'singer_name':artist})
