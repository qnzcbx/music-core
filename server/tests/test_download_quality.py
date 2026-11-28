"""品质核对使用结构化合成音频，不冒充真实录音。"""
import asyncio
from types import SimpleNamespace
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.models import ResolveOptions, TrackIdentity, ResolvedMedia, MediaRepresentation
from app.core.media_probe import inspect_audio
from app.download_quality import satisfies
from app.downloads import DownloadRequest
from app.core.errors import CoreError, ErrorCode
from test_downloads import setup, Stream, finish, TRACK


def mp3(high=False):
    header=bytes.fromhex('fffbe000' if high else 'fffb9000');length=1044 if high else 417
    return (header+b'\0'*(length-4))*5

def flac():
    data=bytearray(34);data[10:18]=((44100<<44)|(1<<41)|(15<<36)|44100).to_bytes(8,'big')
    return b'fLaC'+b'\x80'+(34).to_bytes(3,'big')+data

@pytest.mark.parametrize('raw,codec,bitrate,lossless',[(mp3(),'mp3',128000,False),(mp3(True),'mp3',320000,False),(flac(),'flac',None,True)])
def test_byte_quality(raw,codec,bitrate,lossless):
    value=inspect_audio(raw)
    assert value.codec==codec and value.bitrateBps==bitrate and value.lossless==lossless and value.sampleRateHz==44100

def test_no_suffix_or_id3_or_container_quality_inference():
    for data in (b'ID3'+b'x'*100,b'\0\0\0\x18ftypM4A '+b'x'*100,b'fLaC'+b'x'*100):
        assert not satisfies(inspect_audio(data),'lossless')
    assert not satisfies(inspect_audio(mp3(True)),'lossless')

@pytest.mark.parametrize('quality,raw,success',[('standard',mp3(),True),('standard',mp3(True),True),('high',mp3(True),True),('lossless',mp3(True),False),('lossless',flac(),True),('high',mp3(),False)])
def test_manager_checks_real_bytes_and_cleanup(tmp_path,quality,raw,success):
    async def scenario():
        build,calls,_=setup(tmp_path,Stream(raw),{'content-length':str(len(raw))})
        manager,client=await build()
        async with client:
            job=manager.create(DownloadRequest(identity=TRACK,quality=quality));await finish(job)
            assert calls[0].purpose=='download' and calls[0].providerQualityId==quality
            assert (job.public.status=='completed')==success
            assert not list(tmp_path.glob('*.part'))
            assert len(list(tmp_path.glob('*.mp3'))+list(tmp_path.glob('*.flac')))==int(success)
            if success:assert job.public.actualMedia.codec==('flac' if quality=='lossless' else 'mp3')
    asyncio.run(scenario())


def test_netease_requested_parameters_and_mismatch_fallback(monkeypatch):
    from app.providers.netease import NeteaseProvider
    import app.core.media_probe as probe
    calls=[]
    async def allow(*args):pass
    monkeypatch.setattr(probe,'validate_target',allow)
    def handler(request):
        from urllib.parse import parse_qsl
        calls.append((request.url.host,dict(parse_qsl(request.content.decode())) if request.method=='POST' else dict(request.url.params)))
        if request.url.host=='music-api.gdstudio.xyz':return httpx.Response(200,json={'id':167691,'url':'https://cdn.test/high'})
        if request.url.host=='cdn.test':
            raw=mp3(True) if request.url.path=='/high' else mp3()
            end=min(int(request.headers.get('range','bytes=0-4095').split('-')[1]),len(raw)-1)
            return httpx.Response(206,headers={'content-range':f'bytes 0-{end}/{len(raw)}'},stream=Stream(raw[:end+1]))
        return httpx.Response(200,json={'code':200,'data':[{'id':167691,'code':200,'url':'https://cdn.test/standard'}]})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider=NeteaseProvider(client,route_order=('native','gdstudio-preview','jfjt'))
            result=await provider.resolve(TrackIdentity(providerId='netease',platformId='167691'),ResolveOptions(purpose='download',providerQualityId='high'))
            assert result.representation.bitrateBps==320000
            assert any(params.get('br')=='320000' for _,params in calls)
            assert ('music-api.gdstudio.xyz',{'types':'url','id':'167691','source':'netease','br':'320'}) in calls
            assert not any(host=='dm.jfjt.cc' for host,_ in calls)
    asyncio.run(scenario())

