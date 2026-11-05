"""路线选择使用人工响应，任何测试均不访问第三方音乐平台。"""
import asyncio
import httpx
import pytest
from app.models import TrackIdentity
from app.providers.kuwo import KuwoProvider
from app.core.errors import CoreError,ErrorCode
from scripts.verify_kuwo import probe_media

IDENTITY=TrackIdentity(providerId='kuwo',platformId='123')


def execute(handler):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await KuwoProvider(client).resolve(IDENTITY)
    return asyncio.run(run())


def test_interface_rejection_switches_to_platform_mobi():
    paths=[]
    def handler(request):
        paths.append(request.url.path)
        if len(paths)==1:
            return httpx.Response(200,json={'success':False,'message':'The request is illegal!'})
        assert request.url.host=='mobi.kuwo.cn'
        assert request.url.params['rid']=='123' and request.url.params['format']=='mp3'
        assert 'q' not in request.url.params
        assert request.headers['user-agent']=='okhttp/3.10.0'
        return httpx.Response(200,text='rid=123\r\nformat=mp3\r\nurl=https://example.invalid/audio\r\n')
    media=execute(handler)
    assert paths==['/api/v1/www/music/playUrl','/mobi.s']
    assert media.identity==IDENTITY and media.validUntil is None
    assert media.representation.codec is None and media.representation.sizeBytes is None
    assert 'example.invalid' not in media.model_dump_json()+repr(media)


@pytest.mark.parametrize('body,status',[
    ({'success':False},200),({'success':False,'message':'需要购买'},200),
    ({'success':False,'message':'The request is illegal!','code':403},200),
    ({'success':False,'message':'The request is illegal!'},403),
    ({'code':200,'data':{}},200),({'unexpected':True},200)])
def test_no_fallback_for_permission_or_unconfirmed_failure(body,status):
    calls=[]
    def handler(r):
        calls.append(r)
        return httpx.Response(status,json=body)
    with pytest.raises(CoreError):
        execute(handler)
    assert len(calls)==1


def test_timeout_never_retries():
    calls=[]
    def handler(r):
        calls.append(r)
        raise httpx.ReadTimeout('私有链接不得回显')
    with pytest.raises(CoreError) as error:
        execute(handler)
    assert error.value.code==ErrorCode.UPSTREAM_TIMEOUT and len(calls)==1


def test_cancel_no_fallback():
    async def run():
        calls=[]
        started=asyncio.Event()
        async def handler(r):
            calls.append(r)
            started.set()
            await asyncio.Event().wait()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            task=asyncio.create_task(KuwoProvider(client).resolve(IDENTITY))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert len(calls)==1
    asyncio.run(run())


@pytest.mark.parametrize('text,code',[
    ('rid=999\nurl=https://example.invalid/audio',ErrorCode.UPSTREAM_INVALID_RESPONSE),
    ('rid=123',ErrorCode.MEDIA_UNAVAILABLE),
    ('rid=123\nrid=123\nurl=https://example.invalid/audio',ErrorCode.UPSTREAM_INVALID_RESPONSE),
    ('rid=123\nurl=file:///private',ErrorCode.UPSTREAM_INVALID_RESPONSE),
    ('rid=123\nurl=https://example.invalid/list.m3u8',ErrorCode.CAPABILITY_UNSUPPORTED),
    ('<html>错误页</html>',ErrorCode.UPSTREAM_INVALID_RESPONSE)])
def test_mobi_response_failure(text,code):
    def handler(r):
        if r.url.path.endswith('playUrl'):
            return httpx.Response(200,json={'success':False,'message':'The request is illegal!'})
        return httpx.Response(200,text=text)
    with pytest.raises(CoreError) as error:
        execute(handler)
    assert error.value.code==code


@pytest.mark.parametrize('status,mime,content,range_header,passed,size',[
    (206,'audio/mpeg',b'ID3'+b'x'*4093,'bytes 0-4095/100000',True,100000),
    (200,'application/ogg',b'OggS'+b'x'*10000,None,True,10004),
    (200,'text/html',b'<html>blocked</html>',None,False,20),
    (206,'audio/mpeg',b'ID3x',None,False,None)])
def test_probe_semantics(status,mime,content,range_header,passed,size):
    async def run():
        def handler(r):
            assert r.headers['range']=='bytes=0-4095'
            headers={'content-type':mime,'content-length':str(len(content))}
            if range_header:headers['content-range']=range_header
            return httpx.Response(status,headers=headers,stream=httpx.ByteStream(content))
        media=execute_media()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await probe_media(client,media)
    result=asyncio.run(run())
    assert result['passed']==passed and result['bytesRead']<=4096
    if passed:assert result['sizeBytes']==size


def execute_media():
    from app.models import ResolvedMedia,MediaRepresentation
    return ResolvedMedia(id='temporary',identity=IDENTITY,representation=MediaRepresentation(),
                         resolvedAt=1,upstreamUrl='https://example.invalid/audio')
