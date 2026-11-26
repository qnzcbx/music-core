use crate::{
    download_history::History,
    file_recycle::{self, FileIdentity},
    local_library::{self, Library},
};
use std::{
    collections::HashMap,
    path::PathBuf,
    time::{Duration, Instant},
};

const TTL: Duration = Duration::from_secs(120);

#[derive(Debug, Eq, PartialEq)]
pub struct Target {
    pub id: String,
    pub path: PathBuf,
    pub identity: FileIdentity,
    pub records: Vec<String>,
    revision: u64,
}

impl Target {
    pub fn resolve(
        library: &Library,
        history: &History,
        id: &str,
        protected: &[PathBuf],
    ) -> Result<Self, String> {
        if history.excluded_songs().contains(id) {
            return Err("saved_file_missing".into());
        }
        let downloads = history.list();
        let songs = library.songs(downloads.clone());
        let song = songs.get(id).ok_or("saved_file_missing")?;
        let records: Vec<_> = downloads
            .iter()
            .filter(|row| local_library::path_key(&row.path) == id)
            .collect();
        let mut registered = records
            .iter()
            .filter_map(|row| row.file_identity.as_ref())
            .chain(library.registered_identity(id));
        let expected = registered
            .next()
            .ok_or("local_recycle_identity_unavailable")?;
        if !registered.all(|identity| identity == expected) {
            return Err("local_recycle_changed".into());
        }
        file_recycle::verify(&song.path, expected, protected)?;
        Ok(Self {
            id: id.to_owned(),
            path: song.path.clone(),
            identity: expected.clone(),
            records: records
                .into_iter()
                .map(|record| record.id.clone())
                .collect(),
            revision: library.revision,
        })
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
                file_identity: None,
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
        let target = || Target::resolve(&library, &history, &id, &[]).unwrap();
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
        assert!(Target::resolve(&library, &history, "invalid", &[]).is_err());
        let target = Target::resolve(&library, &history, &id, &[]).unwrap();
        let mut record = history.list().pop().unwrap();
        record.id = "another-download".into();
        history.add(record).unwrap();
        let updated = Target::resolve(&library, &history, &id, &[]).unwrap();
        assert_ne!(updated, target);
        std::fs::write(&target.path, b"change").unwrap();
        assert_eq!(
            Target::resolve(&library, &history, &id, &[]).unwrap_err(),
            "local_recycle_changed"
        );
    }

    #[test]
    fn failed_history_write_reconciles_without_touching_path_again() {
        let (dir, library, mut history, id) = fixture();
        let target = Target::resolve(&library, &history, &id, &[]).unwrap();
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
