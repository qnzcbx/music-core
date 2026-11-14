import asyncio
from pathlib import Path
from types import SimpleNamespace
import httpx
from fastapi.testclient import TestClient
from app.main import create_app
from app.downloads import DownloadSettings, DownloadRequest
from test_downloads import setup, Stream, RAW, TRACK, finish


def test_web_publish_attachment_expiry_and_no_library(tmp_path):
    app = create_app(download_settings=DownloadSettings(directory=tmp_path/'temporary', data_directory=tmp_path/'data', local_mode=False))
    with TestClient(app, base_url='http://remote.example', client=('192.0.2.11', 1234)) as client:
        manager = app.state.downloads
        from app.downloads import Job, DownloadTask
        from app.models import MediaRepresentation
        manager.root.mkdir()
        part = manager.root/'own.part'
        part.write_bytes(RAW)
        job = Job(DownloadTask(id='a'*32, identity=TRACK, title='歌名', artist='歌手', deliveryMode='browser', status='downloading', createdAt=1, updatedAt=1))
        manager.publish(job, part, MediaRepresentation(sizeBytes=len(RAW)), 'mp3')
        part.unlink()
        url = job.public.artifactUrl
        response = client.get(url)
        assert response.content == RAW
        assert response.headers['content-disposition'].startswith('attachment;')
        assert "filename*=UTF-8''" in response.headers['content-disposition']
        assert client.get(url, headers={'Range':'bytes=3-7'}).content == RAW[3:8]
        assert client.head(url).headers['content-length'] == str(len(RAW))
        assert client.get('/api/downloads/files').json() == []
        assert 'directory' not in client.get('/api/downloads/settings').json()
        assert client.post('/api/downloads/settings/directory', json={'location':'music'}).status_code == 403
        assert client.get('/api/downloads/'+'b'*32+'/artifact').status_code == 410
        assert not manager.index.published()
        assert manager.index.libraries() == []
        artifact = manager.artifacts.entries[job.public.id]
        artifact.expires = 0
        manager.readers[artifact.identifier] = 1
        manager.artifacts.sweep(manager.readers)
        assert artifact.path.exists()
        assert client.get(url).status_code == 410
        manager.readers.clear()
        manager.artifacts.sweep(manager.readers)
        assert not artifact.path.exists()


def test_web_download_reuses_pipeline(tmp_path):
    async def scenario():
        build, _, _ = setup(tmp_path/'web', Stream(), local_mode=False)
        manager, client = await build()
        async with client:
            task = manager.create(DownloadRequest(identity=TRACK, title='测试'))
            await finish(task)
            assert task.public.status == 'completed'
            assert task.public.deliveryMode == 'browser'
            assert manager.artifacts.get(task.public.id)
            assert manager.files() == []
            assert not manager.index.published()
    asyncio.run(scenario())


def test_old_web_session_cleanup_is_bounded(tmp_path):
    import os
    from app.download_delivery import BrowserArtifacts
    owned = tmp_path / ('web-999999-' + 'a'*32)
    owned.mkdir()
    temporary = owned / 'finished.mp3'
    temporary.write_bytes(RAW)
    os.utime(temporary, (0, 0))
    unrelated = tmp_path / 'personal'
    unrelated.mkdir()
    (unrelated/'keep.mp3').write_bytes(RAW)
    store = BrowserArtifacts(1)
    store.clean_old_processes(tmp_path, lambda pid: True)
    assert temporary.exists()
    store.clean_old_processes(tmp_path, lambda pid: False)
    assert not owned.exists() and (unrelated/'keep.mp3').exists()
