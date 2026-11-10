"""QQ平台响应为人工脱敏样本，所有请求由MockTransport处理。"""
import asyncio
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.models import TrackIdentity,ResolveOptions
from app.providers.qq import QQProvider,candidate_from
from app.core.errors import CoreError,ErrorCode
from app.media_stream import validate_target

ROW={'mid':'SongMid1','id':987,'title':'测试歌','singer':[{'name':'甲'},{'name':'乙'}],
     'album':{'mid':'AlbumMid','title':'测试专辑'},'file':{'media_mid':'DifferentFileMid'},'interval':120}
TRACK=TrackIdentity(providerId='qq',platformId='SongMid1')


def response(data,code=0):return httpx.Response(200,json={'code':0,'req_0':{'code':code,'data':data}})
def search_response(rows,total=0):return httpx.Response(200,json={'code':0,'data':{'song':{'list':rows,'totalnum':total}}})
def run(call,handler,cookie=''):
    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await call(QQProvider(client,cookie=cookie))
    return asyncio.run(execute())


def test_search_mapping_and_identity():
    def handler(r):
        assert r.url.params['w']=='测试' and r.url.params['n']=='2'
        assert r.url.host=='c.y.qq.com'
        return search_response([ROW,ROW],3)
    page=run(lambda p:p.search('测试',2),handler)
    assert len(page.items)==1 and page.nextCursor=='2:2'
    song=page.items[0];assert song.identity.platformId=='SongMid1' and song.artists==('甲','乙')
    assert song.album=='测试专辑' and song.durationSeconds==120
    assert 'DifferentFileMid' not in song.model_dump_json() and 'playable' not in song.model_dump()


def test_empty_missing_and_multiple_ids():
    assert candidate_from({'id':123,'title':'歌'}) is None
    assert candidate_from({**ROW,'mid':'非法身份'}) is None
    song=candidate_from({'songmid':'Abc','songid':77,'title':'歌'})
    assert song.identity.platformId=='Abc' and song.cover is None and song.durationSeconds is None and song.album is None
    assert not run(lambda p:p.search('空',1),lambda r:search_response([])).items


@pytest.mark.parametrize('cursor',['bad','2:1','11:2'])
def test_bad_cursor(cursor):
    with pytest.raises(CoreError):run(lambda p:p.search('歌',2,cursor),lambda r:pytest.fail('不应请求'))


@pytest.mark.parametrize('query,limit',[('',1),(' '*2,1),('x'*81,1),('歌',16),('歌',True)])
def test_bad_input(query,limit):
    with pytest.raises(CoreError):run(lambda p:p.search(query,limit),lambda r:pytest.fail('不应请求'))


@pytest.mark.parametrize('data',[{}, {'body':{'item_song':{}}},{'body':{'item_song':[1]}}])
def test_bad_search_structure(data):
    with pytest.raises(CoreError) as e:run(lambda p:p.search('歌',1),lambda r:httpx.Response(200,json=data))
    assert e.value.code==ErrorCode.UPSTREAM_INVALID_RESPONSE


@pytest.mark.parametrize('status,code',[(403,ErrorCode.ACCESS_DENIED),(500,ErrorCode.UPSTREAM_FAILURE)])
def test_http_errors(status,code):
    with pytest.raises(CoreError) as e:run(lambda p:p.search('歌',1),lambda r:httpx.Response(status))
    assert e.value.code==code


@pytest.mark.parametrize('code,expected',[(403,ErrorCode.ACCESS_DENIED),(-1,ErrorCode.UPSTREAM_FAILURE),(1000,ErrorCode.PROVIDER_CONTEXT_REJECTED)])
def test_business_errors(code,expected):
    with pytest.raises(CoreError) as e:run(lambda p:p.resolve(TRACK),lambda r:response({},code))
    assert e.value.code==expected


def test_timeout_and_cancel_no_retry():
    calls=[]
    def timeout(r):calls.append(r);raise httpx.ReadTimeout('不得回显')
    with pytest.raises(CoreError) as e:run(lambda p:p.resolve(TRACK),timeout)
    assert e.value.code==ErrorCode.UPSTREAM_TIMEOUT and len(calls)==1
    async def cancelled():
        event=asyncio.Event();calls=[]
        async def handler(r):calls.append(r);event.set();await asyncio.Event().wait()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            task=asyncio.create_task(QQProvider(client).resolve(TRACK));await event.wait();task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            assert len(calls)==1
    asyncio.run(cancelled())


@pytest.mark.parametrize('purpose',['playback','download'])
def test_resolve_mid_purl_and_privacy(purpose):
    def handler(r):
        payload=json.loads(r.url.params['data']);param=payload['req_0']['param']
        assert param['songmid']==['SongMid1'] and 'filename' not in param and param['loginflag']==0
        return response({'midurlinfo':[{'songmid':'SongMid1','purl':'C400file.m4a'}],
            'sip':['https://isure.stream.qqmusic.qq.com/']})
    media=run(lambda p:p.resolve(TRACK,ResolveOptions(purpose=purpose)),handler)
    assert media.identity==TRACK and media.representation.codec is None and media.representation.sizeBytes is None
    assert media.validUntil is None and 'qqmusic.qq.com' not in media.public_view().model_dump_json()+repr(media)


