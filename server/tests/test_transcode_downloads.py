"""转换生命周期使用自有短音频与私有临时目录，不触碰用户文件。"""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import httpx
import pytest
from app.downloads import DownloadManager,DownloadSettings,DownloadRequest
from app.models import ResolvedMedia,TrackIdentity
from app.download_quality import inspect_audio
from app.core.errors import CoreError,ErrorCode
from app import transcode
from test_downloads import Stream,finish
from test_download_quality import mp3

TRACK=TrackIdentity(providerId='kuwo',platformId='1')


@pytest.mark.parametrize('failure', ['encoder', 'spawn', 'output'])
def test_real_pipeline_failure_stage_and_fallback(tmp_path, audio, monkeypatch, failure):
    if failure == 'encoder':
        async def unavailable(): return {'available':False,'reason':'test no libmp3lame'}
        monkeypatch.setattr(transcode, 'encoder_capability', unavailable)
    elif failure == 'spawn':
        original = transcode.owned_process
        async def missing(args, **kwargs):
            if 'libmp3lame' in args: raise FileNotFoundError('test missing executable')
            return await original(args, **kwargs)
        monkeypatch.setattr(transcode, 'owned_process', missing)
    else:
        original = transcode.probe_file
        async def invalid(probe, path):
            result = await original(probe, path)
            return {**result, 'codec_name':'invalid'} if '-output.part' in path.name else result
        monkeypatch.setattr(transcode, 'probe_file', invalid)
    async def scenario():
        manager, client, _ = await manager_at(tmp_path/'downloads', audio)
        async with client:
            job = manager.create(DownloadRequest(identity=TRACK, outputMode='mp3_192'))
            await finish(job)
            assert job.public.sourcePreserved and job.public.errorCode == 'conversion_failed'
            assert job.public.phase == ('output_verifying' if failure=='output' else 'transcoding')
            assert len(manager.files()) == 1 and not list(manager.root.glob('*.part'))
    asyncio.run(scenario())


def test_nonzero_process_has_bounded_safe_diagnostics(caplog):
    with pytest.raises(CoreError):
        asyncio.run(transcode.owned_process([sys.executable, '-c', 'import sys;sys.stderr.write("invalid frame header https://secret.test/?token=hidden");sys.exit(7)']))
    assert 'exit=7' in caplog.text and 'invalid frame header' in caplog.text
    assert 'secret.test' not in caplog.text and 'hidden' not in caplog.text


def test_parallel_fallback_does_not_duplicate_source(tmp_path, audio, monkeypatch):
    async def broken(*args, **kwargs): raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    monkeypatch.setattr(transcode, 'convert_flac', broken)
    async def scenario():
        manager, client, _ = await manager_at(tmp_path/'downloads', audio)
        async with client:
            jobs = [manager.create(DownloadRequest(identity=TRACK, outputMode=mode)) for mode in ('mp3_192','mp3_320')]
            await asyncio.gather(*(finish(job) for job in jobs))
            assert all(job.public.sourcePreserved for job in jobs)
            assert jobs[0].public.fileId == jobs[1].public.fileId
            assert len(manager.files()) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('phase', ['transcoding', 'output_verifying'])
def test_preserved_source_reused_for_retry(tmp_path, audio, monkeypatch, phase):
    async def scenario():
        real = transcode.convert_flac
        async def broken(source, output, *args, **kwargs):
            output.write_bytes(b'incomplete')
            kwargs['phase_changed'](phase)
            raise transcode.ConversionError(phase, CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE))
        monkeypatch.setattr(transcode, 'convert_flac', broken)
        manager, client, calls = await manager_at(tmp_path/'downloads', audio)
        async with client:
            first = manager.create(DownloadRequest(identity=TRACK, outputMode='mp3_320'))
            await finish(first)
            assert first.public.status == 'failed' and first.public.sourcePreserved
            assert first.public.errorCode == 'conversion_failed' and first.public.phase == phase
            assert first.public.actualMedia.codec == 'flac' and first.public.outputMode == 'mp3_320'
            original = manager.root / first.public.filename
            before = original.read_bytes()
            second = manager.create(DownloadRequest(identity=TRACK, outputMode='mp3_320'))
            await finish(second)
            assert second.public.fileId == first.public.fileId
            assert len(manager.files()) == 1 and len(calls) == 1
            monkeypatch.setattr(transcode, 'convert_flac', real)
            third = manager.create(DownloadRequest(identity=TRACK, outputMode='mp3_320'))
            await finish(third)
            assert third.public.status == 'completed' and third.public.actualMedia.codec == 'mp3'
            assert original.read_bytes() == before and len(calls) == 1
            assert not list(manager.root.glob('*.part'))
    asyncio.run(scenario())


