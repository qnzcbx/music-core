use crate::{
    download_history::History,
    file_recycle::{self, FileIdentity},
    local_library::{self, Library},
};
use std::{
    collections::HashMap,
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

const TTL: Duration = Duration::from_secs(120);

#[derive(Debug, Eq, PartialEq)]
pub struct Target {
    pub id: String,
    pub path: PathBuf,
    pub identity: FileIdentity,
    pub records: Vec<String>,
}

impl Target {
    pub fn resolve(
        library: &Library,
        history: &History,
        id: &str,
        path_hint: Option<&Path>,
        protected: &[PathBuf],
    ) -> Result<Self, String> {
        if history.excluded_songs().contains(id) {
            return Err("saved_file_missing".into());
        }
        // 曲库可能展示已规范化的 ID，而历史保留原始路径拼写。
        // 仅用已知记录的路径作提示，最终仍以规范化 ID 和文件实例为准。
        let hint_key = path_hint.map(local_library::key).filter(|key| key != id);
        let records: Vec<_> = history
            .records()
            .filter(|row| {
                let key = local_library::key(&row.path);
                key == id || hint_key.as_ref() == Some(&key)
            })
            .collect();
        let hinted_path = hint_key.as_deref().and_then(|key| {
            records
                .iter()
                .find(|row| local_library::key(&row.path) == key)
                .map(|row| row.path.as_path())
                .or_else(|| library.stored_path(key))
        });
        let path = hinted_path
            .or_else(|| records.first().map(|record| record.path.as_path()))
            .or_else(|| library.stored_path(id))
            .ok_or("saved_file_missing")?;
        let identity = file_recycle::snapshot(path, protected)?;
        if local_library::path_key(path) != id {
            return Err("local_recycle_changed".into());
        }
        Ok(Self {
            id: id.to_owned(),
            path: path.to_owned(),
            identity,
            records: records
                .into_iter()
                .map(|record| record.id.clone())
                .collect(),
        })
    }
    pub fn execute(
        self,
        library: &Library,
        history: &mut History,
        protected: &[PathBuf],
    ) -> Result<bool, String> {
        let current = Self::resolve(library, history, &self.id, Some(&self.path), protected)?;
        if current != self {
            return Err("local_recycle_changed".into());
        }
        file_recycle::recycle(&self.path, &self.identity, protected)?;
        let absent = std::fs::symlink_metadata(&self.path)
            .is_err_and(|error| error.kind() == std::io::ErrorKind::NotFound);
        Ok(history.complete_recycle(&self.id, &self.records, absent))
    }
}

#[derive(Default)]
pub struct Plans(HashMap<String, (Instant, Target)>);

impl Plans {
    pub fn prepare(&mut self, target: Target) -> String {
        let now = Instant::now();
        self.0
            .retain(|_, (expires, old)| *expires > now && old.id != target.id);
        if self.0.len() >= 64 {
            if let Some(oldest) = self
                .0
                .iter()
                .min_by_key(|(_, (expires, _))| *expires)
                .map(|(token, _)| token.clone())
            {
                self.0.remove(&oldest);
            }
        }
        let token = uuid::Uuid::new_v4().simple().to_string();
        self.0.insert(token.clone(), (now + TTL, target));
        token
    }

    pub fn cancel(&mut self, token: &str) {
        self.0.remove(token);
    }

    pub fn take(&mut self, token: &str) -> Result<Target, &'static str> {
        self.0
            .remove(token)
            .filter(|(expires, _)| *expires > Instant::now())
            .map(|(_, target)| target)
            .ok_or("local_recycle_plan_invalid")
    }
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;
    use crate::download_history::SavedDownload;

    fn fixture() -> (tempfile::TempDir, Library, History, String) {
        let dir = tempfile::tempdir().unwrap();
        let library = Library::open(dir.path().join("library.json")).unwrap();
        let mut history =
            History::open(dir.path().join("downloads.json"), dir.path().to_owned()).unwrap();
        let path = dir.path().join("audio.mp3");
        std::fs::write(&path, b"sample").unwrap();
        let id = local_library::path_key(&path);
        history
            .add(SavedDownload {
                id: "download".into(),
                identity: serde_json::Value::Null,
                title: "sample".into(),
                artist: String::new(),
                path,
                format: "mp3".into(),
                size_bytes: 6,
                saved_at: 1,
                source_preserved: false,
            })
            .unwrap();
        (dir, library, history, id)
    }

    #[test]
    fn plans_are_one_time_cancelable_and_expire() {
        let (_dir, library, history, id) = fixture();
        let target = || Target::resolve(&library, &history, &id, None, &[]).unwrap();
        let mut plans = Plans::default();
        let first = plans.prepare(target());
        let second = plans.prepare(target());
        assert!(plans.take(&first).is_err());
        assert_eq!(plans.take(&second).unwrap(), target());
        assert!(plans.take(&second).is_err());
        let cancelled = plans.prepare(target());
        plans.cancel(&cancelled);
        assert!(plans.take(&cancelled).is_err());
        assert_eq!(std::fs::read(&target().path).unwrap(), b"sample");
        let expired = plans.prepare(target());
        plans.0.get_mut(&expired).unwrap().0 = Instant::now() - Duration::from_secs(1);
        assert!(plans.take(&expired).is_err());
    }

    #[test]
    fn resolution_rejects_missing_ids_and_changed_records() {
        let (_dir, library, mut history, id) = fixture();
        assert!(Target::resolve(&library, &history, "invalid", None, &[]).is_err());
        let target = Target::resolve(&library, &history, &id, None, &[]).unwrap();
        let mut record = history.list().pop().unwrap();
        record.id = "another-download".into();
        history.add(record).unwrap();
        assert_eq!(
            target.execute(&library, &mut history, &[]),
            Err("local_recycle_changed".into())
        );
        assert_eq!(history.list().len(), 2);
    }

    #[tokio::test]
    async fn unrelated_downloads_refresh_and_directory_removal_do_not_change_target() {
        let (dir, _library, mut history, id) = fixture();
        let other = dir.path().join("other");
        std::fs::create_dir(&other).unwrap();
        let config = dir.path().join("library.json");
        std::fs::write(
            &config,
            serde_json::to_vec(&serde_json::json!({
                "manual": [],
                "directories": [{"id":"other", "path":other, "files":[]}]
            }))
            .unwrap(),
        )
        .unwrap();
        let library = std::sync::Mutex::new(Library::open(config).unwrap());
        let before = Target::resolve(&library.lock().unwrap(), &history, &id, None, &[]).unwrap();
        let other_song = other.join("different.mp3");
        let mut audio = vec![0; 417 * 20];
        for frame in audio.chunks_exact_mut(417) {
            frame[..4].copy_from_slice(&[255, 251, 144, 0]);
        }
        std::fs::write(&other_song, &audio).unwrap();
        let mut record = history.list().pop().unwrap();
        record.id = "unrelated-download".into();
        record.path = other_song;
        record.size_bytes = audio.len() as u64;
        history.add(record).unwrap();
        local_library::change(
            &library,
            &serde_json::json!({"action":"refresh","id":"other"}),
        )
        .await
        .unwrap();
        local_library::change(
            &library,
            &serde_json::json!({"action":"remove","id":"other"}),
        )
        .await
        .unwrap();
        assert_eq!(
            Target::resolve(&library.lock().unwrap(), &history, &id, None, &[]).unwrap(),
            before
        );
    }

    #[test]
    fn failed_history_write_reconciles_without_touching_path_again() {
        let (dir, library, mut history, id) = fixture();
        let target = Target::resolve(&library, &history, &id, None, &[]).unwrap();
        let config = dir.path().join("downloads.json");
        std::fs::rename(&config, dir.path().join("backup.json")).unwrap();
        std::fs::create_dir(&config).unwrap();
        assert!(!history.complete_recycle(&id, &target.records, false));
        assert!(history.list().is_empty());
        std::fs::write(&target.path, b"new file").unwrap();
        std::fs::remove_dir(&config).unwrap();
        assert!(history.reconcile());
        assert_eq!(std::fs::read(&target.path).unwrap(), b"new file");
        let reopened = History::open(config, dir.path().to_owned()).unwrap();
        assert!(reopened.list().is_empty());
        assert!(!reopened.excluded_songs().contains(&id));
    }
}
