"""下载专项使用自有字节和受控流，不访问真实平台。"""
import asyncio
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.downloads import DownloadManager, DownloadSettings, DownloadRequest
from app.core.file_name import safe_stem
from app.models import TrackIdentity, ResolvedMedia, MediaRepresentation

TRACK = TrackIdentity(providerId='kuwo', platformId='1')
RAW = b'ID3' + b'x'*131069


class Stream(httpx.AsyncByteStream):
    def __init__(self, data=RAW, *, wait=None, error=False):
        self.data, self.wait, self.error, self.closed = data, wait, error, False

    async def __aiter__(self):
        yield self.data[:65536]
        if self.wait: await self.wait.wait()
        if self.error: raise httpx.ReadError('敏感上游地址')
        yield self.data[65536:]

    async def aclose(self): self.closed = True


async def allow(url): pass


def setup(tmp_path, stream, headers=None, status=200, **settings):
    calls = []
    async def resolve(identity, options):
        calls.append(options)
        return ResolvedMedia(id='private', identity=identity, resolvedAt=1,
                             representation=MediaRepresentation(), upstreamUrl='https://cdn.kuwo.cn/secret?token=private')
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers=headers or {}, stream=stream)
    async def build():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), cookies={'private':'secret'}, auth=('a','b'))
        state = SimpleNamespace(kuwo=SimpleNamespace(resolve=resolve), http_client=client, target_check=allow)
        return DownloadManager(state, DownloadSettings(directory=tmp_path, **settings)), client
    return build, calls, requests


async def finish(job):
    if job.worker: await job.worker


@pytest.mark.parametrize('raw,kind',[(RAW,'mp3'),(b'fLaC'+b'x'*100,'flac'),(b'\x00\x00\x00\x18ftypM4A '+b'x'*100,'m4a'),(b'OggS'+b'x'*100,'ogg')])
@pytest.mark.parametrize('known',[True,False])
def test_formats_lengths(tmp_path, raw, kind, known):
    async def scenario():
        stream = Stream(raw)
        build,calls,requests = setup(tmp_path,stream,{'content-type':'audio/mpeg', **({'content-length':str(len(raw))} if known else {})})
        manager,client = await build()
        async with client:
            job=manager.create(DownloadRequest(identity=TRACK,title='飞鸟与鱼',artist='齐豫'))
            await finish(job)
            p=manager.view(job)
            assert p.status=='completed' and p.format==kind
            assert (tmp_path/p.filename).read_bytes()==raw and stream.closed
            assert p.totalBytes==(len(raw) if known else None)
            assert p.progress==(1 if known else None)
            assert calls[0].purpose=='download'
            assert 'range' not in requests[0].headers and 'cookie' not in requests[0].headers and 'authorization' not in requests[0].headers
            assert requests[0].headers['accept-encoding']=='identity'
            assert not list(tmp_path.glob('*.part')) and 'secret' not in p.model_dump_json()
            await manager.cancel(job)
            assert job.public.status=='completed' and (tmp_path/p.filename).exists()
    asyncio.run(scenario())


@pytest.mark.parametrize('status,headers,raw,error',[
    (206,{'content-range':'bytes 0-131071/131072','content-length':'131072'},RAW,None),
    (206,{'content-range':'bytes 0-9/100'},RAW,'upstream_invalid_response'),
    (206,{},RAW,'upstream_invalid_response'),
    (200,{'content-range':'bytes 5-9/10'},RAW,'upstream_invalid_response'),
    (200,{'content-length':'131073'},RAW,'upstream_invalid_response'),
    (200,{'content-length':'1'},RAW,'upstream_invalid_response'),
    (200,{'content-length':'bad'},RAW,'upstream_invalid_response'),
    (200,{'content-encoding':'gzip'},RAW,'upstream_invalid_response'),
    (200,{},'<html>错误</html>'.encode(),'upstream_invalid_response'),
    (200,{},b'','upstream_invalid_response'),
    (403,{},RAW,'access_denied'),(404,{},RAW,'upstream_media_expired'),
    (429,{},RAW,'upstream_failure'),(503,{},RAW,'upstream_failure'),
])
def test_integrity_errors(tmp_path,status,headers,raw,error):
    async def scenario():
        stream=Stream(raw)
        build,_,_=setup(tmp_path,stream,headers,status)
        manager,client=await build()
        async with client:
            job=manager.create(DownloadRequest(identity=TRACK))
            await finish(job)
            assert job.public.errorCode==error and job.public.status==('failed' if error else 'completed')
            assert stream.closed and not list(tmp_path.glob('*.part'))
            if error: assert not list(tmp_path.iterdir())
    asyncio.run(scenario())


