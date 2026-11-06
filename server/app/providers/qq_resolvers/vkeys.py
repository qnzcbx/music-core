"""vkeys单档位请求，URL-only保留请求绑定等级。"""
import httpx
from . import check_mid,request_json,result


async def resolve(client,mid,quality=14):
    check_mid(mid)
    if type(quality)is not int or quality not in (4,8,10,11,14):raise ValueError('品质参数无效')
    data=await request_json(client,httpx.Request('GET','https://api.vkeys.cn/music/tencent/song/link',
        params={'mid':mid,'quality':quality},headers={'User-Agent':'Mozilla/5.0'}))
    return result('vkeys',mid,data.get('data'))
