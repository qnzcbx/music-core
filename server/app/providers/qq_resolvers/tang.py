"""Tang 只读取正选媒体字段，使用 MID 和已有元数据核对身份。"""
import httpx
from app.core.errors import CoreError,ErrorCode
from . import check_mid,request_json,result


async def resolve(client,mid,*,expected_title=None,expected_artist=None):
    check_mid(mid)
    data=await request_json(client,httpx.Request('GET','https://tang.api.s01s.cn/music_open_api.php',
        params={'mid':mid},headers={'User-Agent':'Mozilla/5.0'}))
    if data.get('song_mid')!=mid:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    if not isinstance(data.get('song_name'),str) or not isinstance(data.get('singer_name'),str):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    if not data['song_name'].strip() or not data['singer_name'].strip():raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    for expected,actual in ((expected_title,data['song_name']),(expected_artist,data['singer_name'])):
        if expected is not None and ' '.join(expected.split()).casefold()!=' '.join(actual.split()).casefold():
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    url=next((data[k] for k in ('song_play_url_sq','song_play_url_pq','song_play_url_hq','song_play_url','song_play_url_standard','song_play_url_fq') if data.get(k)),None)
    return result('tang',mid,{**data,'url':url})