def test_cancellation_queue_and_shutdown(tmp_path):
    async def scenario():
        streams=[];gate=asyncio.Event()
        build,calls,_=setup(tmp_path,Stream())
        manager,client=await build()
        async def handler(request):
            stream=Stream(wait=gate);streams.append(stream)
            return httpx.Response(200,stream=stream)
        client._transport=httpx.MockTransport(handler)
        async with client:
            jobs=[manager.create(DownloadRequest(identity=TRACK)) for _ in range(3)]
            for _ in range(100):
                if all(j.public.receivedBytes for j in jobs[:2]): break
                await asyncio.sleep(.001)
            assert [j.public.status for j in jobs]==['downloading','downloading','queued']
            assert len(calls)==2
            await manager.cancel(jobs[2]);await manager.cancel(jobs[2])
            await manager.close()
            assert all(j.public.status=='cancelled' for j in jobs)
            assert all(s.closed for s in streams) and not list(tmp_path.iterdir())
            await asyncio.sleep(0)
            assert all(j.worker is None for j in jobs)
    asyncio.run(scenario())


def test_resolving_cancel_and_capacity(tmp_path):
    async def scenario():
        build,_,_=setup(tmp_path,Stream(),max_pending=1)
        manager,client=await build()
        async def resolve(*args): await asyncio.Event().wait()
        manager.state.kuwo.resolve=resolve
        async with client:
            job=manager.create(DownloadRequest(identity=TRACK))
            await asyncio.sleep(.01)
            assert job.public.status=='resolving'
            with pytest.raises(Exception) as e: manager.create(DownloadRequest(identity=TRACK))
            assert e.value.status_code==429
            await manager.cancel(job)
            assert job.public.status=='cancelled' and not list(tmp_path.iterdir())
    asyncio.run(scenario())


def test_disconnect_and_retry_api(tmp_path):
    streams=[]
    async def handler(request):
        stream=Stream(error=len(streams)==0);streams.append(stream)
        return httpx.Response(200,stream=stream)
    app=create_app(download_settings=DownloadSettings(directory=tmp_path),target_check=allow,transport=httpx.MockTransport(handler))
    with TestClient(app) as client:
        resolve_calls=[]
        async def resolve(identity,options):
            resolve_calls.append(options)
            return ResolvedMedia(id='hidden',identity=identity,resolvedAt=1,representation=MediaRepresentation(),upstreamUrl='https://cdn.kuwo.cn/private')
        app.state.kuwo.resolve=resolve
        def wait(identifier):
            import time
            for _ in range(200):
                data=client.get('/api/downloads/'+identifier).json()
                if data['status'] in ('failed','completed'): return data
                time.sleep(.005)
            pytest.fail('任务未结束')
        response=client.post('/api/downloads',json={'identity':TRACK.model_dump()})
        assert response.status_code==202
        first=wait(response.json()['id']);assert first['status']=='failed'
        retry=client.post('/api/downloads/'+first['id']+'/retry')
        second=wait(retry.json()['id']);assert second['status']=='completed' and second['id']!=first['id']
        assert len(resolve_calls)==2 and all(s.closed for s in streams)
        assert client.post('/api/downloads/'+second['id']+'/retry').status_code==409
        assert client.post('/api/downloads/'+second['id']+'/cancel').json()['status']=='completed'
        assert len(client.get('/api/downloads').json())==2
        assert 'private' not in client.get('/api/downloads').text
        assert not app.state.media_store.records and not app.state.playback_leases.entries
        for path in ('/api/downloads/missing','/api/downloads/missing/cancel','/api/downloads/missing/retry'):
            assert (client.get(path) if path.endswith('missing') else client.post(path)).status_code==404
        for body in ({'providerId':'other','platformId':'1'},{'providerId':'kuwo','platformId':'../a'}):
            assert client.post('/api/downloads',json={'identity':body}).status_code==422
        assert client.post('/api/downloads',json={'identity':TRACK.model_dump(),'url':'https://evil.test'}).status_code==422


