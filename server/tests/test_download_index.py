from types import SimpleNamespace
import shutil

from app.downloads import DownloadManager, DownloadSettings, DownloadTask, Job
from app.models import TrackIdentity, MediaRepresentation
from app.download_index import safe_cover


def manager(root, data):
    root.mkdir(exist_ok=True)
    return DownloadManager(SimpleNamespace(), DownloadSettings(directory=root, data_directory=data))


def test_libraries_identity_metadata_and_missing(tmp_path):
    a, b, data = (tmp_path / name for name in ('音乐 A', 'Music B', 'data'))
    first = manager(a, data)
    old = a / 'same.mp3'
    old.write_bytes(b'ID3' + b'x' * 100)
    row = next(row for row in first.files() if row.filename == 'same.mp3')
    first.index.record(row.fileId, old, {'title': '标题', 'album': '专辑', 'cover': 'https://example.test/a.jpg'})
    second = manager(b, data)
    shutil.copyfile(old, b / old.name)
    rows = [r for r in second.files() if r.filename == old.name]
    assert len(rows) == 2
    assert len({r.fileId for r in rows}) == 2
    assert next(r for r in rows if r.fileId == row.fileId).album == '专辑'
    assert second.find_file(row.fileId)[0] == old
    second.remove_file(row.fileId, False)
    assert old.exists()
    assert row.fileId not in {r.fileId for r in manager(b, data).files()}
    old.unlink()
    import pytest
    with pytest.raises(FileNotFoundError):
        second.find_file(row.fileId)
    other = next(r for r in second.files() if r.filename == old.name)
    second.remove_file(other.fileId, True)
    assert not (b / old.name).exists()
    imported = b / 'import.mp3'
    imported.write_bytes(b'ID3' + b'y' * 100)
    imported_id = next(r.fileId for r in second.files() if r.filename == imported.name)
    moved = a / imported.name
    imported.rename(moved)
    restarted = manager(b, data)
    with pytest.raises(FileNotFoundError):
        restarted.find_file(imported_id)
    moved_row = next(r for r in restarted.files() if r.filename == moved.name)
    assert moved_row.fileId != imported_id
    assert restarted.find_file(moved_row.fileId)[0] == moved


def test_settings_read_only_path_and_invalid_library(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    invalid = tmp_path / 'not-a-directory'
    invalid.write_text('owned test')
    app = create_app(download_settings=DownloadSettings(directory=invalid, data_directory=tmp_path / 'data'))
    with TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 1)) as client:
        value = client.get('/api/downloads/settings').json()
        assert value['directory'] == str(invalid.resolve())
        assert '不可写' in value['error']
        assert client.put('/api/downloads/settings', json={'naming': 'title', 'directory': str(tmp_path)}).status_code == 422
        assert client.put('/api/downloads/settings', json={'naming': 'title'}).status_code == 403
        assert client.put('/api/downloads/settings', json={'naming': 'title'}, headers={'X-Library-Admin':app.state.downloads.library.token}).status_code == 200


def test_naming_publish_and_restart(tmp_path):
    m = manager(tmp_path / 'library', tmp_path / 'data')
    for naming, stem in [('title', '歌名'), ('artist_title', '歌手 - 歌名'), ('title_artist', '歌名 - 歌手')]:
        m.index.naming(naming)
        for duplicate in range(2):
            part = m.root / 'own.part'
            part.write_bytes(b'ID3' + b'x' * 100)
            job = Job(DownloadTask(id=f'{naming}{duplicate}', identity=TrackIdentity(providerId='kuwo', platformId='1'),
                                  title='歌名', artist='歌手', album='专辑', status='downloading', createdAt=1, updatedAt=1), naming=m.index.naming())
            m.publish(job, part, MediaRepresentation(sizeBytes=103), 'mp3')
            assert job.public.filename == stem + (' (2)' if duplicate else '') + '.mp3'
            part.unlink()
    restarted = manager(m.root, tmp_path / 'data')
    assert restarted.index.naming() == 'title_artist'
    assert all(r.album == '专辑' for r in restarted.files() if r.filename.startswith(('歌名', '歌手')))
    assert safe_cover('https://example.test/a.jpg?token=secret') is None
