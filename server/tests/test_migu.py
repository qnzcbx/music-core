"""咪咕脱敏人工样本；离线测试不访问真实平台。"""
import asyncio
import json
import httpx
import pytest
from app.providers.migu import MiguProvider,candidate_from,decode_response,MAGIC,RESPONSE_KEY
from app.models import TrackIdentity,ResolveOptions
from app.core.errors import CoreError,ErrorCode
from app.media_stream import validate_target
from app.main import create_app
from fastapi.testclient import TestClient

TRACK=TrackIdentity(providerId='migu',platformId='600123')
ROW={'contentId':'600123','copyrightId':'A123','name':'测试歌','duration':123,
    'singers':[{'name':'甲'},{'name':'乙'}],'albums':[{'name':'专辑'}],
    'imgItems':[{'img':'/cover.jpg'}],'rateFormats':[{'formatType':'PQ','resourceType':'2'}]}


def run(call,handler):
    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),cookies={'private':'secret'},headers={'Authorization':'secret'}) as client:
            return await call(MiguProvider(client))
    return asyncio.run(execute())


def handler(request):
    assert 'cookie' not in request.headers and 'authorization' not in request.headers
    if request.url.path.endswith('search_all.do'):
        assert request.url.params['pageSize']=='2'
        return httpx.Response(200,json={'code':'000000','songResultData':{'result':[ROW,ROW],'totalCount':3}})
    if request.url.path.endswith('resourceinfo.do'):
        assert dict(request.url.params)=={'resourceId':'600123','resourceType':'2'}
        return httpx.Response(200,json={'code':'000000','resource':[ROW]})
    assert request.url.path=='/strategy/listen-url/h5/v2.4'
    assert dict(request.url.params)=={'contentId':'600123','copyrightId':'A123','resourceType':'2',
        'netType':'01','toneFlag':'PQ','scene':'','lowerQualityContentId':'600123'}
    assert request.headers['signature']=='1' and request.headers['birth']=='h5page'
    return httpx.Response(200,json={'code':'000000','data':{'url':'https://media.example/audio.mp3','song':ROW}})


def test_mapping_and_no_resolve():
    calls=[]
    def search(request):calls.append(request);return handler(request)
    page=run(lambda p:p.search('测试',2),search)
    assert len(calls)==1 and len(page.items)==1 and page.nextCursor=='2:2'
    song=page.items[0]
    assert song.identity==TRACK and song.durationSeconds==123 and song.artists==('甲','乙')
    assert song.album=='专辑' and str(song.cover)=='https://d.musicapp.migu.cn/cover.jpg'
    assert 'A123' not in song.model_dump_json()
    assert candidate_from({'contentId':'600124','name':'测试歌'}).identity!=TRACK


@pytest.mark.parametrize('value',[None,True,0,1.5,'A123','01','',10**33])
def test_invalid_content_id(value):assert candidate_from({**ROW,'contentId':value}) is None


def test_optional_metadata():
    song=candidate_from({'contentId':600123,'name':'歌','duration':True})
    assert song.identity==TRACK and song.durationSeconds is None and song.album is None and song.cover is None
    assert not song.artists


@pytest.mark.parametrize('query,limit,cursor',[('',1,None),(' '*2,1,None),('a'*81,1,None),('歌',True,None),('歌',11,None),('歌',2,'2:1'),('歌',2,'11:2'),('歌',2,'invalid')])
def test_invalid_search(query,limit,cursor):
    with pytest.raises(CoreError):run(lambda p:p.search(query,limit,cursor),lambda r:pytest.fail('不应请求'))


def test_empty_and_pagination():
    def page(r):
        assert r.url.params['pageNo']=='2'
        return httpx.Response(200,json={'songResultData':{'result':[],'totalCount':0}})
    assert not run(lambda p:p.search('空',2,'2:2'),page).items


@pytest.mark.parametrize('payload',[{},[],{'songResultData':None},{'songResultData':{'result':{}}},{'songResultData':{'result':[1]}}])
def test_search_structure(payload):
    with pytest.raises(CoreError):run(lambda p:p.search('歌',2),lambda r:httpx.Response(200,json=payload))