@pytest.mark.parametrize('name',['CON','con.txt','NUL','LPT1','../逃逸/名称:*?"<>|\x00','   ','a'*1000,'飞鸟与鱼𝄞'])
def test_safe_names(name):
    result=safe_stem(name)
    assert result and len(result.encode('utf-16-le'))<=242
    assert not any(c in result for c in '\\/:*?"<>|\x00') and not result.endswith((' ','.'))
    assert result not in ('CON','con.txt','NUL','LPT1')


def test_collision_restart_and_file_failure(tmp_path):
    async def scenario():
        build,_,_=setup(tmp_path,Stream())
        manager,client=await build()
        async with client:
            # 并发同名任务与已有用户文件均不互相覆盖。
            (tmp_path/'同名.mp3').write_bytes('用户文件'.encode())
            jobs=[manager.create(DownloadRequest(identity=TRACK,title='同名')) for _ in range(2)]
            await asyncio.gather(*(finish(j) for j in jobs))
            assert {j.public.filename for j in jobs}=={'同名 (2).mp3','同名 (3).mp3'}
            assert (tmp_path/'同名.mp3').read_bytes()=='用户文件'.encode()
            stale=tmp_path/('.music-core-999999999-'+'a'*32+'.part');stale.write_bytes('未完成'.encode())
            other=tmp_path/'user.part';other.write_bytes('保留'.encode())
            manager.prepare();assert not stale.exists() and other.exists()
            bad=tmp_path/'文件';bad.write_bytes('非目录'.encode())
            manager.root=bad
            job=manager.create(DownloadRequest(identity=TRACK));await finish(job)
            assert job.public.status=='failed' and job.public.errorCode in ('file_io_error','temporary_cleanup_failed')
    asyncio.run(scenario())


@pytest.mark.parametrize('failure',['open','write','sync','publish','size_limit','timeout','target','redirect'])
def test_resource_failures(tmp_path, monkeypatch, failure):
    async def scenario():
        stream=Stream(wait=asyncio.Event() if failure=='timeout' else None)
        build,_,requests=setup(tmp_path,stream,**({'max_bytes':1024} if failure=='size_limit' else {'timeout':.02} if failure=='timeout' else {}))
        manager,client=await build()
        async with client:
            if failure=='open':
                monkeypatch.setattr(Path,'open',lambda *a,**k: (_ for _ in ()).throw(PermissionError()))
            if failure=='write':
                original=Path.open
                class Broken:
                    def __enter__(self):self.file=original(tmp_path/'broken','wb');return self
                    def write(self,chunk): raise OSError('磁盘已满')
                    def __exit__(self,*args):self.file.close();(tmp_path/'broken').unlink()
                monkeypatch.setattr(Path,'open',lambda *a,**k:Broken())
            if failure in ('sync','publish'):
                import os
                monkeypatch.setattr(os,'fsync' if failure=='sync' else 'link',lambda *a: (_ for _ in ()).throw(OSError('文件系统错误')))
            if failure in ('target','redirect'):
                from app.core.errors import CoreError,ErrorCode
                async def check(url):
                    if 'evil' in url: raise CoreError(ErrorCode.UNTRUSTED_MEDIA)
                manager.state.target_check=check
                if failure=='target':
                    async def deny(url):raise CoreError(ErrorCode.UNTRUSTED_MEDIA)
                    manager.state.target_check=deny
                else:
                    async def redirect(request):return httpx.Response(302,headers={'location':'https://evil.test/'},stream=stream)
                    client._transport=httpx.MockTransport(redirect)
            job=manager.create(DownloadRequest(identity=TRACK));await finish(job)
            assert job.public.status=='failed' and job.public.filename is None
            assert not list(tmp_path.iterdir())
            if failure!='target': assert stream.closed
    asyncio.run(scenario())


