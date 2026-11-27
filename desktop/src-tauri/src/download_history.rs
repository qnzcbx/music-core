//! 只记录本应用实际发布的成品，不发现或扫描目录中的其他文件。
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::BTreeSet,
    path::{Path, PathBuf},
};

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SavedDownload {
    pub id: String,
    pub identity: Value,
    pub title: String,
    pub artist: String,
    pub path: PathBuf,
    pub format: String,
    pub size_bytes: u64,
    pub saved_at: u64,
    pub source_preserved: bool,
}

use crate::{
    local_library,
    storage::{self, Database},
};
use rusqlite::{params, Connection, Transaction};

const UNAVAILABLE: &str = "download_history_unavailable";
const RECORDS: &str = "SELECT d.download_id,d.provider_id,d.platform_id,d.title,d.artist,
    f.path,d.format,d.size_bytes,d.saved_at,d.source_preserved
    FROM downloads d JOIN local_files f ON f.file_id=d.file_id";

pub struct History {
    pub(crate) db: Database,
    default_directory: PathBuf,
    pending_records: BTreeSet<String>,
    pending_exclusions: BTreeSet<String>,
}

fn read_download(row: &rusqlite::Row<'_>) -> rusqlite::Result<SavedDownload> {
    Ok(SavedDownload {
        id: row.get(0)?,
        identity: serde_json::json!({"providerId":row.get::<_, String>(1)?, "platformId":row.get::<_, String>(2)?}),
        title: row.get(3)?,
        artist: row.get(4)?,
        path: PathBuf::from(row.get::<_, String>(5)?),
        format: row.get(6)?,
        size_bytes: row.get(7)?,
        saved_at: row.get(8)?,
        source_preserved: row.get(9)?,
    })
}

fn apply_reconciliation(
    tx: &Transaction<'_>,
    records: &BTreeSet<String>,
    exclusions: &BTreeSet<String>,
) -> rusqlite::Result<()> {
    let mut delete = tx.prepare_cached("DELETE FROM downloads WHERE download_id=?1")?;
    for id in records {
        delete.execute([id])?;
    }
    let mut exclude = tx.prepare_cached("INSERT OR IGNORE INTO excluded_files VALUES (?1)")?;
    for id in exclusions {
        exclude.execute([id])?;
    }
    storage::prune_files(tx)
}

impl History {
    pub(crate) fn new(db: Database, default_directory: PathBuf) -> Self {
        Self {
            db,
            default_directory,
            pending_records: BTreeSet::new(),
            pending_exclusions: BTreeSet::new(),
        }
    }

    #[cfg(test)]
    pub(crate) fn open(path: PathBuf, default_directory: PathBuf) -> Result<Self, String> {
        let db = Database::open(&path).map_err(|error| error.to_string())?;
        Ok(Self::new(db, default_directory))
    }