def test_truncated_source_never_publishes_incomplete_mp3(tmp_path, audio):
    async def scenario():
        manager, client, _ = await manager_at(tmp_path/'downloads', audio[:-1000])
        async with client:
            job = manager.create(DownloadRequest(identity=TRACK, outputMode='mp3_192'))
            await finish(job)
            assert job.public.errorCode == 'conversion_failed'
            assert job.public.sourcePreserved and len(manager.files()) == 1
            assert (manager.root/job.public.filename).read_bytes() == audio[:-1000]
    asyncio.run(scenario())

@pytest.fixture
def audio(tmp_path):
    executable,_=transcode.tools()
    if not executable:pytest.skip('本机未安装FFmpeg，缺失能力另有离线测试')
    path=tmp_path/'fixture.flac'
    subprocess.run([executable,'-nostdin','-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=44100:duration=2','-ac','2','-c:a','flac',str(path)],check=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    return path.read_bytes()

async def manager_at(directory,raw,**kwargs):
    calls=[]
    async def allow(*args):pass
    async def resolve(identity,options):
        calls.append(options)
        return ResolvedMedia(id='private',identity=identity,resolvedAt=1,upstreamUrl='https://cdn.test/file',representation=inspect_audio(raw).model_copy(update={'sizeBytes':len(raw)}))
    client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'content-length':str(len(raw))},stream=Stream(raw))))
    state=SimpleNamespace(kuwo=SimpleNamespace(resolve=resolve),http_client=client,target_check=allow)
    return DownloadManager(state,DownloadSettings(directory=directory,**kwargs)),client,calls

@pytest.mark.parametrize('mode',['original','mp3_320','mp3_192'])
def test_real_conversion_and_atomic_publish(tmp_path,audio,mode):
    async def scenario():
        manager,client,_=await manager_at(tmp_path/'downloads',audio)
        async with client:
            job=manager.create(DownloadRequest(identity=TRACK,quality='lossless',outputMode=mode,expectedSourceCodec='flac'));await finish(job)
            assert job.public.status=='completed',job.public
            assert job.public.sourceMedia.codec=='flac'
            assert job.public.transcoded==(mode!='original')
            assert job.public.actualMedia.lossless==(mode=='original')
            assert job.public.finalSizeBytes==(manager.root/job.public.filename).stat().st_size
            assert len(manager.files())==1 and not list(manager.root.glob('*.part'))
            assert job.public.actualMedia.codec==('flac' if mode=='original' else 'mp3')
            if mode!='original':assert job.public.actualMedia.bitrateBps==(320000 if mode=='mp3_320' else 192000)
            other=manager.create(DownloadRequest(identity=TRACK,outputMode=mode));await finish(other)
            assert other.public.status=='completed' and other.public.filename!=job.public.filename
    asyncio.run(scenario())

def test_missing_tools_keep_original(tmp_path,audio,monkeypatch):
    monkeypatch.setattr(transcode,'tools',lambda:(None,None))
    async def scenario():
        assert not (await transcode.encoder_capability())['available']
        manager,client,_=await manager_at(tmp_path/'downloads',audio)
        async with client:
            for mode in ('original','mp3_320'):
                job=manager.create(DownloadRequest(identity=TRACK,outputMode=mode));await finish(job)
                assert job.public.status==('completed' if mode=='original' else 'failed')
            assert len(manager.files())==1 and not list(manager.root.glob('*.part'))
    asyncio.run(scenario())

def test_no_lame_encoder(monkeypatch):
    monkeypatch.setattr(transcode,'tools',lambda:('ffmpeg','ffprobe'))
    async def result(*args,**kwargs):return b'Encoders: no encoder available'
    monkeypatch.setattr(transcode,'owned_process',result)
    assert not asyncio.run(transcode.encoder_capability())['available']

