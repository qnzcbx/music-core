"""所有写入、隐藏和删除仅使用 pytest 独立临时目录。"""
import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from app.main import create_app
from app.downloads import DownloadManager, DownloadSettings


def manager(root):
    return DownloadManager(SimpleNamespace(), DownloadSettings(directory=root))


@pytest.fixture
def local(tmp_path):
    (tmp_path / '甲.mp3').write_bytes(b'ID3' + bytes(range(256)) * 512)
    app = create_app(download_settings=DownloadSettings(directory=tmp_path))
    with TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 12345)) as client:
        identifier = client.get('/api/downloads/files').json()[0]['fileId']
        yield client, identifier, tmp_path, app


def test_hidden_durable_and_replacement_visible(local):
    client, identifier, root, app = local
    target = root / '甲.mp3'
    original = target.read_bytes()
    old_info = target.stat()
    response = client.post(f'/api/downloads/files/{identifier}/remove', json={})
    assert response.json() == {'removed': True, 'fileDeleted': False}
    assert client.get('/api/downloads/files').json() == []
    assert target.read_bytes() == original
    assert manager(root).files() == []
    # 同名新实例不得继承隐藏标记；序号文件也不受影响。
    replacement = root / 'replacement.tmp'
    replacement.write_bytes(original)
    os.utime(replacement, ns=(old_info.st_atime_ns, old_info.st_mtime_ns))
    os.replace(replacement, target)
    (root / '甲 (2).mp3').write_bytes(original)
    rows = manager(root).files()
    assert len(rows) == 2 and identifier not in {r.fileId for r in rows}
    assert client.post(f'/api/downloads/files/{identifier}/remove', json={'deleteFile': True}).status_code == 404
    assert target.exists()


def test_delete_actual_and_failed_delete_retains_list(local, monkeypatch):
    client, identifier, root, app = local
    original_unlink = app.state.downloads.unlink_file
    def denied(*args): raise PermissionError()
    monkeypatch.setattr(app.state.downloads, 'unlink_file', denied)
    assert client.post(f'/api/downloads/files/{identifier}/remove', json={'deleteFile': True}).status_code == 503
    assert client.get('/api/downloads/files').json()[0]['fileId'] == identifier
    monkeypatch.setattr(app.state.downloads, 'unlink_file', original_unlink)
    assert client.post(f'/api/downloads/files/{identifier}/remove', json={'deleteFile': True}).json()['fileDeleted']
    assert not (root / '甲.mp3').exists()
    assert manager(root).files() == []
    assert client.get(f'/api/downloads/files/{identifier}/stream').status_code == 404


@pytest.mark.parametrize('value', ['bytes=99999999-', 'bytes=3-2', 'bytes=-0', 'bytes=1-2,4-5', 'items=1-2', 'bytes=-'])
def test_invalid_ranges(local, value):
    client, identifier, _, app = local
    response = client.get(f'/api/downloads/files/{identifier}/stream', headers={'Range': value})
    assert response.status_code == 416
    assert response.headers['content-range'].startswith('bytes */')
    assert app.state.downloads.readers == {}


def test_stream_head_ranges_and_cleanup(local):
    client, identifier, root, app = local
    url = f'/api/downloads/files/{identifier}/stream'
    data = (root / '甲.mp3').read_bytes()
    response = client.get(url)
    assert response.status_code == 200 and response.content == data
    assert response.headers['accept-ranges'] == 'bytes'
    assert response.headers['content-type'] == 'audio/mpeg'
    head = client.head(url)
    assert not head.content and int(head.headers['content-length']) == len(data)
    for value, expected in [('bytes=10-19', data[10:20]), ('bytes=-12', data[-12:]), ('bytes=100-', data[100:]), ('bytes=0-99999999', data)]:
        response = client.get(url, headers={'Range': value})
        assert response.status_code == 206 and response.content == expected
        assert int(response.headers['content-length']) == len(expected)
    assert app.state.downloads.readers == {}