def test_large_bounded_transfer(tmp_path):
    async def scenario():
        import tracemalloc
        total=128*1024*1024
        class Generated(httpx.AsyncByteStream):
            closed=False
            async def __aiter__(self):
                # 自有传输载荷只验证128MiB字节传输，不冒称完整有效FLAC录音。
                block=b'x'*65536
                yield b'fLaC'+block[4:]
                for _ in range(total//65536-1):yield block
            async def aclose(self):self.closed=True
        stream=Generated()
        build,_,_=setup(tmp_path,stream,{'content-length':str(total)})
        manager,client=await build()
        tracemalloc.start()
        try:
            async with client:
                job=manager.create(DownloadRequest(identity=TRACK))
                seen=[]
                while job.worker is not None:
                    seen.append(job.public.receivedBytes)
                    await asyncio.sleep(.001)
                _,peak=tracemalloc.get_traced_memory()
                assert job.public.status=='completed' and job.public.receivedBytes==total and stream.closed
                assert (tmp_path/job.public.filename).stat().st_size==total
                assert len(set(seen))>3 and peak<8*1024*1024
                print({'controlledBytes':total,'pythonPeakBytes':peak,'progressSamples':len(set(seen))})
        finally:tracemalloc.stop()
    asyncio.run(scenario())


def test_download_does_not_touch_playback(tmp_path):
    from test_media_lifecycle import media
    app=create_app(download_settings=DownloadSettings(directory=tmp_path),target_check=allow,
                   transport=httpx.MockTransport(lambda r:httpx.Response(200,stream=Stream(error=True))))
    with TestClient(app) as client:
        entry=app.state.media_store.put(media())
        lease=app.state.playback_leases.create(entry.id)
        async def resolve(identity,options):return media().model_copy(update={'identity':identity})
        app.state.kuwo.resolve=resolve
        response=client.post('/api/downloads',json={'identity':TRACK.model_dump()})
        import time
        for _ in range(100):
            result=client.get('/api/downloads/'+response.json()['id']).json()
            if result['status']=='failed':break
            time.sleep(.005)
        assert result['status']=='failed'
        assert app.state.media_store.get(entry.id).media.id==entry.id
        assert len(app.state.playback_leases.entries)==1


@pytest.mark.parametrize('case',['identity','expired','format','size'])
def test_resolved_context_conflicts(tmp_path,case):
    async def scenario():
        build,_,_=setup(tmp_path,Stream())
        manager,client=await build()
        original=manager.state.kuwo.resolve
        async def changed(identity,options):
            result=await original(identity,options)
            if case=='identity':return result.model_copy(update={'identity':TrackIdentity(providerId='kuwo',platformId='2')})
            if case=='expired':return result.model_copy(update={'validUntil':2})
            return result.model_copy(update={'representation':MediaRepresentation(container='flac') if case=='format' else MediaRepresentation(sizeBytes=3)})
        manager.state.kuwo.resolve=changed
        async with client:
            job=manager.create(DownloadRequest(identity=TRACK));await finish(job)
            assert job.public.status=='failed' and not list(tmp_path.iterdir())
    asyncio.run(scenario())


def test_cancel_at_publication_boundary(tmp_path,monkeypatch):
    async def scenario():
        from app import downloads
        build,_,_=setup(tmp_path,Stream())
        manager,client=await build()
        original=downloads.audio_format
        job=None
        def cancel_before_publish(raw):
            # 子协程正准备发布时父任务收到取消，模拟wait_for的取消传播竞争。
            manager.update(job,status='cancelled')
            job.worker.cancel()
            return original(raw)
        monkeypatch.setattr(downloads,'audio_format',cancel_before_publish)
        async with client:
            job=manager.create(DownloadRequest(identity=TRACK));await finish(job)
            assert job.public.status=='cancelled' and not list(tmp_path.iterdir())
    asyncio.run(scenario())


@pytest.mark.parametrize('address,allowed',[('1.1.1.1',True),('127.0.0.1',False)])
def test_native_m10_keeps_dns_boundary(monkeypatch,address,allowed):
    async def scenario():
        from app.media_stream import validate_target
        from app.core.errors import CoreError
        async def resolve(*args,**kwargs):return [(2,1,6,'',(address,443))]
        monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',resolve)
        if allowed:await validate_target('https://m10.music.126.net/sample','netease')
        else:
            with pytest.raises(CoreError):await validate_target('https://m10.music.126.net/sample','netease')
        with pytest.raises(CoreError):await validate_target('https://m10.music.126.net.evil.test/sample','netease')
    asyncio.run(scenario())