def test_no_lossy_reencode_or_changed_source(tmp_path):
    async def scenario():
        for expected,mode in [('flac','original'),(None,'mp3_320')]:
            manager,client,_=await manager_at(tmp_path/str(mode),mp3())
            async with client:
                job=manager.create(DownloadRequest(identity=TRACK,outputMode=mode,expectedSourceCodec=expected));await finish(job)
                assert job.public.status=='failed' and not manager.files() and not list(manager.root.glob('*.part'))
    asyncio.run(scenario())

def test_known_mp3_prefers_direct_and_preserves_target(tmp_path,monkeypatch):
    import time
    async def forbidden(*args,**kwargs):pytest.fail('已有目标MP3不能转码')
    monkeypatch.setattr(transcode,'convert_flac',forbidden)
    async def scenario():
        manager,client,calls=await manager_at(tmp_path/'downloads',mp3(True))
        manager.state.download_quality_cache={('kuwo','1','high'):(time.time()+30,{'representation':inspect_audio(mp3(True)).model_dump()})}
        async with client:
            job=manager.create(DownloadRequest(identity=TRACK,quality='lossless',outputMode='mp3_320',expectedSourceCodec='flac'));await finish(job)
            assert job.public.status=='completed' and not job.public.transcoded and job.public.quality=='lossless'
            assert calls[0].providerQualityId=='high' and len(calls)==1
    asyncio.run(scenario())

@pytest.mark.parametrize('kind',['cancel','timeout','disk','invalid'])
def test_failure_cleanup_and_cancel(tmp_path,audio,monkeypatch,kind):
    async def scenario():
        entered=asyncio.Event()
        async def convert(source,output,*args,**kwargs):
            assert source.exists() and job.public.actualMedia is None;output.write_bytes(b'partial');entered.set()
            if kind in ('cancel','timeout'):await asyncio.Event().wait()
            if kind=='disk':raise OSError('磁盘空间不足')
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        monkeypatch.setattr(transcode,'convert_flac',convert)
        manager,client,_=await manager_at(tmp_path/'downloads',audio,conversion_timeout=2 if kind=='timeout' else 5)
        async with client:
            job=manager.create(DownloadRequest(identity=TRACK,outputMode='mp3_192'));await entered.wait()
            if kind=='cancel':await manager.cancel(job)
            await finish(job)
            assert job.public.status==('cancelled' if kind=='cancel' else 'failed')
            assert bool(manager.files()) == (kind in ('timeout','invalid'))
            assert job.public.sourcePreserved == (kind in ('timeout','invalid'))
            assert not list(manager.root.glob('*.part'))
    asyncio.run(scenario())

def test_conversion_serial_and_service_close(tmp_path,audio,monkeypatch):
    async def scenario():
        active=0;peak=0;entered=asyncio.Event()
        async def convert(source,output,*args,**kwargs):
            nonlocal active,peak
            active+=1;peak=max(peak,active);entered.set()
            try:await asyncio.Event().wait()
            finally:active-=1
        monkeypatch.setattr(transcode,'convert_flac',convert)
        manager,client,_=await manager_at(tmp_path/'downloads',audio)
        async with client:
            jobs=[manager.create(DownloadRequest(identity=TRACK,outputMode='mp3_320')) for _ in range(2)]
            await entered.wait();await asyncio.sleep(.05);assert peak==1
            await manager.close();assert active==0 and all(j.public.status=='cancelled' for j in jobs)
            assert not list(manager.root.glob('*.part'))
    asyncio.run(scenario())

@pytest.mark.parametrize('cancel',[False,True])
def test_owned_process_terminated_on_timeout_or_cancel(monkeypatch,cancel):
    async def scenario():
        original=asyncio.create_subprocess_exec;processes=[]
        async def spawn(*args,**kwargs):
            process=await original(*args,**kwargs);processes.append(process);return process
        monkeypatch.setattr(asyncio,'create_subprocess_exec',spawn)
        work=asyncio.create_task(transcode.owned_process([sys.executable,'-c','import time;time.sleep(30)'],timeout=.1))
        while not processes:await asyncio.sleep(.005)
        if cancel:work.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else asyncio.TimeoutError):await work
        assert processes[0].returncode is not None
    asyncio.run(scenario())