def test_encoding_vectors():
    # 固定向量来自明确的字节加减协议，既测明文也测混淆头；不处理音频加密。
    plain=b'{"code":"000000"}'
    encoded=bytes.fromhex('abcd0107be8694d9d7d3808384735a9a6e5c965fcf')
    assert decode_response(plain)=={'code':'000000'}
    assert decode_response(encoded,'1')=={'code':'000000'}
    seed=7
    packet=MAGIC+bytes([seed])+bytes((b-seed+RESPONSE_KEY[i%len(RESPONSE_KEY)])&255 for i,b in enumerate(plain))
    assert decode_response(packet,'1')=={'code':'000000'}
    assert decode_response(packet)==decode_response(plain)
    assert run(lambda p:p.request_json('https://c.musicapp.migu.cn/strategy/listen-url/h5/v2.4',{},listen=True),
        lambda r:httpx.Response(200,content=encoded,headers={'signature':'1'}))=={'code':'000000'}


@pytest.mark.parametrize('raw,signature',[(b'',None),(b'<html>',None),(b'[]',None),(MAGIC,'1'),(b'{}','1')])
def test_invalid_encoding(raw,signature):
    with pytest.raises(CoreError):decode_response(raw,signature)


@pytest.mark.parametrize('purpose',['playback','download'])
def test_resolve_without_search_and_new_provider(purpose):
    first=run(lambda p:p.resolve(TRACK,ResolveOptions(purpose=purpose)),handler)
    second=run(lambda p:p.resolve(TRACK,ResolveOptions(purpose=purpose)),handler)
    assert first.identity==second.identity==TRACK and first.id!=second.id
    assert first.representation.codec is None and first.representation.sizeBytes is None and first.validUntil is None
    assert 'example' not in first.model_dump_json() and 'headers' not in first.model_dump()


@pytest.mark.parametrize('changes,expected',[
    ({'contentId':'600124'},ErrorCode.UPSTREAM_INVALID_RESPONSE),({'copyrightId':None},ErrorCode.UPSTREAM_INVALID_RESPONSE),
    ({'rateFormats':[]},ErrorCode.CAPABILITY_UNSUPPORTED),
    ({'needEncrypt':'1'},ErrorCode.CAPABILITY_UNSUPPORTED),
    ({'rateFormats':[{'formatType':'Z3D','resourceType':'2'}]},ErrorCode.CAPABILITY_UNSUPPORTED)])
def test_detail_rejections(changes,expected):
    with pytest.raises(CoreError) as error:run(lambda p:p.resolve(TRACK),lambda r:httpx.Response(200,json={'resource':[{**ROW,**changes}]}))
    assert error.value.code==expected


@pytest.mark.parametrize('url,song,expected',[
    (None,ROW,ErrorCode.MEDIA_UNAVAILABLE),('',ROW,ErrorCode.MEDIA_UNAVAILABLE),
    ('file:///secret',ROW,ErrorCode.UPSTREAM_INVALID_RESPONSE),('https://user:pass@host/a',ROW,ErrorCode.UPSTREAM_INVALID_RESPONSE),
    ('https://media.example/a.m3u8',ROW,ErrorCode.CAPABILITY_UNSUPPORTED),
    ('https://media.example/a',{**ROW,'contentId':'600124'},ErrorCode.UPSTREAM_INVALID_RESPONSE),
    ('https://media.example/a',{**ROW,'copyrightId':'600123'},ErrorCode.UPSTREAM_INVALID_RESPONSE)])
def test_media_rejections(url,song,expected):
    calls=[]
    def response(r):
        calls.append(r)
        if r.url.path.endswith('resourceinfo.do'):return handler(r)
        return httpx.Response(200,json={'code':'000000','data':{'url':url,'song':song}})
    with pytest.raises(CoreError) as error:run(lambda p:p.resolve(TRACK),response)
    assert error.value.code==expected and len(calls)==2