def test_explicit_denial_not_quality_fallback():
    from app.providers.netease import NeteaseProvider
    calls=[]
    def handler(request):calls.append(request.url.host);return httpx.Response(200,json={'code':200,'data':[{'id':1,'code':403}]})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider=NeteaseProvider(client,route_order=('native','gdstudio-preview'))
            with pytest.raises(CoreError) as raised:await provider.resolve(TrackIdentity(providerId='netease',platformId='1'),ResolveOptions(purpose='download',providerQualityId='lossless'))
            assert raised.value.code==ErrorCode.ACCESS_DENIED and len(calls)==1
    asyncio.run(scenario())

def test_preview_metadata_cache_and_quality_retry(tmp_path,monkeypatch):
    import app.core.media_probe as probe
    from app.downloads import DownloadSettings
    count=[]
    async def allow(*args):pass
    monkeypatch.setattr(probe,'validate_target',allow)
    raw=mp3(True)
    def handler(request):
        if 'range' not in request.headers:return httpx.Response(200,stream=Stream(raw))
        end=len(raw)-1;return httpx.Response(206,headers={'content-range':f'bytes 0-{end}/{len(raw)}'},stream=Stream(raw))
    app=create_app(transport=httpx.MockTransport(handler),target_check=allow,download_settings=DownloadSettings(directory=tmp_path))
    async def resolve(identity,options):
        count.append(options.providerQualityId)
        return ResolvedMedia(id='private',identity=identity,resolvedAt=1,upstreamUrl='https://cdn.test/secret',representation=MediaRepresentation())
    with TestClient(app) as client:
        app.state.kuwo=SimpleNamespace(resolve=resolve)
        body={'identity':TRACK.model_dump(),'quality':'high'}
        assert client.post('/api/downloads/options',json=body).json()['availability']=='available'
        assert client.post('/api/downloads/options',json=body).json()['availability']=='available'
        assert count==['high']
        failed=client.post('/api/downloads',json={**body,'quality':'lossless'}).json()
        import time
        for _ in range(100):
            value=client.get('/api/downloads/'+failed['id']).json()
            if value['status']=='failed':break
            time.sleep(.01)
        assert value['status']=='failed' and value['quality']=='lossless'
        retry=client.post('/api/downloads/'+failed['id']+'/retry').json()
        assert retry['quality']=='lossless' and retry['id']!=failed['id']
        assert 'secret' not in client.post('/api/downloads/options',json=body).text


def test_quality_resolution_cancellation_and_budget():
    from app.providers.qq import QQProvider
    async def scenario():
        provider=QQProvider(None);started=asyncio.Event();cancelled=[]
        async def blocked(route,identity,options):
            assert options.providerQualityId=='high';started.set()
            try:await asyncio.Event().wait()
            finally:cancelled.append(True)
        provider._resolve_route=blocked
        options=ResolveOptions(purpose='download',providerQualityId='high')
        work=asyncio.create_task(provider.resolve(TrackIdentity(providerId='qq',platformId='ABC'),options))
        await started.wait();work.cancel()
        with pytest.raises(asyncio.CancelledError):await work
        provider.resolve_timeout=.01
        with pytest.raises(CoreError) as raised:await provider.resolve(TrackIdentity(providerId='qq',platformId='ABC'),options)
        assert raised.value.code==ErrorCode.UPSTREAM_TIMEOUT and len(cancelled)==2
    asyncio.run(scenario())


