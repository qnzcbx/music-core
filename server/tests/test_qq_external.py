"""外部协议脱敏Fixture，不请求真实服务，不代表在线成功。"""
import asyncio
import httpx
import pytest
from app.providers.qq_resolvers import vkeys,qqovo,tang,result,request_json
from app.providers.qq import QQProvider
from app.models import TrackIdentity
from app.core.errors import CoreError,ErrorCode

MID='ABC'
URL='https://aqqmusic.tc.qq.com/private-audio'

def run(call,handler):
    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),headers={'Authorization':'private'},cookies={'qq':'private'},auth=('private','private')) as client:
            return await call(client)
    return asyncio.run(execute())

def test_vkeys_binding_and_quality():
    def handler(r):
        assert dict(r.url.params)=={'mid':MID,'quality':'14'}
        assert 'cookie' not in r.headers and 'authorization' not in r.headers
        return httpx.Response(200,json={'code':200,'data':{'url':URL}})
    value=run(lambda c:vkeys.resolve(c,MID),handler)
    assert value.evidence=='request_bound' and value.response_mid is None
    assert 'private-audio' not in repr(value)

@pytest.mark.parametrize('body',[{},[],{'data':None},{'data':{}},{'data':{'url':''}},{'data':{'url':'file:///secret'}},{'data':{'url':URL,'mid':'wrong'}}])
def test_vkeys_bad_response(body):
    with pytest.raises(CoreError):run(lambda c:vkeys.resolve(c,MID),lambda r:httpx.Response(200,json=body))

@pytest.mark.parametrize('code',[401,403,500])
def test_business_failure(code):
    with pytest.raises(CoreError):run(lambda c:vkeys.resolve(c,MID),lambda r:httpx.Response(200,json={'code':code}))

def test_signature_vector():
    url='https://qqovo.top/api/meting?type=url&server=tencent&id=ABC&quality=lossless'
    assert qqovo.sign(url,'test-key','1700000000','nonce-1')=='4ohQ-umoxzw5l67JkI5T2gYNAPv6tv8ml25ae8BClmo'
    reordered='https://qqovo.top/api/meting?quality=lossless&id=ABC&server=tencent&type=url'
    assert qqovo.sign(url,'test-key','1700000000','nonce-1')==qqovo.sign(reordered,'test-key','1700000000','nonce-1')
    assert qqovo.sign(url,'test-key','1700000001','nonce-1')!=qqovo.sign(url,'test-key','1700000000','nonce-1')

def test_qqovo_bootstrap_session_signature(monkeypatch):
    calls=[];sessions=[]
    monkeypatch.setattr(qqovo,'time',lambda:1700000000)
    def handler(r):
        calls.append(r)
        assert 'authorization' not in r.headers
        if len(calls)==1:
            assert r.method=='POST' and r.url.path=='/api/session/bootstrap'
            assert 'cookie' not in r.headers
            return httpx.Response(200,json={'apiSignKey':'synthetic'},headers={'set-cookie':'session=synthetic; Path=/; Secure'})
        assert r.headers['cookie']=='session=synthetic'
        assert r.headers['x-om-ts']=='1700000000'
        assert r.headers['x-om-sign']==qqovo.sign(str(r.url),'synthetic',r.headers['x-om-ts'],r.headers['x-om-nonce'])
        return httpx.Response(200,json={'url':URL})
    def factory(**kwargs):
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler),**kwargs);sessions.append(client);return client
    value=asyncio.run(qqovo.resolve(None,MID,session_factory=factory))
    assert value.evidence=='request_bound' and sessions[0].is_closed and len(calls)==2

@pytest.mark.parametrize('body,status',[({},200),({'apiSignKey':''},200),({'code':403},200),({},403)])
def test_qqovo_bad_bootstrap(body,status):
    calls=[]
    def handler(r):calls.append(r);return httpx.Response(status,json=body)
    def factory(**kwargs):return httpx.AsyncClient(transport=httpx.MockTransport(handler),**kwargs)
    with pytest.raises(CoreError):asyncio.run(qqovo.resolve(None,MID,session_factory=factory))
    assert len(calls)==1

@pytest.mark.parametrize('payload,expected',[
    ({'song_mid':MID,'song_name':'原曲','singer_name':'歌手','song_play_url_pq':URL},True),
    ({'song_mid':'wrong','song_name':'原曲','singer_name':'歌手','song_play_url_sq':URL},False),
    ({'song_mid':MID,'song_name':'伴奏','singer_name':'歌手','song_play_url_sq':URL},False),
    ({'song_mid':MID,'song_name':'翻唱版','singer_name':'歌手','song_play_url_sq':URL},False),
    ({'song_mid':MID,'song_name':'原曲','singer_name':'歌手','song_play_url_accom':URL},False),
    ({'song_mid':MID},False),({},False)])
def test_tang_identity_and_fields(payload,expected):
    def handler(r):
        assert dict(r.url.params)=={'mid':MID}
        return httpx.Response(200,json=payload)
    if expected:
        value=run(lambda c:tang.resolve(c,MID),handler)
        assert value.evidence=='confirmed' and value.response_mid==MID
    else:
        with pytest.raises(CoreError):run(lambda c:tang.resolve(c,MID),handler)