@pytest.mark.parametrize('status,payload,expected',[(403,{},ErrorCode.ACCESS_DENIED),(404,{},ErrorCode.TRACK_NOT_FOUND),
    (500,{},ErrorCode.UPSTREAM_FAILURE),(200,{'code':'403'},ErrorCode.ACCESS_DENIED),
    (200,{'code':'123456'},ErrorCode.UPSTREAM_FAILURE),(200,{'resource':[]},ErrorCode.TRACK_NOT_FOUND)])
def test_platform_errors(status,payload,expected):
    calls=[]
    def response(r):calls.append(r);return httpx.Response(status,json=payload)
    with pytest.raises(CoreError) as error:run(lambda p:p.resolve(TRACK),response)
    assert error.value.code==expected and len(calls)==1


@pytest.mark.parametrize('options',[ResolveOptions(providerQualityId='unsupported'),ResolveOptions(providerQualityId='SQ')])
def test_unsupported_options(options):
    with pytest.raises(CoreError):run(lambda p:p.resolve(TRACK,options),lambda r:pytest.fail('不应请求'))


@pytest.mark.parametrize('operation',['search','resolve'])
def test_timeout_and_cancel(operation):
    def timeout(r):raise httpx.ReadTimeout('不得泄漏')
    with pytest.raises(CoreError) as error:run(lambda p:p.search('歌',2) if operation=='search' else p.resolve(TRACK),timeout)
    assert error.value.code==ErrorCode.UPSTREAM_TIMEOUT
    async def cancel():
        entered=asyncio.Event();closed=[]
        class Waiting(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'{';entered.set();await asyncio.Event().wait()
            async def aclose(self):closed.append(True)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,stream=Waiting()))) as client:
            provider=MiguProvider(client)
            task=asyncio.create_task(provider.search('歌',2) if operation=='search' else provider.resolve(TRACK))
            await entered.wait();task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            assert closed==[True]
    asyncio.run(cancel())


def test_versions_with_same_name_and_copyright():
    rows=[ROW,{**ROW,'contentId':'600124'}]
    page=run(lambda p:p.search('测试歌',2),lambda r:httpx.Response(200,json={'songResultData':{'result':rows,'totalCount':'2'}}))
    assert len(page.items)==2 and page.nextCursor is None
    assert page.items[0].title==page.items[1].title and page.items[0].identity!=page.items[1].identity


@pytest.mark.parametrize('changes',[
    {'audioFormatType':'Z3D'},{'freeListenType':'1'},{'song':{**ROW,'copyrightId':'other'}}])
def test_unavailable_representation_does_not_fallback(changes):
    calls=[]
    def response(r):
        calls.append(r)
        if r.url.path.endswith('resourceinfo.do'):return handler(r)
        return httpx.Response(200,json={'code':'000000','data':{'url':'https://media.example/a','song':ROW,**changes}})
    with pytest.raises(CoreError):run(lambda p:p.resolve(TRACK),response)
    assert len(calls)==2