@pytest.mark.parametrize('row,sip,expected',[
    ({'songmid':'SongMid1','purl':''},[],ErrorCode.MEDIA_UNAVAILABLE),
    ({'songmid':'Wrong','purl':'x'},[],ErrorCode.UPSTREAM_INVALID_RESPONSE),
    ({'songmid':'SongMid1','purl':'x'},[],ErrorCode.UPSTREAM_INVALID_RESPONSE),
    ({'songmid':'SongMid1','result':403},[],ErrorCode.ACCESS_DENIED),
    ({'songmid':'SongMid1','purl':'x.mflac'},['https://isure.stream.qqmusic.qq.com/'],ErrorCode.CAPABILITY_UNSUPPORTED)])
def test_resolve_errors(row,sip,expected):
    with pytest.raises(CoreError) as e:run(lambda p:p.resolve(TRACK),lambda r:response({'midurlinfo':[row],'sip':sip}))
    assert e.value.code==expected


def test_credentials_only_qq_rpc_not_media():
    def handler(r):
        assert r.method=='POST' and 'data' not in r.url.params
        assert r.headers['cookie']=='uin=123; qqmusic_key=synthetic-private'
        payload=json.loads(r.content);assert payload['comm']['authst']=='synthetic-private'
        return response({'midurlinfo':[{'songmid':'SongMid1','purl':'https://isure.stream.qqmusic.qq.com/a.m4a'}]})
    media=run(lambda p:p.resolve(TRACK),handler,'uin=123; qqmusic_key=synthetic-private')
    assert 'Cookie' not in media.headers and 'synthetic-private' not in media.model_dump_json()


def test_wrong_provider_and_selection():
    for track,options in [(TrackIdentity(providerId='kuwo',platformId='1'),None),(TRACK,ResolveOptions(providerQualityId='unsupported'))]:
        with pytest.raises(CoreError):run(lambda p:p.resolve(track,options),lambda r:pytest.fail('不应请求'))


def test_qq_open_lease_isolated_from_kuwo():
    async def allow(url):pass
    def handler(r):
        if r.url.host=='u.y.qq.com':return response({'midurlinfo':[{'songmid':'SongMid1','purl':'x.m4a'}], 'sip':['https://isure.stream.qqmusic.qq.com/']})
        return httpx.Response(200,headers={'content-type':'audio/mp4','content-length':'0'},stream=httpx.ByteStream(b''))
    app=create_app(transport=httpx.MockTransport(handler),target_check=allow)
    with TestClient(app) as c:
        qq=c.post('/api/playback/open',json={'identity':TRACK.model_dump()})
        assert qq.status_code==200 and 'qqmusic.qq.com' not in qq.text
        from test_media_lifecycle import media
        kuwo=app.state.media_store.put(media());kw=app.state.playback_leases.create(kuwo.id)
        c.post(f"/api/playback/{qq.json()['playbackId']}/close")
        assert app.state.playback_leases.use(kw).identity.providerId=='kuwo'
        assert c.head(qq.json()['streamUrl']).status_code==410
        assert TrackIdentity(providerId='qq',platformId='1').key!=kuwo.identity.key


@pytest.mark.parametrize('url,provider',[('https://evil.qq.com/audio','qq'),('https://media.kuwo.cn/audio','qq'),
    ('https://isure.stream.qqmusic.qq.com/audio','kuwo'),('http://127.0.0.1/','qq')])
def test_cross_provider_target_denied(url,provider):
    with pytest.raises(CoreError):asyncio.run(validate_target(url,provider))


def test_qq_media_domain_with_public_dns(monkeypatch):
    async def execute():
        async def dns(*args,**kwargs):return [(None,None,None,None,('8.8.8.8',443))]
        monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',dns)
        await validate_target('https://aqqmusic.tc.qq.com/a','qq')
        await validate_target('https://isure.stream.qqmusic.qq.com/a','qq')
    asyncio.run(execute())


def test_shared_client_never_sends_qq_cookie_to_kuwo():
    from app.providers.kuwo import KuwoProvider
    def handler(r):
        if r.url.host=='c.y.qq.com':
            assert r.headers['cookie']=='uin=123; qqmusic_key=synthetic-private'
            return httpx.Response(200,json={'code':0,'data':{'song':{'list':[ROW],'totalnum':1}}},
                headers={'set-cookie':'qq_context=synthetic-private; Domain=.qq.com; Path=/'})
        assert r.url.host=='www.kuwo.cn' and 'cookie' not in r.headers
        return httpx.Response(200,json={'abslist':[],'TOTAL':'0'})
    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await QQProvider(client,cookie='uin=123; qqmusic_key=synthetic-private').search('歌',1)
            await KuwoProvider(client).search('歌',1)
    asyncio.run(execute())
