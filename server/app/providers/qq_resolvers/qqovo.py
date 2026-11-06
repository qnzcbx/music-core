"""qqovo短生命周期会话，签名材料只在本次调用中存在。"""
import base64
import hashlib
import hmac
import json
from time import time
from uuid import uuid4
from urllib.parse import urlsplit,parse_qsl
import httpx
from app.core.errors import CoreError,ErrorCode
from . import check_mid,request_json,result


def sign(url,key,timestamp,nonce):
    parsed=urlsplit(url)
    query='&'.join(f'{k}={v}' for k,v in sorted(parse_qsl(parsed.query,keep_blank_values=True)))
    payload='\n'.join(['GET',parsed.path,query,'',timestamp,nonce])
    return base64.urlsafe_b64encode(hmac.new(key.encode(),payload.encode(),hashlib.sha256).digest()).decode().rstrip('=')


async def resolve(client,mid,*,session_factory=httpx.AsyncClient):
    check_mid(mid)
    # 独立短会话不把服务Cookie留在共享平台连接池；退出或取消即关闭。
    async with session_factory(timeout=httpx.Timeout(10,connect=5),follow_redirects=False) as session:
        headers={'User-Agent':'Mozilla/5.0','Origin':'https://qqovo.top','Referer':'https://qqovo.top/room/4SVWQK'}
        bootstrap=await request_json(session,httpx.Request('POST','https://qqovo.top/api/session/bootstrap',
            headers={**headers,'Content-Type':'application/json'},content=json.dumps({'deviceId':str(uuid4())},separators=(',',':'))))
        key=bootstrap.get('apiSignKey')
        if not isinstance(key,str) or not key:raise CoreError(ErrorCode.PROVIDER_CONTEXT_REJECTED)
        request=httpx.Request('GET','https://qqovo.top/api/meting',headers=headers,
            params={'server':'tencent','type':'url','id':mid,'quality':'lossless'})
        timestamp=str(int(time()));nonce=str(uuid4())
        request.headers.update({'X-OM-Ts':timestamp,'X-OM-Nonce':nonce,'X-OM-Sign':sign(str(request.url),key,timestamp,nonce)})
        session.cookies.set_cookie_header(request)
        return result('qqovo',mid,await request_json(session,request))