@pytest.mark.parametrize('status',[200,206,416])
def test_four_provider_lifecycle_and_range(status):
    from test_media_lifecycle import media
    closed=[]
    class Bytes(httpx.AsyncByteStream):
        async def __aiter__(self):
            if status!=416:yield b'ID3x'
        async def aclose(self):closed.append(True)
    async def allow(url):pass
    def upstream(r):
        if r.url.host=='c.musicapp.migu.cn':return handler(r)
        assert 'authorization' not in r.headers and 'cookie' not in r.headers
        headers={'content-type':'audio/mpeg','content-length':'0' if status==416 else '4'}
        if status==206:headers['content-range']='bytes 0-3/4'
        if status==416:headers['content-range']='bytes */4'
        return httpx.Response(status,headers=headers,stream=Bytes())
    app=create_app(transport=httpx.MockTransport(upstream),target_check=allow)
    with TestClient(app) as client:
        page=client.post('/api/search',json={'providerId':'migu','query':'歌','limit':2})
        assert page.status_code==200 and page.json()['items'][0]['identity']==TRACK.model_dump()
        assert not app.state.media_store.records
        for pid in ('kuwo','qq','netease'):
            class Provider:
                def __init__(self,source):self.source=source
                async def resolve(self,identity,options=None):return media().model_copy(update={'identity':identity})
            setattr(app.state,pid,Provider(pid))
        opened=[]
        for pid in ('kuwo','qq','netease','migu'):
            response=client.post('/api/playback/open',json={'identity':{'providerId':pid,'platformId':'600123'}})
            assert response.status_code==200
            opened.append(response.json())
        assert len({r['media']['id'] for r in opened})==4
        assert len({r['playbackId'] for r in opened})==4
        assert client.get(opened[-1]['streamUrl'],headers={'Range':'bytes=0-3'}).status_code==status
        assert closed==[True]
        client.post(opened[-1]['streamUrl'].replace('/stream','/close'))
        assert client.get(opened[-1]['streamUrl']).status_code==410
        for item in opened[:-1]:
            assert app.state.playback_leases.use(item['playbackId']).identity.providerId!='migu'
        fresh=client.post('/api/playback/open',json={'identity':TRACK.model_dump()}).json()
        assert fresh['playbackId']!=opened[-1]['playbackId']
        for item in [*opened,fresh]:client.post(item['streamUrl'].replace('/stream','/close'))
        store=app.state.media_store;now=store.clock();store.clock=lambda:now+301
        app.state.playback_leases.sweep()
        assert not store.records


@pytest.mark.parametrize('url,provider',[
    ('https://freetyst.nf.migu.cn/a','qq'),('https://freetyst.nf.migu.cn/a','netease'),
    ('https://freetyst.nf.migu.cn/a','kuwo'),('https://x.freetyst.nf.migu.cn/a','migu'),
    ('https://freetyst.nf.migu.cn.evil.test/a','migu'),('https://unknown.nf.migu.cn/a','migu'),
    ('https://c.musicapp.migu.cn/a','migu'),('http://127.0.0.1/a','migu'),
    ('https://freetyst.nf.migu.cn:8443/a','migu')])
def test_target_rejections(url,provider):
    with pytest.raises(CoreError):asyncio.run(validate_target(url,provider))


@pytest.mark.parametrize('address,allowed',[('8.8.8.8',True),('10.0.0.1',False),('::1',False)])
def test_target_dns(monkeypatch,address,allowed):
    async def execute():
        async def dns(*args,**kwargs):return [(None,None,None,None,(address,443))]
        monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',dns)
        if allowed:await validate_target('https://freetyst.nf.migu.cn/a','migu')
        else:
            with pytest.raises(CoreError):await validate_target('https://freetyst.nf.migu.cn/a','migu')
    asyncio.run(execute())


def test_untrusted_redirect_releases_stream():
    async def guard(url):
        if httpx.URL(url).host!='media.example':raise CoreError(ErrorCode.UNTRUSTED_MEDIA)
    def upstream(r):
        if r.url.host=='c.musicapp.migu.cn':return handler(r)
        return httpx.Response(302,headers={'location':'http://127.0.0.1/private'})
    app=create_app(transport=httpx.MockTransport(upstream),target_check=guard)
    with TestClient(app) as client:
        opened=client.post('/api/playback/open',json={'identity':TRACK.model_dump()}).json()
        assert client.get(opened['streamUrl']).json()['error']['code']=='untrusted_media'
        assert all(not r.streams for r in app.state.media_store.records.values())


def test_wrong_provider_and_oversized_response():
    with pytest.raises(CoreError):run(lambda p:p.resolve(TrackIdentity(providerId='netease',platformId='600123')),lambda r:pytest.fail('不应请求'))
    with pytest.raises(CoreError) as error:run(lambda p:p.resolve(TRACK),lambda r:httpx.Response(200,content=b'x'*(2*1024*1024+1)))
    assert error.value.code==ErrorCode.UPSTREAM_INVALID_RESPONSE
