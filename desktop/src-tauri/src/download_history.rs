//! 只记录本应用实际发布的成品，不发现或扫描目录中的其他文件。
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::BTreeSet,
    io::Write,
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

#[derive(Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Stored {
    directory: Option<PathBuf>,
    #[serde(default)]
    records: Vec<SavedDownload>,
    #[serde(default, skip_serializing_if = "BTreeSet::is_empty")]
    excluded_songs: BTreeSet<String>,
}

pub struct History {
    path: PathBuf,
    default_directory: PathBuf,
    stored: Stored,
}

pub(crate) fn write_snapshot(path: &Path, value: &impl Serialize) -> Result<(), String> {
    let parent = path.parent().ok_or("download_history_unavailable")?;
    std::fs::create_dir_all(parent).map_err(|_| "download_history_unavailable")?;
    // 同目录临时文件同步后原子替换；失败不修改内存快照，也不覆盖成品。
    let mut temporary =
        tempfile::NamedTempFile::new_in(parent).map_err(|_| "download_history_unavailable")?;
    serde_json::to_writer_pretty(&mut temporary, value)
        .map_err(|_| "download_history_unavailable")?;
    temporary
        .flush()
        .map_err(|_| "download_history_unavailable")?;
    temporary
        .as_file()
        .sync_all()
        .map_err(|_| "download_history_unavailable")?;
    temporary
        .persist(path)
        .map_err(|_| "download_history_unavailable")?;
    Ok(())
}

impl History {
    pub fn open(path: PathBuf, default_directory: PathBuf) -> Result<Self, String> {
        let stored = match std::fs::read(&path) {
            Ok(bytes) => serde_json::from_slice(&bytes).map_err(|_| "download_history_invalid")?,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Stored::default(),
            Err(_) => return Err("download_history_unavailable".into()),
        };
        Ok(Self {
            path,
            default_directory,
            stored,
        })
    }

    pub fn directory(&self) -> &Path {
        self.stored
            .directory
            .as_deref()
            .unwrap_or(&self.default_directory)
    }

    pub fn default_directory(&self) -> &Path {
        &self.default_directory
    }

    pub fn using_default(&self) -> bool {
        self.stored.directory.is_none()
    }

    fn commit(&mut self, next: Stored) -> Result<(), String> {
        write_snapshot(&self.path, &next)?;
        self.stored = next;
        Ok(())
    }

    pub fn set_directory(&mut self, directory: Option<PathBuf>) -> Result<(), String> {
        let target = directory.as_deref().unwrap_or(&self.default_directory);
        if !target.is_absolute() {
            return Err("invalid_input".into());
        }
        std::fs::create_dir_all(target).map_err(|_| "file_io_error")?;
        // 仅检测所选目录可写；不枚举、不迁移任何文件。
        let probe = tempfile::NamedTempFile::new_in(target).map_err(|_| "file_io_error")?;
        drop(probe);
        let mut next = self.stored.clone();
        next.directory = directory;
        self.commit(next)
    }

    pub fn add(&mut self, record: SavedDownload) -> Result<(), String> {
        // 成品已经正式发布才能入历史；不收临时文件或仅探查的资源。
        let metadata = std::fs::metadata(&record.path).map_err(|_| "file_io_error")?;
        if !record.path.is_absolute()
            || !metadata.is_file()
            || metadata.len() == 0
            || metadata.len() != record.size_bytes
        {
            return Err("source_verification_failed".into());
        }
        let mut next = self.stored.clone();
        next.excluded_songs
            .remove(&crate::local_library::path_key(&record.path));
        next.records.push(record);
        self.commit(next)
    }

    pub fn list(&self) -> Vec<SavedDownload> {
        self.stored.records.iter().rev().cloned().collect()
    }

    pub fn find(&self, id: &str) -> Result<&SavedDownload, String> {
        self.stored
            .records
            .iter()
            .find(|r| r.id == id)
            .ok_or_else(|| "track_not_found".into())
    }

    pub fn excluded_songs(&self) -> &BTreeSet<String> {
        &self.stored.excluded_songs
    }

    pub fn restore_songs(&mut self, ids: &[String]) -> Result<(), String> {
        if !ids.iter().any(|id| self.stored.excluded_songs.contains(id)) {
            return Ok(());
        }
        let mut next = self.stored.clone();
        for id in ids {
            next.excluded_songs.remove(id);
        }
        self.commit(next)
    }