def test_corrupt_flac_is_not_published(tmp_path,audio):
    async def scenario():
        manager,client,_=await manager_at(tmp_path/'downloads',audio[:80])
        async with client:
            job=manager.create(DownloadRequest(identity=TRACK,outputMode='mp3_320'));await finish(job)
            assert job.public.status=='failed' and not manager.files() and not list(manager.root.glob('*.part'))
    asyncio.run(scenario())

def test_process_output_limit_and_unusable_executable(tmp_path,monkeypatch):
    async def scenario():
        output=tmp_path/'limited.part'
        command=[sys.executable,'-c','import sys,time;from pathlib import Path;Path(sys.argv[1]).write_bytes(b"x"*1024);time.sleep(30)',str(output)]
        with pytest.raises(CoreError) as raised:await transcode.owned_process(command,timeout=3,output=output,max_bytes=32)
        assert raised.value.code==ErrorCode.MEDIA_CAPACITY
        monkeypatch.setattr(transcode,'tools',lambda:(str(tmp_path/'not-executable'),str(tmp_path/'missing-probe')))
        assert not (await transcode.encoder_capability())['available']
    asyncio.run(scenario())

def test_cancel_while_process_is_spawning(monkeypatch):
    async def scenario():
        original=asyncio.create_subprocess_exec;processes=[]
        async def slow(*args,**kwargs):
            await asyncio.sleep(.05);process=await original(*args,**kwargs);processes.append(process);return process
        monkeypatch.setattr(asyncio,'create_subprocess_exec',slow)
        work=asyncio.create_task(transcode.owned_process([sys.executable,'-c','import time;time.sleep(30)']))
        await asyncio.sleep(.01);work.cancel()
        with pytest.raises(asyncio.CancelledError):await work
        assert len(processes)==1 and processes[0].returncode is not None
    asyncio.run(scenario())


def test_retry_keeps_saving_intent_and_re_resolves(tmp_path,audio):
    from fastapi.testclient import TestClient
    from app.main import create_app
    import time
    calls=[]
    async def allow(*args):pass
    async def resolve(identity,options):
        calls.append(options)
        if len(calls)==1:raise CoreError(ErrorCode.UPSTREAM_MEDIA_EXPIRED)
        return ResolvedMedia(id='new-media',identity=identity,resolvedAt=1,upstreamUrl='https://cdn.test/fresh',representation=inspect_audio(audio).model_copy(update={'sizeBytes':len(audio)}))
    app=create_app(transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'content-length':str(len(audio))},stream=Stream(audio))),target_check=allow,download_settings=DownloadSettings(directory=tmp_path/'downloads'))
    with TestClient(app) as client:
        app.state.kuwo=SimpleNamespace(resolve=resolve)
        body={'identity':TRACK.model_dump(),'quality':'lossless','outputMode':'mp3_192','expectedSourceCodec':'flac'}
        def terminal(identifier):
            for _ in range(300):
                task=client.get('/api/downloads/'+identifier).json()
                if task['status'] in ('completed','failed','cancelled'):return task
                time.sleep(.01)
            pytest.fail('转换任务未按时结束')
        first=client.post('/api/downloads',json=body).json();assert terminal(first['id'])['status']=='failed'
        retry=client.post('/api/downloads/'+first['id']+'/retry').json();result=terminal(retry['id'])
        assert result['status']=='completed' and result['transcoded'] and result['actualMedia']['codec']=='mp3'
        assert result['outputMode']=='mp3_192' and result['quality']=='lossless' and result['expectedSourceCodec']=='flac'
        assert retry['id']!=first['id'] and len(calls)==2 and not list((tmp_path/'downloads').glob('*.part'))


@pytest.mark.parametrize('mode', ['mp3_320', 'mp3_192'])
def test_trailing_junk_does_not_block_complete_conversion(tmp_path, audio, mode):
    raw = audio + bytes.fromhex('f000ff0f44444048463c360e55fff0')
    async def scenario():
        manager, client, _ = await manager_at(tmp_path/'downloads', raw)
        async with client:
            job = manager.create(DownloadRequest(identity=TRACK, quality='lossless', outputMode=mode))
            await finish(job)
            assert job.public.status == 'completed', job.public
            assert job.public.actualMedia.codec == 'mp3' and job.public.transcoded
            assert not job.public.sourcePreserved and not list(manager.root.glob('*.part'))
    asyncio.run(scenario())