def test_tang_never_picks_accompaniment():
    payload={'song_mid':MID,'song_name':'原曲','singer_name':'歌手','song_play_url_accom':'https://wrong/a','song_play_url_hq':URL}
    value=run(lambda c:tang.resolve(c,MID),lambda r:httpx.Response(200,json=payload))
    assert value.url.get_secret_value()==URL

@pytest.mark.parametrize('adapter',[vkeys,tang])
def test_timeout_and_cancellation(adapter):
    def timeout(r):raise httpx.ReadTimeout('private')
    with pytest.raises(CoreError) as error:run(lambda c:adapter.resolve(c,MID),timeout)
    assert error.value.code==ErrorCode.UPSTREAM_TIMEOUT
    async def execute():
        entered=asyncio.Event();closed=[]
        class Waiting(httpx.AsyncByteStream):
            async def __aiter__(self):yield b'{';entered.set();await asyncio.Event().wait()
            async def aclose(self):closed.append(True)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,stream=Waiting()))) as client:
            task=asyncio.create_task(adapter.resolve(client,MID));await entered.wait();task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            assert closed==[True]
    asyncio.run(execute())

def test_qqovo_cancellation_no_second_request():
    async def execute():
        entered=asyncio.Event();calls=[];sessions=[]
        async def handler(r):calls.append(r);entered.set();await asyncio.Event().wait()
        def factory(**kwargs):
            c=httpx.AsyncClient(transport=httpx.MockTransport(handler),**kwargs);sessions.append(c);return c
        task=asyncio.create_task(qqovo.resolve(None,MID,session_factory=factory));await entered.wait();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert len(calls)==1 and sessions[0].is_closed
    asyncio.run(execute())

def test_enabled_dispatch_request_bound_never_published(monkeypatch):
    calls=[]
    async def fake(client,mid):calls.append(mid);return result('vkeys',mid,{'url':URL})
    monkeypatch.setattr(vkeys,'resolve',fake)
    p=QQProvider(None,route_order=('vkeys',),enabled_external_routes=('vkeys',))
    with pytest.raises(CoreError) as error:asyncio.run(p.resolve(TrackIdentity(providerId='qq',platformId=MID)))
    assert error.value.code==ErrorCode.MEDIA_UNAVAILABLE and calls==[MID]

def test_enabled_confirmed_dispatch_and_probe(monkeypatch):
    from app.providers.qq_resolvers import media
    calls=[]
    async def fake(client,mid):return result('tang',mid,{'url':URL,'mid':mid,'song_name':'歌','singer_name':'歌手'})
    async def verify(client,url):
        calls.append(url)
        from app.models import MediaRepresentation
        return MediaRepresentation()
    monkeypatch.setattr(tang,'resolve',fake);monkeypatch.setattr(media,'verify_media',verify)
    identity=TrackIdentity(providerId='qq',platformId=MID)
    p=QQProvider(None,route_order=('tang',),enabled_external_routes=('tang',))
    value=asyncio.run(p.resolve(identity))
    assert value.identity==identity and calls==[URL] and 'private-audio' not in value.model_dump_json()

def test_tang_version_mismatch():
    payload={'song_mid':MID,'song_name':'原曲 Live','singer_name':'歌手','song_play_url_pq':URL}
    with pytest.raises(CoreError):run(lambda c:tang.resolve(c,MID,expected_title='原曲'),lambda r:httpx.Response(200,json=payload))

def test_qqovo_expired_session_no_retry():
    calls=[];sessions=[]
    def handler(r):
        calls.append(r)
        return httpx.Response(200,json={'apiSignKey':'synthetic'}) if len(calls)==1 else httpx.Response(401)
    def factory(**kwargs):
        c=httpx.AsyncClient(transport=httpx.MockTransport(handler),**kwargs);sessions.append(c);return c
    with pytest.raises(CoreError) as error:asyncio.run(qqovo.resolve(None,MID,session_factory=factory))
    assert error.value.code==ErrorCode.ACCESS_DENIED and len(calls)==2 and sessions[0].is_closed

@pytest.mark.parametrize('status,mime,raw,valid',[(206,'audio/mpeg',b'ID3x',True),
    (200,'audio/flac',b'fLaCxxx',True),(200,'text/html',b'<html>',False),
    (200,'audio/mpeg',b'wrong',False),(403,'audio/mpeg',b'ID3x',False)])
def test_bounded_media_validation(monkeypatch,status,mime,raw,valid):
    from app.core import media_probe as media
    closed=[];targets=[]
    async def guard(url,provider):targets.append(url);assert provider=='qq'
    monkeypatch.setattr(media,'validate_target',guard)
    class Bytes(httpx.AsyncByteStream):
        async def __aiter__(self):yield raw
        async def aclose(self):closed.append(True)
    def handler(r):
        assert r.headers['range']=='bytes=0-4095' and 'cookie' not in r.headers and 'authorization' not in r.headers
        return httpx.Response(status,headers={'content-type':mime,'content-range':f'bytes 0-{len(raw)-1}/{len(raw)}'},stream=Bytes())
    if valid:run(lambda c:media.verify_media(c,URL),handler)
    else:
        with pytest.raises(CoreError):run(lambda c:media.verify_media(c,URL),handler)
    assert closed==[True] and targets==[URL]