def test_kuwo_quality_preserves_official_denial():
    from app.providers.kuwo import KuwoProvider
    async def scenario():
        provider=KuwoProvider(None);calls=[]
        async def request(url,params,**kwargs):calls.append(url);return {'success':False,'code':403}
        provider.request=request
        with pytest.raises(CoreError) as raised:await provider.resolve(TRACK,ResolveOptions(purpose='download',providerQualityId='high'))
        assert raised.value.code==ErrorCode.ACCESS_DENIED and len(calls)==1
    asyncio.run(scenario())


@pytest.mark.parametrize('quality', ['auto', 'high', 'lossless'])
@pytest.mark.parametrize('failure', ['unsupported_loop', 'missing_tools', 'missing_encoder'])
def test_flac_options_keep_original_when_conversion_unavailable(tmp_path, monkeypatch, quality, failure):
    import app.transcode as transcode
    from app.downloads import DownloadSettings

    async def unsupported(*args, **kwargs):
        raise NotImplementedError('event loop has no subprocess transport')

    monkeypatch.setattr(transcode, 'tools', lambda: ('ffmpeg', 'ffprobe'))
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', unsupported)
    if failure == 'missing_tools':
        monkeypatch.setattr(transcode, 'tools', lambda: (None, None))
    elif failure == 'missing_encoder':
        async def no_encoder(*args, **kwargs):
            return b'Encoders: no libmp3 encoder'
        monkeypatch.setattr(transcode, 'owned_process', no_encoder)

    async def resolve(identity, options):
        return ResolvedMedia(id='flac', identity=identity, resolvedAt=1,
                             upstreamUrl='https://cdn.test/private',
                             representation=inspect_audio(flac()).model_copy(update={'sizeBytes':50000000}))

    app = create_app(download_settings=DownloadSettings(directory=tmp_path))
    with TestClient(app) as client:
        app.state.qq = SimpleNamespace(resolve=resolve)
        response = client.post('/api/downloads/options', json={
            'identity': {'providerId':'qq', 'platformId':'0023CVP23SH17s'}, 'quality':quality})
        assert response.status_code == 200
        result = response.json()
        assert result['availability'] == 'available' and result['errorCode'] is None
        assert result['representation']['codec'] == 'flac'
        assert result['representation']['lossless'] is True
        assert result['conversion']['available'] is False
        assert result['conversion']['reason']


def test_encoder_capability_does_not_hide_unexpected_errors(monkeypatch):
    import app.transcode as transcode
    monkeypatch.setattr(transcode, 'tools', lambda: ('ffmpeg', 'ffprobe'))

    async def unexpected(*args, **kwargs):
        raise RuntimeError('programming error')

    monkeypatch.setattr(asyncio, 'create_subprocess_exec', unexpected)
    with pytest.raises(RuntimeError):
        asyncio.run(transcode.encoder_capability())


@pytest.mark.parametrize('status,headers,total', [
    (206, {'content-range':'bytes 0-65535/50000000', 'content-length':'65536'}, 50000000),
    (200, {'content-length':'50000000'}, 50000000),
    (200, {}, None),
])
def test_probe_reports_entity_total_not_received_prefix(monkeypatch, status, headers, total):
    import app.core.media_probe as probe
    async def allow(*args):
        pass
    monkeypatch.setattr(probe, 'validate_target', allow)
    raw = flac() + b'\0' * (65536 - len(flac()))
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(status, headers=headers, stream=Stream(raw)))) as client:
            result = await probe.verify_media(client, 'https://cdn.test/media', detail=True)
            assert result.codec == 'flac' and result.sizeBytes == total
    asyncio.run(scenario())


def test_standard_accepts_observed_lossy_aac_without_marking_it_lossless():
    aac = MediaRepresentation(codec='aac', lossless=False, sampleRateHz=44100, bitrateBps=191800)
    assert satisfies(aac, 'standard')
    assert not satisfies(aac, 'lossless')
