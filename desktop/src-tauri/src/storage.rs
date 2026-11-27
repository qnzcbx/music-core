use rusqlite::{params, Connection, OpenFlags, OptionalExtension, Transaction};
use std::{
    path::Path,
    sync::{Arc, Mutex, MutexGuard},
    time::Duration,
};

const SCHEMA: &str = include_str!("storage.sql");

#[derive(Clone)]
pub(crate) struct Database(Arc<Mutex<Connection>>);

impl Database {
    pub(crate) fn open(path: &Path) -> Result<Self, Box<dyn std::error::Error>> {
        let exists = path.try_exists()?;
        if !exists {
            std::fs::create_dir_all(path.parent().ok_or("invalid database path")?)?;
        }
        let flags = if exists {
            OpenFlags::SQLITE_OPEN_READ_WRITE
        } else {
            OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_CREATE
        };
        let mut connection = Connection::open_with_flags(path, flags)?;
        connection.pragma_update(None, "foreign_keys", true)?;
        connection.busy_timeout(Duration::from_millis(500))?;
        if exists {
            // 打开时验证已有结构和完整性，不修补或覆盖原库。
            let expected = Connection::open_in_memory()?;
            expected.execute_batch(SCHEMA)?;
            let version: u32 = connection.pragma_query_value(None, "user_version", |r| r.get(0))?;
            if version != 1 || objects(&connection)? != objects(&expected)? {
                return Err(format!("不受支持的桌面数据库结构：{}", path.display()).into());
            }
            let integrity: String =
                connection.query_row("PRAGMA quick_check(1)", [], |row| row.get(0))?;
            if integrity != "ok" {
                return Err(format!("桌面数据库损坏：{} ({integrity})", path.display()).into());
            }
        } else {
            initialize(&mut connection)?;
        }
        Ok(Self(Arc::new(Mutex::new(connection))))
    }

    pub(crate) fn lock(&self) -> MutexGuard<'_, Connection> {
        self.0.lock().unwrap()
    }

    #[cfg(test)]
    pub(crate) fn memory() -> Self {
        let mut connection = Connection::open_in_memory().unwrap();
        connection
            .pragma_update(None, "foreign_keys", true)
            .unwrap();
        initialize(&mut connection).unwrap();
        Self(Arc::new(Mutex::new(connection)))
    }
}

fn initialize(connection: &mut Connection) -> rusqlite::Result<()> {
    let tx = connection.transaction()?;
    tx.execute_batch(SCHEMA)?;
    tx.commit()
}

fn objects(connection: &Connection) -> rusqlite::Result<Vec<String>> {
    let mut query = connection.prepare(
        "SELECT sql FROM sqlite_schema WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY name",
    )?;
    let rows = query.query_map([], |row| row.get(0))?;
    rows.collect()
}

pub(crate) fn path_text(path: &Path) -> Option<&str> {
    path.is_absolute().then(|| path.to_str()).flatten()
}

pub(crate) fn file_id(tx: &Transaction<'_>, path: &str, key: &str) -> rusqlite::Result<i64> {
    if let Some(id) = tx
        .query_row(
            "SELECT file_id FROM local_files WHERE path=?1",
            [path],
            |row| row.get(0),
        )
        .optional()?
    {
        return Ok(id);
    }
    tx.execute(
        "INSERT INTO local_files(path,stored_path_key) VALUES (?1,?2)",
        params![path, key],
    )?;
    Ok(tx.last_insert_rowid())
}

pub(crate) fn prune_files(tx: &Transaction<'_>) -> rusqlite::Result<()> {
    tx.execute(
        "DELETE FROM local_files WHERE manual=0
         AND NOT EXISTS(SELECT 1 FROM downloads d WHERE d.file_id=local_files.file_id)
         AND NOT EXISTS(SELECT 1 FROM directory_files m WHERE m.file_id=local_files.file_id)",
        [],
    )?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn current_schema_reopens_and_unsupported_database_is_left_intact() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("music-core.sqlite3");
        let db = Database::open(&path).unwrap();
        assert!(db
            .lock()
            .pragma_query_value(None, "foreign_keys", |r| r.get::<_, bool>(0))
            .unwrap());
        for table in [
            "local_files",
            "library_directories",
            "directory_files",
            "downloads",
            "excluded_files",
            "download_settings",
            "track_resources",
            "covers",
        ] {
            assert!(db
                .lock()
                .query_row(
                    "SELECT EXISTS(SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?1)",
                    [table],
                    |row| row.get::<_, bool>(0)
                )
                .unwrap());
        }
        drop(db);
        drop(Database::open(&path).unwrap());
        let altered = Connection::open(&path).unwrap();
        altered
            .execute_batch("DROP INDEX downloads_by_track")
            .unwrap();
        drop(altered);
        let before = std::fs::read(&path).unwrap();
        assert!(Database::open(&path)
            .err()
            .unwrap()
            .to_string()
            .contains("不受支持"));
        assert_eq!(std::fs::read(&path).unwrap(), before);
    }
}