    pub(crate) fn transact<T>(
        &mut self,
        action: impl FnOnce(&Transaction<'_>) -> rusqlite::Result<T>,
    ) -> Result<T, String> {
        let result = (|| {
            let mut db = self.db.lock();
            let tx = db.transaction()?;
            if !self.pending_records.is_empty() || !self.pending_exclusions.is_empty() {
                apply_reconciliation(&tx, &self.pending_records, &self.pending_exclusions)?;
            }
            let value = action(&tx)?;
            tx.commit()?;
            Ok::<_, rusqlite::Error>(value)
        })()
        .map_err(|error| {
            eprintln!("桌面记录事务失败: {error}");
            UNAVAILABLE.to_owned()
        })?;
        self.pending_records.clear();
        self.pending_exclusions.clear();
        Ok(result)
    }

    pub(crate) fn settings(&self) -> Result<(Option<PathBuf>, String), String> {
        self.db
            .lock()
            .query_row(
                "SELECT directory,naming FROM download_settings WHERE singleton=1",
                [],
                |row| {
                    Ok((
                        row.get::<_, Option<String>>(0)?.map(PathBuf::from),
                        row.get(1)?,
                    ))
                },
            )
            .map_err(|_| UNAVAILABLE.into())
    }

    pub fn directory(&self) -> Result<PathBuf, String> {
        Ok(self
            .settings()?
            .0
            .unwrap_or_else(|| self.default_directory.clone()))
    }

    pub fn default_directory(&self) -> &Path {
        &self.default_directory
    }

    pub fn set_directory(&mut self, directory: Option<PathBuf>) -> Result<(), String> {
        let target = directory.as_deref().unwrap_or(&self.default_directory);
        if storage::path_text(target).is_none() {
            return Err("invalid_input".into());
        }
        std::fs::create_dir_all(target).map_err(|_| "file_io_error")?;
        drop(tempfile::NamedTempFile::new_in(target).map_err(|_| "file_io_error")?);
        self.transact(|tx| {
            tx.execute(
                "UPDATE download_settings SET directory=?1 WHERE singleton=1",
                [directory.as_deref().and_then(storage::path_text)],
            )?;
            Ok(())
        })
    }

    pub fn add(&mut self, record: SavedDownload) -> Result<(), String> {
        // 保留发布后校验，实例身份仅归删除计划所有。
        let metadata = std::fs::metadata(&record.path).map_err(|_| "file_io_error")?;
        if !metadata.is_file() || metadata.len() == 0 || metadata.len() != record.size_bytes {
            return Err("source_verification_failed".into());
        }
        let path = storage::path_text(&record.path).ok_or("source_verification_failed")?;
        let key = local_library::key(&record.path);
        let song_id = local_library::path_key(&record.path);
        let (provider, platform) =
            crate::media_cache::identity(&record.identity).ok_or("invalid_input")?;
        self.transact(|tx| {
            let file_id = storage::file_id(tx, path, &key)?;
            tx.execute(
                "INSERT INTO downloads(download_id,file_id,provider_id,platform_id,title,artist,format,size_bytes,saved_at,source_preserved)
                 VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10)",
                params![record.id,file_id,provider,platform,record.title,record.artist,
                        record.format,record.size_bytes,record.saved_at,record.source_preserved],
            )?;
            tx.execute("DELETE FROM excluded_files WHERE song_id=?1", [song_id])?;
            Ok(())
        })
    }

    fn records(
        &self,
        db: &Connection,
        predicate: &str,
        parameters: impl rusqlite::Params,
    ) -> Result<Vec<SavedDownload>, String> {
        let mut query = db
            .prepare_cached(&format!("{RECORDS} {predicate} ORDER BY d.seq DESC"))
            .map_err(|_| UNAVAILABLE)?;
        let rows = query
            .query_map(parameters, read_download)
            .map_err(|_| UNAVAILABLE)?;
        rows.filter(|row| {
            row.as_ref()
                .map_or(true, |row| !self.pending_records.contains(&row.id))
        })
        .collect::<rusqlite::Result<_>>()
        .map_err(|_| UNAVAILABLE.into())
    }

    pub fn list(&self) -> Result<Vec<SavedDownload>, String> {
        self.records(&self.db.lock(), "", [])
    }

    pub(crate) fn target_records(
        &self,
        id: &str,
        hint: Option<&str>,
    ) -> Result<Vec<SavedDownload>, String> {
        self.records(
            &self.db.lock(),
            "WHERE f.stored_path_key IN (?1, ?2)",
            params![id, hint],
        )
    }

    pub(crate) fn snapshot(
        &self,
        db: &Connection,
    ) -> Result<(Vec<SavedDownload>, BTreeSet<String>), String> {
        let mut query = db
            .prepare_cached("SELECT song_id FROM excluded_files")
            .map_err(|_| UNAVAILABLE)?;
        let mut excluded = query
            .query_map([], |row| row.get(0))
            .map_err(|_| UNAVAILABLE)?
            .collect::<rusqlite::Result<BTreeSet<String>>>()
            .map_err(|_| UNAVAILABLE)?;
        excluded.extend(self.pending_exclusions.iter().cloned());
        Ok((self.records(db, "", [])?, excluded))
    }