@pytest.mark.parametrize('headers', [{'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}, {'Sec-Fetch-Site': 'same-site'}, {'Host': 'evil.example'}, {'Origin': 'null'}])
def test_cross_site_rejected(local, headers):
    client, identifier, root, _ = local
    assert client.post(f'/api/downloads/files/{identifier}/remove', json={'deleteFile': True}, headers=headers).status_code == 403
    assert client.get(f'/api/downloads/files/{identifier}/stream', headers=headers).status_code == 403
    assert (root / '甲.mp3').exists()


def test_external_client_rejected(tmp_path):
    (tmp_path / 'x.mp3').write_bytes(b'ID3test')
    app = create_app(download_settings=DownloadSettings(directory=tmp_path))
    with TestClient(app, base_url='http://127.0.0.1', client=('192.0.2.4', 80)) as client:
        identifier = client.get('/api/downloads/files').json()[0]['fileId']
        assert client.post(f'/api/downloads/files/{identifier}/remove', json={}).status_code == 403


def test_illegal_paths_and_reparse_rejected(tmp_path, monkeypatch):
    root = tmp_path / 'only'; root.mkdir()
    outside = tmp_path / 'private.mp3'; outside.write_bytes(b'ID3private')
    (root / 'folder').mkdir(); (root / 'folder' / 'nested.mp3').write_bytes(b'ID3nested')
    (root / 'text.mp3').write_bytes(b'not audio')
    m = manager(root)
    for value in ['../private.mp3', str(outside), 'folder/nested.mp3', 'abc', '0' * 64]:
        with pytest.raises(FileNotFoundError): m.remove_file(value, True)
    assert m.files() == [] and outside.exists()
    target = root / 'reparse.mp3'; target.write_bytes(b'ID3test')
    original = Path.lstat
    def reparse(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if path == target: return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info
    monkeypatch.setattr(Path, 'lstat', reparse)
    assert m.files() == []


def test_real_symlink_rejected(tmp_path):
    root = tmp_path / 'only'; root.mkdir()
    outside = tmp_path / 'outside.mp3'; outside.write_bytes(b'ID3private')
    try: (root / 'link.mp3').symlink_to(outside)
    except OSError: pytest.skip('当前 Windows 未提供创建符号链接权限')
    assert manager(root).files() == [] and outside.read_bytes() == b'ID3private'


def test_concurrent_hides(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    for i in range(6): (tmp_path / f'{i}.mp3').write_bytes(b'ID3test')
    m = manager(tmp_path); identifiers = [f.fileId for f in m.files()]
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda value: m.remove_file(value, False), identifiers))
    assert manager(tmp_path).files() == []
    assert not list(tmp_path.glob('.music-core-hidden*'))


def test_hide_write_failure_keeps_file_and_reports_failure(local):
    client, identifier, root, app = local
    target = root / '甲.mp3'
    original = target.read_bytes()
    with app.state.downloads.index.connect() as db:
        db.execute('''
            CREATE TRIGGER reject_hide BEFORE UPDATE OF hidden ON files
            BEGIN SELECT RAISE(ABORT, 'test write failure'); END
        ''')
    response = client.post(f'/api/downloads/files/{identifier}/remove', json={})
    assert response.status_code == 503
    assert client.get('/api/downloads/files').json()[0]['fileId'] == identifier
    assert target.read_bytes() == original


def test_old_hidden_json_is_ignored_and_preserved(local):
    import json
    client, identifier, root, _ = local
    legacy = root / '.music-core-hidden.json'
    old_data = json.dumps({'version': 1, 'hidden': [identifier]})
    legacy.write_text(old_data, encoding='utf-8')
    assert client.get('/api/downloads/files').json()[0]['fileId'] == identifier
    assert client.post(f'/api/downloads/files/{identifier}/remove', json={}).status_code == 200
    assert client.get('/api/downloads/files').json() == []
    assert legacy.read_text(encoding='utf-8') == old_data


def test_bounded_stream_cancel_releases_handle(tmp_path):
    target = tmp_path / 'large.flac'
    with target.open('wb') as output:
        output.write(b'fLaC'); output.truncate(64 * 1024 * 1024)
    m = manager(tmp_path); identifier = m.files()[0].fileId
    request = Request({'type': 'http', 'method': 'GET', 'headers': []})
    async def check():
        response = m.stream_file(request, identifier)
        chunk = await response.body_iterator.__anext__()
        assert len(chunk) == 65536
        with pytest.raises(BlockingIOError): m.remove_file(identifier, True)
        # ASGI 发送被取消，也必须由 OwnedStream 的 finally 释放句柄。
        async def receive(): await asyncio.sleep(100)
        async def send(message):
            if message['type'] == 'http.response.body': raise asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):
            await response({'type': 'http', 'method': 'GET', 'asgi': {'spec_version': '2.4'}}, receive, send)
        assert not m.readers
        m.remove_file(identifier, True)
    asyncio.run(check())
    assert not target.exists()



def test_disappearing_file_is_skipped_in_scan_and_lookup(tmp_path, monkeypatch):
    target = tmp_path / 'disappearing.mp3'
    target.write_bytes(b'ID3fixture')
    m = manager(tmp_path)
    identifier = m.files()[0].fileId
    original_open = Path.open

    def open_path(path, *args, **kwargs):
        if path == target:
            raise FileNotFoundError(path)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', open_path)
    assert m.files() == []
    with pytest.raises(FileNotFoundError):
        m.find_file(identifier)
