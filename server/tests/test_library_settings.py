from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.downloads import DownloadManager, DownloadSettings, DownloadTask, Job
from app.models import TrackIdentity, MediaRepresentation
from app.library_settings import initial_directory, system_folder


def publish(manager, name='download'):
    manager.root.mkdir(parents=True, exist_ok=True)
    part = manager.root / 'owned.part'
    part.write_bytes(b'ID3' + b'x' * 100)
    job = Job(DownloadTask(id=name, identity=TrackIdentity(providerId='kuwo', platformId='1'),
                          title=name, artist='artist', album='album', status='downloading', createdAt=1, updatedAt=1), directory=manager.root)
    manager.publish(job, part, MediaRepresentation(sizeBytes=103), 'mp3')
    part.unlink()
    return job.public.fileId, manager.root / job.public.filename


def test_default_and_existing(tmp_path):
    data = tmp_path / 'data'
    legacy = tmp_path / 'legacy'
    expected = system_folder('music') if __import__('os').name == 'nt' else legacy
    assert initial_directory(data, legacy) == expected
    assert initial_directory(data, legacy) == expected.resolve()
    assert initial_directory(data, legacy, str(tmp_path / 'override')) == tmp_path / 'override'
    old = tmp_path / 'old'
    old.mkdir()
    assert initial_directory(tmp_path / 'other-data', old) == old


def test_authority_switch_and_deployment_lock(tmp_path):
    app = create_app(download_settings=DownloadSettings(directory=tmp_path / 'A', data_directory=tmp_path / 'data'))
    body = {'location': 'custom', 'path': str(tmp_path / '中文 B')}
    with TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 1)) as client:
        token = app.state.downloads.library.token
        headers = {'X-Library-Admin': token}
        assert client.post('/api/downloads/settings/directory', json=body).status_code == 403
        assert client.post('/api/downloads/settings/directory', json=body, headers={**headers, 'X-Forwarded-For': '127.0.0.1'}).status_code == 403
        assert client.post('/api/downloads/settings/directory/preview', json=body, headers=headers).status_code == 200
        assert client.post('/api/downloads/settings/directory', json=body, headers=headers).status_code == 200
        assert app.state.downloads.root == tmp_path / '中文 B'
        bad = tmp_path / 'not-dir'
        bad.write_text('owned')
        assert client.post('/api/downloads/settings/directory', json={**body, 'path':str(bad)}, headers=headers).status_code == 400
        assert app.state.downloads.root == tmp_path / '中文 B'
    assert initial_directory(tmp_path / 'data', tmp_path / 'A') == tmp_path / '中文 B'
    locked = create_app(download_settings=DownloadSettings(directory=tmp_path / 'A', data_directory=tmp_path / 'locked', deployment_locked=True))
    with TestClient(locked, base_url='http://127.0.0.1', client=('127.0.0.1', 1)) as client:
        assert client.get('/api/downloads/settings').json()['deploymentLocked']
        assert client.post('/api/downloads/settings/directory', json=body, headers={'X-Library-Admin': locked.state.downloads.library.token}).status_code == 400


def test_owned_migration_alias_hidden_collision_and_job_root(tmp_path):
    manager = DownloadManager(SimpleNamespace(), DownloadSettings(directory=tmp_path / 'A', data_directory=tmp_path / 'data'))
    original, source = publish(manager)
    personal = manager.root / 'personal.mp3'
    personal.write_bytes(b'ID3personal')
    manager.files()
    manager.remove_file(original, False)
    b = manager.library.target('custom', str(tmp_path / 'B'))
    collision = b / source.name
    collision.write_bytes(b'ID3different')
    assert len(manager.library.candidates()) == 1
    result = manager.library.change(b, True)
    assert result['results'][0]['status'] == 'moved'
    assert personal.exists() and not source.exists()
    assert collision.read_bytes() == b'ID3different'
    moved, _, _ = manager.find_file(original)
    assert moved.name.endswith('(2).mp3')
    assert original not in [row.fileId for row in manager.files()]
    assert manager.index.metadata(manager.index.resolve(original))[0]['album'] == 'album'
    c = manager.library.target('custom', str(tmp_path / 'C'))
    manager.library.change(c, True)
    assert manager.find_file(original)[0].parent == c
    manager.remove_file(original, True)
    with pytest.raises(FileNotFoundError):
        manager.find_file(original)


def test_failure_keeps_source_and_busy_refused(tmp_path, monkeypatch):
    manager = DownloadManager(SimpleNamespace(), DownloadSettings(directory=tmp_path / 'A', data_directory=tmp_path / 'data'))
    identifier, source = publish(manager)
    target = manager.library.target('custom', str(tmp_path / 'B'))
    manager.readers[identifier] = 1
    with pytest.raises(ValueError, match='正在播放'):
        manager.library.change(target, True)
    manager.readers.clear()
    monkeypatch.setattr('app.library_settings.os.link', lambda *args: (_ for _ in ()).throw(OSError('owned failure')))
    result = manager.library.change(target, True)
    assert result['results'][0]['status'] == 'failed'
    assert source.exists() and manager.find_file(identifier)[0] == source


def test_already_created_task_keeps_directory(tmp_path):
    import asyncio
    from test_downloads import setup, Stream, finish, TRACK
    from app.downloads import DownloadRequest
    async def scenario():
        a = tmp_path / 'A'
        build, _, _ = setup(a, Stream())
        manager, client = await build()
        async with client:
            job = manager.create(DownloadRequest(identity=TRACK, title='old job'))
            b = manager.library.target('custom', str(tmp_path / 'B'))
            manager.library.change(b, False)
            await finish(job)
            assert job.public.status == 'completed'
            assert (a / job.public.filename).is_file()
            assert not (b / job.public.filename).exists()
    asyncio.run(scenario())


def test_local_launcher_ticket_and_cookie_session(tmp_path):
    app = create_app(download_settings=DownloadSettings(directory=tmp_path / 'A', data_directory=tmp_path / 'data'))
    with TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 1)) as client:
        assert not client.get('/api/downloads/settings').json()['canManage']
        assert client.post('/api/downloads/settings/local-launch').status_code == 403
        header = {'X-Library-Admin': app.state.downloads.library.token}
        assert client.post('/api/downloads/settings/local-launch', headers={**header, 'Forwarded':'for=127.0.0.1'}).status_code == 403
        ticket = client.post('/api/downloads/settings/local-launch', headers=header).json()['ticket']
        response = client.post('/api/downloads/settings/local-session', json={'ticket':ticket})
        assert response.status_code == 200
        assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
        assert client.get('/api/downloads/settings').json()['canManage']
        assert client.post('/api/downloads/settings/local-session', json={'ticket':ticket}).status_code == 403
        assert client.post('/api/downloads/settings/directory', json={'location':'custom', 'path':str(tmp_path/'B')}).status_code == 200
        with TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 2)) as ordinary:
            assert not ordinary.get('/api/downloads/settings').json()['canManage']
        expired = app.state.downloads.library.issue_ticket()
        app.state.downloads.library.tickets[expired] = 0
        assert client.post('/api/downloads/settings/local-session', json={'ticket':expired}).status_code == 403
    with TestClient(app, base_url='http://music.example', client=('192.0.2.42', 1)) as remote:
        assert remote.get('/api/downloads/settings').status_code == 200
        assert not remote.get('/api/downloads/settings').json()['canManage']
        assert remote.post('/api/downloads/settings/local-launch').status_code == 403
        assert remote.post('/api/downloads/settings/directory', json={'location':'music'}).status_code == 403