    pub(crate) fn is_excluded(&self, id: &str) -> Result<bool, String> {
        if self.pending_exclusions.contains(id) {
            return Ok(true);
        }
        self.db
            .lock()
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM excluded_files WHERE song_id=?1)",
                [id],
                |row| row.get(0),
            )
            .map_err(|_| UNAVAILABLE.into())
    }

    pub fn complete_recycle(&mut self, id: &str, records: &[String], hide_path: bool) -> bool {
        // 只对账已确认的 UUID；后续读写不会再次执行 Shell 操作。
        self.pending_records.extend(records.iter().cloned());
        if hide_path {
            self.pending_exclusions.insert(id.to_owned());
        }
        self.reconcile()
    }

    pub fn reconcile(&mut self) -> bool {
        (self.pending_records.is_empty() && self.pending_exclusions.is_empty())
            || self.transact(|_| Ok(())).is_ok()
    }

    pub fn remove_song(&mut self, path: &Path, id: &str, delete_file: bool) -> Result<(), String> {
        if delete_file {
            return Err("local_recycle_unavailable".into());
        }
        if local_library::path_key(path) != id || self.is_excluded(id)? {
            return Err("track_not_found".into());
        }
        let mut paths = std::collections::HashMap::new();
        let records = self
            .list()?
            .into_iter()
            .filter_map(|row| {
                let key = paths
                    .entry(row.path.clone())
                    .or_insert_with(|| local_library::path_key(&row.path));
                (key == id).then_some(row.id)
            })
            .collect();
        self.transact(|tx| apply_reconciliation(tx, &records, &BTreeSet::from([id.to_owned()])))
    }

    #[cfg(test)]
    pub(crate) fn reject_writes(&self, reject: bool) {
        self.db
            .lock()
            .pragma_update(None, "query_only", reject)
            .unwrap();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn record(path: PathBuf, fallback: bool) -> SavedDownload {
        SavedDownload {
            id: uuid::Uuid::new_v4().simple().to_string(),
            identity: serde_json::json!({"providerId":"qq","platformId":"fixture"}),
            title: "歌曲".into(),
            artist: "歌手".into(),
            format: "mp3".into(),
            size_bytes: 5,
            saved_at: 123,
            source_preserved: fallback,
            path,
        }
    }

    #[test]
    fn record_removal_preserves_audio_and_excludes_all_records_for_path() {
        let root = tempfile::tempdir().unwrap();
        let config = root.path().join("music-core.sqlite3");
        let path = root.path().join("song.mp3");
        std::fs::write(&path, b"audio").unwrap();
        let mut history = History::open(config.clone(), root.path().to_owned()).unwrap();
        let id = crate::local_library::path_key(&path);
        history.add(record(path.clone(), false)).unwrap();
        history.add(record(path.clone(), false)).unwrap();
        history.remove_song(&path, &id, false).unwrap();
        assert_eq!(std::fs::read(&path).unwrap(), b"audio");

        let mut history = History::open(config.clone(), root.path().to_owned()).unwrap();
        assert!(history.list().unwrap().is_empty());
        assert!(history.is_excluded(&id).unwrap());
        history.add(record(path.clone(), false)).unwrap();
        assert!(!history.is_excluded(&id).unwrap());
        assert_eq!(
            History::open(config, root.path().to_owned())
                .unwrap()
                .list()
                .unwrap()
                .len(),
            1
        );
    }
    #[test]
    fn physical_removal_is_refused_without_touching_file_or_records() {
        let root = tempfile::tempdir().unwrap();
        let config = root.path().join("music-core.sqlite3");
        let path = root.path().join("song.mp3");
        std::fs::write(&path, b"audio").unwrap();
        let id = crate::local_library::path_key(&path);
        let mut history = History::open(config.clone(), root.path().to_owned()).unwrap();
        history.add(record(path.clone(), false)).unwrap();
        assert_eq!(
            history.remove_song(&path, &id, true),
            Err("local_recycle_unavailable".into())
        );
        assert_eq!(std::fs::read(&path).unwrap(), b"audio");
        assert_eq!(history.list().unwrap().len(), 1);
        assert!(!history.is_excluded(&id).unwrap());
        assert_eq!(
            History::open(config, root.path().to_owned())
                .unwrap()
                .list()
                .unwrap()
                .len(),
            1
        );
    }

    #[test]
    fn settings_and_actual_paths_survive_reopening_without_moving_files() {
        let root = tempfile::tempdir().unwrap();
        let file = root.path().join("config/music-core.sqlite3");
        let default = root.path().join("redirected-music/拾音");
        let other = root.path().join("outside-library");
        std::fs::create_dir_all(&default).unwrap();
        std::fs::create_dir_all(&other).unwrap();
        let first = default.join("song.mp3");
        let second = other.join("renamed.mp3");
        std::fs::write(&first, b"audio").unwrap();
        std::fs::write(&second, b"audio").unwrap();
        let mut history = History::open(file.clone(), default.clone()).unwrap();
        history.add(record(first.clone(), false)).unwrap();
        history.add(record(second.clone(), true)).unwrap();
        let changed = root.path().join("new-default");
        history.set_directory(Some(changed.clone())).unwrap();
        let mut reopened = History::open(file.clone(), default.clone()).unwrap();
        assert_eq!(reopened.directory().unwrap(), changed);
        assert_eq!(reopened.list().unwrap().len(), 2);
        assert_eq!(reopened.list().unwrap()[0].path, second);
        assert!(reopened.list().unwrap()[0].source_preserved);
        assert_eq!(reopened.list().unwrap()[1].path, first);
        assert!(first.exists() && second.exists());
        reopened.set_directory(None).unwrap();
        let reopened = History::open(file, default.clone()).unwrap();
        assert_eq!(reopened.directory().unwrap(), default);
        assert!(reopened.settings().unwrap().0.is_none());
        assert_eq!(reopened.list().unwrap().len(), 2);
    }
    #[test]
    fn failed_record_write_preserves_existing_history_and_the_actual_product() {
        let root = tempfile::tempdir().unwrap();
        let file = root.path().join("music-core.sqlite3");
        let product = root.path().join("saved.mp3");
        std::fs::write(&product, b"audio").unwrap();
        let mut history = History::open(file.clone(), root.path().join("music")).unwrap();
        history.add(record(product.clone(), false)).unwrap();
        history.reject_writes(true);
        assert!(history.add(record(product.clone(), false)).is_err());
        assert_eq!(history.list().unwrap().len(), 1);
        history.reject_writes(false);
        assert_eq!(std::fs::read(product).unwrap(), b"audio");
    }

    #[test]
    fn remove_rolls_back_and_later_download_supersedes_pending_exclusion() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("song.mp3");
        std::fs::write(&path, b"audio").unwrap();
        let public_id = local_library::path_key(&path);
        let mut history = History::new(Database::memory(), root.path().into());
        let previous = record(path.clone(), false);
        let previous_id = previous.id.clone();
        history.add(previous).unwrap();
        history
            .db
            .lock()
            .execute_batch(
                "CREATE TEMP TRIGGER refuse_exclusion BEFORE INSERT ON excluded_files
             BEGIN SELECT RAISE(ABORT, 'exclude failed'); END;",
            )
            .unwrap();
        assert!(history.remove_song(&path, &public_id, false).is_err());
        assert_eq!(history.list().unwrap()[0].id, previous_id);
        assert!(!history.is_excluded(&public_id).unwrap());
        assert_eq!(std::fs::read(&path).unwrap(), b"audio");

        assert!(!history.complete_recycle(&public_id, &[previous_id], true));
        assert!(history.list().unwrap().is_empty());
        assert!(history.is_excluded(&public_id).unwrap());
        history
            .db
            .lock()
            .execute_batch("DROP TRIGGER refuse_exclusion")
            .unwrap();
        let replacement = record(path, false);
        let replacement_id = replacement.id.clone();
        history.add(replacement).unwrap();
        assert!(history.reconcile());
        assert!(!history.is_excluded(&public_id).unwrap());
        assert_eq!(history.list().unwrap()[0].id, replacement_id);
    }

    #[test]
    fn incomplete_records_and_broken_storage_are_not_silently_accepted() {
        let root = tempfile::tempdir().unwrap();
        let file = root.path().join("music-core.sqlite3");
        let mut history = History::open(file.clone(), root.path().join("music")).unwrap();
        assert!(history
            .add(record(root.path().join("missing.mp3"), false))
            .is_err());
        assert!(history.list().unwrap().is_empty());
        drop(history);
        std::fs::write(&file, b"invalid history").unwrap();
        assert!(History::open(file, root.path().join("music")).is_err());
    }
}
