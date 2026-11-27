"""跨音乐库的轻量索引：只保存定位和展示信息，文件身份仍由现有指纹验证。"""
from contextlib import closing, contextmanager
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl


def safe_cover(value):
    if not value or len(value) > 2048:
        return None
    try:
        url = urlsplit(value)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
            return None
        if any(any(word in key.lower() for word in ('token', 'auth', 'sig', 'cookie', 'key', 'expires')) for key, _ in parse_qsl(url.query)):
            return None
        if url.path.lower().endswith(('.mp3', '.flac', '.m4a', '.ogg', '.m3u8')) or '/api/playback/' in url.path:
            return None
        return value
    except ValueError:
        return None


def alias_origins(rows):
    successors = dict(rows)
    predecessors = {new: old for old, new in rows}
    if len(predecessors) != len(successors):
        raise OSError('音乐库身份索引损坏')
    origins = {}
    for origin in successors.keys() - predecessors.keys():
        current = origin
        while current in successors:
            current = successors[current]
            origins[current] = origin
    if len(origins) != len(successors):
        raise OSError('音乐库身份索引损坏')
    return successors, origins


class DownloadIndex:
    def __init__(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)
        self.path = Path(directory) / 'downloads.sqlite3'
        with self.connect() as db:
            columns = {row[1] for row in db.execute('PRAGMA table_info(files)')}
            if columns and not {'id', 'path', 'metadata', 'hidden', 'published'} <= columns:
                raise OSError('下载索引使用不受支持的旧结构，请检查开发数据库')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS libraries (path TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY, path TEXT NOT NULL, metadata TEXT NOT NULL,
                    hidden INTEGER NOT NULL DEFAULT 0,
                    published INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS aliases (old_id TEXT PRIMARY KEY, new_id TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        try:
            with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
                yield db
        except sqlite3.Error as reason:
            raise OSError('下载索引不可读写') from reason

    def libraries(self, *paths):
        with self.connect() as db:
            db.executemany('INSERT OR IGNORE INTO libraries VALUES (?)', [(str(p),) for p in paths])
            return [Path(row[0]) for row in db.execute('SELECT path FROM libraries')]

    def record(self, identifier, path, metadata=None, *, published=False):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO files(id,path,metadata) VALUES (?,?,?)',
                       (identifier, str(path), '{}'))
            if metadata is not None:
                db.execute('UPDATE files SET metadata=? WHERE id=?',
                           (json.dumps(metadata, ensure_ascii=False), identifier))
            if published:
                db.execute('UPDATE files SET published=1 WHERE id=?', (identifier,))

    def metadata(self, identifier):
        with self.connect() as db:
            row = db.execute('SELECT metadata,hidden FROM files WHERE id=?', (identifier,)).fetchone()
        return (json.loads(row[0]), bool(row[1])) if row else ({}, False)

    def hide(self, identifier):
        with self.connect() as db:
            result = db.execute('UPDATE files SET hidden=1 WHERE id=?', (identifier,))
            if result.rowcount != 1:
                raise OSError('未找到需要隐藏的下载索引记录')

    def naming(self, value=None):
        with self.connect() as db:
            if value is not None:
                db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('naming', value))
            row = db.execute('SELECT value FROM settings WHERE key=?', ('naming',)).fetchone()
        return row[0] if row else 'artist_title'

    def setting(self, key, value=None):
        with self.connect() as db:
            if value is not None:
                db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, value))
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else None

    def resolve(self, identifier):
        successors, _ = self.aliases()
        while identifier in successors:
            identifier = successors[identifier]
        return identifier

    def aliases(self):
        with self.connect() as db:
            return alias_origins(list(db.execute('SELECT old_id,new_id FROM aliases')))

    def scanned(self, paths):
        if not paths:
            return {}
        with self.connect() as db:
            entries = list(paths.items())
            # 每个条目绑定两个参数，在 SQLite 的传统参数上限内分批执行。
            for offset in range(0, len(entries), 250):
                batch = entries[offset:offset + 250]
                values = ','.join("(?,?,'{}')" for _ in batch)
                parameters = [value for identifier, path in batch for value in (identifier, str(path))]
                db.execute(f'INSERT OR IGNORE INTO files(id,path,metadata) VALUES {values}', parameters)
            successors, origins = alias_origins(list(db.execute('SELECT old_id,new_id FROM aliases')))
            identifiers = [identifier for identifier in paths if identifier not in successors]
            visible = {}
            for offset in range(0, len(identifiers), 500):
                batch = identifiers[offset:offset + 500]
                parameters = ','.join('?' for _ in batch)
                rows = db.execute(
                    f'SELECT id,metadata FROM files WHERE hidden=0 AND id IN ({parameters})', batch
                )
                for identifier, metadata in rows:
                    visible[identifier] = (origins.get(identifier, identifier), json.loads(metadata))
            return visible

    def relocated(self, old, new, path, metadata, hidden):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO files(id,path,metadata,hidden,published) VALUES (?,?,?,?,1)', (new, str(path), json.dumps(metadata), int(hidden)))
            db.execute('INSERT OR REPLACE INTO aliases VALUES (?,?)', (old, new))

    def published(self):
        with self.connect() as db:
            return list(db.execute('SELECT id,path,metadata,hidden FROM files WHERE published=1'))