    pub fn remove_song(&mut self, path: &Path, id: &str, delete_file: bool) -> Result<(), String> {
        if crate::local_library::path_key(path) != id || self.stored.excluded_songs.contains(id) {
            return Err("track_not_found".into());
        }
        let mut next = self.stored.clone();
        let mut expected_size = None;
        next.records.retain(|record| {
            if crate::local_library::path_key(&record.path) != id {
                return true;
            }
            expected_size = Some(record.size_bytes);
            false
        });
        next.excluded_songs.insert(id.to_owned());
        if delete_file {
            crate::local_library::delete_audio_file(path, expected_size)?;
        }
        self.commit(next)
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
    fn only_explicit_deletion_removes_the_recorded_file() {
        let root = tempfile::tempdir().unwrap();
        let config = root.path().join("history.json");
        let path = root.path().join("song.mp3");
        std::fs::write(&path, b"audio").unwrap();
        let mut history = History::open(config.clone(), root.path().to_owned()).unwrap();
        let id = crate::local_library::path_key(&path);
        history.add(record(path.clone(), false)).unwrap();
        history.add(record(path.clone(), false)).unwrap();
        history.remove_song(&path, &id, false).unwrap();
        assert!(path.is_file());

        let mut history = History::open(config.clone(), root.path().to_owned()).unwrap();
        assert!(history.list().is_empty());
        assert!(history.excluded_songs().contains(&id));
        history.add(record(path.clone(), false)).unwrap();
        assert!(!history.excluded_songs().contains(&id));
        std::fs::write(&path, b"changed contents").unwrap();
        assert!(history.remove_song(&path, &id, true).is_err());
        assert_eq!(history.list().len(), 1);
        std::fs::write(&path, b"audio").unwrap();
        history.remove_song(&path, &id, true).unwrap();
        assert!(!path.exists());
        assert!(History::open(config, root.path().to_owned())
            .unwrap()
            .list()
            .is_empty());
    }
    #[test]
    fn settings_and_actual_paths_survive_reopening_without_moving_files() {
        let root = tempfile::tempdir().unwrap();
        let file = root.path().join("config/history.json");
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
        assert_eq!(reopened.directory(), changed);
        assert_eq!(reopened.list().len(), 2);
        assert_eq!(reopened.list()[0].path, second);
        assert!(reopened.list()[0].source_preserved);
        assert_eq!(reopened.list()[1].path, first);
        assert!(first.exists() && second.exists());
        reopened.set_directory(None).unwrap();
        let reopened = History::open(file, default.clone()).unwrap();
        assert_eq!(reopened.directory(), default);
        assert!(reopened.using_default());
        assert_eq!(reopened.list().len(), 2);
    }
    #[test]
    fn failed_record_write_preserves_existing_history_and_the_actual_product() {
        let root = tempfile::tempdir().unwrap();
        let file = root.path().join("history.json");
        let product = root.path().join("saved.mp3");
        std::fs::write(&product, b"audio").unwrap();
        let mut history = History::open(file.clone(), root.path().join("music")).unwrap();
        history.add(record(product.clone(), false)).unwrap();
        let before = std::fs::read(&file).unwrap();
        std::fs::rename(&file, root.path().join("history-backup.json")).unwrap();
        std::fs::create_dir(&file).unwrap();
        assert!(history.add(record(product.clone(), false)).is_err());
        assert_eq!(history.list().len(), 1);
        assert_eq!(
            std::fs::read(root.path().join("history-backup.json")).unwrap(),
            before
        );
        assert_eq!(std::fs::read(product).unwrap(), b"audio");
    }

    #[test]
    fn incomplete_records_and_broken_storage_are_not_silently_accepted() {
        let root = tempfile::tempdir().unwrap();
        let file = root.path().join("history.json");
        let mut history = History::open(file.clone(), root.path().join("music")).unwrap();
        assert!(history
            .add(record(root.path().join("missing.mp3"), false))
            .is_err());
        assert!(history.list().is_empty());
        std::fs::write(&file, b"invalid history").unwrap();
        assert!(History::open(file, root.path().join("music")).is_err());
    }
}
