from types import SimpleNamespace
import shutil
import pytest

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


def test_current_schema_and_hidden_survive_reregistration(tmp_path):
    from app.download_index import DownloadIndex
    index = DownloadIndex(tmp_path)
    with index.connect() as db:
        assert {row[1] for row in db.execute('PRAGMA table_info(files)')} == {
            'id', 'path', 'metadata', 'hidden', 'published',
        }
    path = tmp_path / 'audio.mp3'
    index.record('scanned', path)
    index.hide('scanned')
    index.naming('title_artist')
    index.setting('directory', str(tmp_path))
    reopened = DownloadIndex(tmp_path)
    reopened.record('scanned', path)
    reopened.record('scanned', path, {'title': 'fixture'}, published=True)
    assert reopened.metadata('scanned') == ({'title': 'fixture'}, True)
    assert len(reopened.published()) == 1
    assert reopened.naming() == 'title_artist'
    assert reopened.setting('directory') == str(tmp_path)
    with pytest.raises(OSError, match='索引记录'):
        reopened.hide('missing')


def test_old_schema_rejected_without_modification(tmp_path):
    import sqlite3
    from contextlib import closing
    from app.download_index import DownloadIndex
    path = tmp_path / 'downloads.sqlite3'
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE files (id TEXT PRIMARY KEY, path TEXT, metadata TEXT, hidden INTEGER)')
        db.execute("INSERT INTO files VALUES ('old', 'song.mp3', '{}', 1)")
    before = path.read_bytes()
    with pytest.raises(OSError, match='不受支持的旧结构'):
        DownloadIndex(tmp_path)
    assert path.read_bytes() == before



@pytest.mark.parametrize('aliases', [
    [('a', 'b'), ('b', 'a')],
    [('a', 'c'), ('b', 'c')],
])
def test_batch_rejects_corrupt_aliases(tmp_path, aliases):
    from app.download_index import DownloadIndex
    index = DownloadIndex(tmp_path)
    with index.connect() as db:
        db.executemany('INSERT INTO aliases VALUES (?,?)', aliases)
    with pytest.raises(OSError, match='身份索引损坏'):
        index.scanned({'candidate': tmp_path / 'candidate.mp3'})
    with pytest.raises(OSError, match='身份索引损坏'):
        index.aliases()
    with pytest.raises(OSError, match='身份索引损坏'):
        index.resolve('a')
    with index.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM files').fetchone() == (0,)


def test_batch_write_error_rolls_back_previous_chunk_and_closes_connection(tmp_path, monkeypatch):
    import sqlite3
    from app.download_index import DownloadIndex
    index = DownloadIndex(tmp_path)
    with index.connect() as db:
        db.execute('''
            CREATE TRIGGER reject_scan BEFORE INSERT ON files WHEN NEW.id = '250'
            BEGIN SELECT RAISE(ABORT, 'fixture write failure'); END
        ''')
    connect = sqlite3.connect
    connections = []

    def capture(*args, **kwargs):
        db = connect(*args, **kwargs)
        connections.append(db)
        return db

    monkeypatch.setattr(sqlite3, 'connect', capture)
    with pytest.raises(OSError, match='下载索引不可读写'):
        index.scanned({str(i): tmp_path / f'{i}.mp3' for i in range(251)})
    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        connections[0].execute('SELECT 1')
    with index.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM files').fetchone() == (0,)
