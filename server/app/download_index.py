"""跨音乐库的轻量索引：只保存定位和展示信息，文件身份仍由现有指纹验证。"""
from contextlib import contextmanager
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


class DownloadIndex:
    def __init__(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)
        self.path = Path(directory) / 'downloads.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS libraries (path TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY, path TEXT NOT NULL, metadata TEXT NOT NULL,
                    hidden INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS aliases (old_id TEXT PRIMARY KEY, new_id TEXT NOT NULL);
            ''')
            if 'published' not in {row[1] for row in db.execute('PRAGMA table_info(files)')}:
                db.execute('ALTER TABLE files ADD COLUMN published INTEGER NOT NULL DEFAULT 0')
                # 06 旧版本仅发布下载时写入非空元数据；普通扫描一直是 {}。
                db.execute("UPDATE files SET published=1 WHERE metadata <> '{}'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        except sqlite3.Error as reason:
            raise OSError('下载索引不可读写') from reason
        finally:
            db.close()

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
            db.execute('UPDATE files SET hidden=1 WHERE id=?', (identifier,))

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
        with self.connect() as db:
            seen = set()
            while identifier not in seen:
                seen.add(identifier)
                row = db.execute('SELECT new_id FROM aliases WHERE old_id=?', (identifier,)).fetchone()
                if not row:
                    return identifier
                identifier = row[0]
        raise OSError('音乐库身份索引损坏')

    def public_id(self, identifier):
        with self.connect() as db:
            rows = list(db.execute('SELECT old_id,new_id FROM aliases'))
        # 展示最初的 ID，使既有本地队列、隐藏记录和续播继续匹配。
        while True:
            previous = next((old for old, new in rows if new == identifier), None)
            if previous is None:
                return identifier
            identifier = previous

    def relocated(self, old, new, path, metadata, hidden):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO files(id,path,metadata,hidden,published) VALUES (?,?,?,?,1)', (new, str(path), json.dumps(metadata), int(hidden)))
            db.execute('INSERT OR REPLACE INTO aliases VALUES (?,?)', (old, new))

    def published(self):
        with self.connect() as db:
            return list(db.execute('SELECT id,path,metadata,hidden FROM files WHERE published=1'))
