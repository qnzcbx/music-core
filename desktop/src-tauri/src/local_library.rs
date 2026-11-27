use crate::{
    download_history::{History, SavedDownload},
    storage::{self, Database},
};
use rusqlite::{params, Connection, OptionalExtension, Transaction};
use serde::Serialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Path, PathBuf},
    time::SystemTime,
};
use symphonia::core::{
    formats::FormatOptions,
    io::MediaSourceStream,
    meta::{MetadataRevision, StandardTagKey},
    probe::Hint,
};

struct Directory {
    id: String,
    path: PathBuf,
    files: Vec<PathBuf>,
}

pub(crate) struct Sources {
    manual: Vec<PathBuf>,
    directories: Vec<Directory>,
}

pub struct Library {
    media: BTreeMap<String, CachedMedia>,
}

const UNAVAILABLE: &str = "local_library_unavailable";

pub(crate) fn sources(db: &Connection) -> Result<Sources, String> {
    let read = || -> rusqlite::Result<Sources> {
        let mut manual_query = db.prepare_cached("SELECT path FROM local_files WHERE manual=1")?;
        let manual = manual_query
            .query_map([], |row| Ok(PathBuf::from(row.get::<_, String>(0)?)))?
            .collect::<rusqlite::Result<_>>()?;

        let mut directory_query =
            db.prepare_cached("SELECT directory_id,path FROM library_directories ORDER BY seq")?;
        let mut directories: Vec<Directory> = directory_query
            .query_map([], |row| {
                Ok(Directory {
                    id: row.get(0)?,
                    path: PathBuf::from(row.get::<_, String>(1)?),
                    files: Vec::new(),
                })
            })?
            .collect::<rusqlite::Result<_>>()?;
        let mut members = db.prepare_cached(
            "SELECT m.directory_id,f.path FROM directory_files m JOIN local_files f ON f.file_id=m.file_id",
        )?;
        let by_id: std::collections::HashMap<_, _> = directories
            .iter()
            .enumerate()
            .map(|(index, dir)| (dir.id.clone(), index))
            .collect();
        let mut rows = members.query([])?;
        while let Some(row) = rows.next()? {
            let id: String = row.get(0)?;
            if let Some(index) = by_id.get(&id) {
                directories[*index]
                    .files
                    .push(PathBuf::from(row.get::<_, String>(1)?));
            }
        }
        Ok(Sources {
            manual,
            directories,
        })
    };
    read().map_err(|_| UNAVAILABLE.into())
}

#[derive(Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
struct MediaFacts {
    album: Option<String>,
    duration_seconds: Option<f64>,
}

struct CachedMedia {
    size_bytes: Option<u64>,
    modified: SystemTime,
    facts: MediaFacts,
}

impl MediaFacts {
    fn read(path: &Path) -> Option<Self> {
        fn album(revision: Option<&MetadataRevision>) -> Option<String> {
            revision?.tags().iter().find_map(|tag| {
                if tag.std_key != Some(StandardTagKey::Album) {
                    return None;
                }
                let value = tag.value.to_string();
                let value = value.trim();
                (!value.is_empty()).then(|| value.to_owned())
            })
        }

        let stream =
            MediaSourceStream::new(Box::new(fs::File::open(path).ok()?), Default::default());
        let mut probed = symphonia::default::get_probe()
            .format(
                &Hint::new(),
                stream,
                &FormatOptions::default(),
                &Default::default(),
            )
            .ok()?;
        let duration_seconds = probed.format.default_track().and_then(|track| {
            let params = &track.codec_params;
            let time = params.time_base?.calc_time(params.n_frames?);
            let seconds = time.seconds as f64 + time.frac;
            (seconds > 0.0).then_some(seconds)
        });
        let album = album(probed.format.metadata().current())
            .or_else(|| album(probed.metadata.get()?.current()));
        Some(Self {
            album,
            duration_seconds,
        })
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Song {
    pub id: String,
    pub(crate) path: PathBuf,
    title: String,
    artist: String,
    pub format: &'static str,
    available: bool,
    size_bytes: Option<u64>,
    #[serde(skip)]
    modified: Option<SystemTime>,
    #[serde(flatten)]
    media: MediaFacts,
    saved_at: Option<u64>,
    source_preserved: bool,
    downloaded: bool,
    #[serde(skip)]
    pub download_identity: Option<Value>,
    manual: bool,
    directories: Vec<String>,
}

fn file_format(path: &Path) -> Option<&'static str> {
    let ext = path.extension()?.to_str()?;
    if ext.eq_ignore_ascii_case("mp3") {
        Some("mp3")
    } else if ext.eq_ignore_ascii_case("flac") {
        Some("flac")
    } else if ext.eq_ignore_ascii_case("m4a") {
        Some("m4a")
    } else {
        None
    }
}

pub(crate) fn key(path: &Path) -> String {
    let path = path.to_string_lossy().replace('/', "\\");
    let normalized = if let Some(unc) = path.strip_prefix(r"\\?\UNC\") {
        format!(r"\\{unc}")
    } else {
        path.strip_prefix(r"\\?\").unwrap_or(&path).to_string()
    };
    format!("{:x}", Sha256::digest(normalized.to_lowercase().as_bytes()))
}

#[cfg(test)]
thread_local! {
    static PATH_KEY_CALLS: std::cell::Cell<usize> = const { std::cell::Cell::new(0) };
}

pub(crate) fn path_key(path: &Path) -> String {
    #[cfg(test)]
    PATH_KEY_CALLS.with(|count| count.set(count.get() + 1));
    key(path.canonicalize().as_deref().unwrap_or(path))
}

fn playable_import(path: &Path) -> Option<PathBuf> {
    let format = file_format(path)?;
    if format == "m4a" || !path.is_file() {
        return None;
    }
    let canonical = path.canonicalize().ok()?;
    let media = crate::download_media::inspect_original(&canonical, "auto").ok()?;
    (media["extension"] == format).then_some(canonical)
}

fn link(metadata: &fs::Metadata) -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        metadata.file_attributes() & 0x400 != 0
    }
    #[cfg(not(windows))]
    metadata.file_type().is_symlink()
}

fn scan(directory: &Path) -> Result<Vec<PathBuf>, String> {
    let mut pending = vec![directory.to_owned()];
    let mut files = Vec::new();
    while let Some(path) = pending.pop() {
        for entry in fs::read_dir(path).map_err(|_| "local_directory_unavailable")? {
            let entry = entry.map_err(|_| "local_directory_unavailable")?;
            let path = entry.path();
            let metadata =
                fs::symlink_metadata(&path).map_err(|_| "local_directory_unavailable")?;
            // 不跟随子目录联接点，避免循环或越过用户明确选定的树。
            if link(&metadata) {
                continue;
            }
            if metadata.is_dir() {
                pending.push(path);
            } else if metadata.is_file() {
                files.extend(playable_import(&path));
            }
        }
    }
    Ok(files)
}

pub(crate) fn stored_path(db: &Database, id: &str) -> Result<Option<PathBuf>, String> {
    db.lock()
        .query_row(
            "SELECT path FROM local_files f WHERE stored_path_key=?1 AND
               (manual=1 OR EXISTS(SELECT 1 FROM directory_files m WHERE m.file_id=f.file_id))
             ORDER BY manual DESC,file_id LIMIT 1",
            [id],
            |row| Ok(PathBuf::from(row.get::<_, String>(0)?)),
        )
        .optional()
        .map_err(|_| UNAVAILABLE.into())
}

impl Library {
    pub(crate) fn new() -> Self {
        Self {
            media: BTreeMap::new(),
        }
    }

    pub(crate) fn songs(
        sources: &Sources,
        downloads: Vec<SavedDownload>,
        ids: &mut std::collections::HashMap<PathBuf, String>,
    ) -> BTreeMap<String, Song> {
        fn entry<'a>(
            songs: &'a mut BTreeMap<String, Song>,
            path: PathBuf,
            ids: &mut std::collections::HashMap<PathBuf, String>,
        ) -> Option<&'a mut Song> {
            let format = file_format(&path)?;
            let id = ids
                .entry(path.clone())
                .or_insert_with(|| path_key(&path))
                .clone();
            Some(songs.entry(id.clone()).or_insert_with(|| {
                let metadata = fs::metadata(&path)
                    .ok()
                    .filter(|metadata| metadata.is_file());
                Song {
                    id,
                    format,
                    title: path
                        .file_stem()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .into_owned(),
                    artist: String::new(),
                    available: metadata.is_some(),
                    modified: metadata
                        .as_ref()
                        .and_then(|metadata| metadata.modified().ok()),
                    size_bytes: metadata.map(|metadata| metadata.len()),
                    media: MediaFacts::default(),
                    saved_at: None,
                    source_preserved: false,
                    path,
                    downloaded: false,
                    download_identity: None,
                    manual: false,
                    directories: Vec::new(),
                }
            }))
        }
        let mut songs = BTreeMap::new();
        for saved in downloads {
            if let Some(song) = entry(&mut songs, saved.path, ids) {
                song.downloaded = true;
                if song.saved_at.is_none() {
                    song.download_identity = Some(saved.identity);
                    if !saved.title.is_empty() {
                        song.title = saved.title;
                    }
                    song.artist = saved.artist;
                    song.saved_at = Some(saved.saved_at);
                    song.source_preserved = saved.source_preserved;
                    if song.size_bytes.is_none() {
                        song.size_bytes = Some(saved.size_bytes);
                    }
                }
            }
        }
        for path in &sources.manual {
            if let Some(song) = entry(&mut songs, path.clone(), ids) {
                song.manual = true;
            }
        }
        for dir in &sources.directories {
            for path in &dir.files {
                if let Some(song) = entry(&mut songs, path.clone(), ids) {
                    if !song.directories.contains(&dir.id) {
                        song.directories.push(dir.id.clone());
                    }
                }
            }
        }
        songs
    }

    pub(crate) fn view(
        &mut self,
        sources: &Sources,
        downloads: Vec<SavedDownload>,
        excluded: &BTreeSet<String>,
    ) -> Value {
        let directories: Vec<_> = sources
            .directories
            .iter()
            .map(|dir| {
                json!({
                    "id":dir.id,"path":dir.path,"available":dir.path.is_dir()
                })
            })
            .collect();
        let mut ids = std::collections::HashMap::new();
        let mut songs = Self::songs(sources, downloads.clone(), &mut ids);
        songs.retain(|id, _| !excluded.contains(id));
        self.media
            .retain(|id, _| songs.get(id).is_some_and(|song| song.available));
        for song in songs.values_mut().filter(|song| song.available) {
            let Some(modified) = song.modified else {
                song.media = MediaFacts::read(&song.path).unwrap_or_default();
                continue;
            };
            let cached = self.media.get(&song.id).filter(|cached| {
                cached.modified == modified && cached.size_bytes == song.size_bytes
            });
            song.media = if let Some(cached) = cached {
                cached.facts.clone()
            } else {
                let facts = MediaFacts::read(&song.path).unwrap_or_default();
                self.media.insert(
                    song.id.clone(),
                    CachedMedia {
                        size_bytes: song.size_bytes,
                        modified,
                        facts: facts.clone(),
                    },
                );
                facts
            };
        }
        let mut seen = BTreeSet::new();
        let downloads: Vec<_> = downloads
            .into_iter()
            .filter_map(|saved| {
                let id = ids.get(&saved.path)?.clone();
                let song = songs.get(&id)?;
                if !seen.insert(id.clone()) {
                    return None;
                }
                Some(json!({
                    "id":id,"recordId":saved.id,"path":saved.path,"title":saved.title,
                    "artist":saved.artist,"format":saved.format,"sizeBytes":song.size_bytes,
                    "album":song.media.album,"durationSeconds":song.media.duration_seconds,
                    "savedAt":saved.saved_at,"sourcePreserved":saved.source_preserved,
                    "available":song.available
                }))
            })
            .collect();
        let mut songs: Vec<_> = songs.into_values().collect();
        songs.sort_by(|a, b| a.title.cmp(&b.title).then_with(|| a.path.cmp(&b.path)));
        json!({"songs":songs, "downloads":downloads, "directories":directories})
    }
}

fn restore(tx: &Transaction<'_>, key: &str) -> rusqlite::Result<()> {
    tx.execute("DELETE FROM excluded_files WHERE song_id=?1", [key])?;
    Ok(())
}

fn paths_for_write(paths: &[PathBuf]) -> Result<Vec<(&str, String)>, String> {
    paths
        .iter()
        .map(|path| Ok((storage::path_text(path).ok_or(UNAVAILABLE)?, key(path))))
        .collect()
}

pub(crate) fn import(history: &mut History, paths: &[PathBuf]) -> Result<(), String> {
    let paths = paths_for_write(paths)?;
    history
        .transact(|tx| {
            for (path, key) in paths {
                let duplicate: bool = tx.query_row(
                "SELECT EXISTS(SELECT 1 FROM local_files WHERE stored_path_key=?1 AND manual=1)",
                [&key], |row| row.get(0),
            )?;
                if !duplicate {
                    let file = storage::file_id(tx, path, &key)?;
                    tx.execute("UPDATE local_files SET manual=1 WHERE file_id=?1", [file])?;
                }
                restore(tx, &key)?;
            }
            Ok(())
        })
        .map_err(|_| UNAVAILABLE.into())
}

pub(crate) fn merge_directory(
    history: &mut History,
    id: &str,
    path: &Path,
    discovered: &[PathBuf],
    choose: bool,
) -> Result<(), String> {
    let path = storage::path_text(path).ok_or(UNAVAILABLE)?;
    let discovered = paths_for_write(discovered)?;
    history
        .transact(|tx| {
            if choose {
                tx.execute(
                    "INSERT INTO library_directories(directory_id,path) VALUES (?1,?2)
                 ON CONFLICT(directory_id) DO NOTHING",
                    params![id, path],
                )?;
            }
            let current: Option<String> = tx
                .query_row(
                    "SELECT path FROM library_directories WHERE directory_id=?1",
                    [id],
                    |row| row.get(0),
                )
                .optional()?;
            if current.as_deref() != Some(path) {
                // 扫描期间目录可能已删除或改变，只提交仍有效的扫描结果。
                return Err(rusqlite::Error::QueryReturnedNoRows);
            }
            for (path, key) in discovered {
                let file = storage::file_id(tx, path, &key)?;
                tx.execute(
                    "DELETE FROM directory_files WHERE directory_id=?1 AND file_id<>?2
                  AND file_id IN (SELECT file_id FROM local_files WHERE stored_path_key=?3)",
                    params![id, file, key],
                )?;
                tx.execute(
                    "INSERT OR IGNORE INTO directory_files VALUES (?1,?2)",
                    params![id, file],
                )?;
                restore(tx, &key)?;
            }
            storage::prune_files(tx)
        })
        .map_err(|_| UNAVAILABLE.into())
}

pub async fn change(downloads: &crate::downloads::Downloads, body: &Value) -> Result<(), String> {
    let action = body["action"].as_str().ok_or("invalid_input")?;
    match action {
        "files" => {
            let Some(files) = rfd::AsyncFileDialog::new()
                .set_title("添加歌曲")
                .add_filter("音乐", &["mp3", "flac"])
                .pick_files()
                .await
            else {
                return Ok(());
            };
            let paths = files
                .into_iter()
                .map(|file| file.path().to_owned())
                .collect::<Vec<_>>();
            let downloads = downloads.clone();
            tokio::task::spawn_blocking(move || {
                let paths = paths
                    .iter()
                    .filter_map(|path| playable_import(path))
                    .collect::<Vec<_>>();
                if paths.is_empty() {
                    return Err("local_unsupported".into());
                }
                downloads.access_history(|history| import(history, &paths))
            })
            .await
            .map_err(|_| UNAVAILABLE)?
        }
        "choose" | "refresh" => {
            let choose = action == "choose";
            let (id, path) =
                if choose {
                    let Some(folder) = rfd::AsyncFileDialog::new()
                        .set_title("添加文件夹")
                        .pick_folder()
                        .await
                    else {
                        return Ok(());
                    };
                    let path = folder
                        .path()
                        .canonicalize()
                        .map_err(|_| "local_directory_unavailable")?;
                    (key(&path), path)
                } else {
                    let id = body["id"].as_str().ok_or("track_not_found")?.to_owned();
                    let downloads = downloads.clone();
                    tokio::task::spawn_blocking(move || {
                        let path =
                            downloads.access_history(|history| {
                                history.db.lock().query_row(
                            "SELECT path FROM library_directories WHERE directory_id=?1",
                            [&id], |row| Ok(PathBuf::from(row.get::<_, String>(0)?)),
                        ).optional().map_err(|_| UNAVAILABLE)?
                        .ok_or_else(|| "track_not_found".into())
                            })?;
                        Ok::<_, String>((id, path))
                    })
                    .await
                    .map_err(|_| UNAVAILABLE)??
                };
            let downloads = downloads.clone();
            tokio::task::spawn_blocking(move || {
                let files = scan(&path)?;
                downloads
                    .access_history(|history| merge_directory(history, &id, &path, &files, choose))
            })
            .await
            .map_err(|_| UNAVAILABLE)?
        }
        "remove" => {
            if let Some(id) = body["id"].as_str() {
                let id = id.to_owned();
                let downloads = downloads.clone();
                tokio::task::spawn_blocking(move || {
                    downloads.access_history(|history| {
                        history
                            .transact(|tx| {
                                tx.execute(
                                    "DELETE FROM library_directories WHERE directory_id=?1",
                                    [id],
                                )?;
                                storage::prune_files(tx)
                            })
                            .map_err(|_| UNAVAILABLE.into())
                    })
                })
                .await
                .map_err(|_| UNAVAILABLE)??;
            }
            Ok(())
        }
        _ => Err("invalid_input".into()),
    }
}

impl Song {
    pub fn playback_path(&self) -> Result<PathBuf, String> {
        self.path
            .is_file()
            .then(|| self.path.clone())
            .ok_or_else(|| "saved_file_missing".into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn mp3(path: &Path) {
        let mut audio = vec![0; 417 * 20];
        for frame in audio.chunks_exact_mut(417) {
            frame[..4].copy_from_slice(&[255, 251, 144, 0]);
        }
        fs::write(path, audio).unwrap();
    }

    fn view(library: &mut Library, history: &History) -> Value {
        let (sources, records, excluded) = {
            let db = history.db.lock();
            let (records, excluded) = history.snapshot(&db).unwrap();
            (sources(&db).unwrap(), records, excluded)
        };
        library.view(&sources, records, &excluded)
    }

    #[cfg(windows)]
    #[test]
    fn preparing_one_song_avoids_canonicalizing_unrelated_library_paths() {
        use crate::delete_plan::Target;
        let root = tempfile::tempdir().unwrap();
        let selected = root.path().join("selected.mp3");
        mp3(&selected);
        let mut history = History::new(Database::memory(), root.path().into());
        let mut paths = (0..512)
            .map(|i| root.path().join(format!("unrelated-{i}.mp3")))
            .collect::<Vec<_>>();
        paths.push(selected.clone());
        import(&mut history, &paths).unwrap();
        let id = path_key(&selected);

        PATH_KEY_CALLS.with(|count| count.set(0));
        assert_eq!(
            Library::songs(
                &sources(&history.db.lock()).unwrap(),
                vec![],
                &mut Default::default()
            )
            .len(),
            513
        );
        let list_calls = PATH_KEY_CALLS.with(|count| count.replace(0));
        let target = Target::resolve(&history, &id, None, &[]).unwrap();
        let plan_calls = PATH_KEY_CALLS.with(|count| count.get());
        assert_eq!(target.path, selected);
        assert_eq!((list_calls, plan_calls), (513, 1));
        let other = root.path().join("other.mp3");
        mp3(&other);
        import(&mut history, &[other]).unwrap();
        assert_eq!(Target::resolve(&history, &id, None, &[]).unwrap(), target);
    }

    #[test]
    fn reads_mp3_album_and_duration_without_decoding() {
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("tagged.mp3");
        mp3(&path);
        let audio = fs::read(&path).unwrap();
        let mut tagged = b"ID3\x03\0\0\0\0\0\x10TALB\0\0\0\x06\0\0\0Album".to_vec();
        tagged.extend(audio);
        fs::write(&path, tagged).unwrap();
        let facts = MediaFacts::read(&path).unwrap();
        assert_eq!(facts.album.as_deref(), Some("Album"));
        assert!(facts.duration_seconds.is_some_and(|seconds| seconds > 0.4));
    }

    #[test]
    fn explicit_scan_keeps_members_and_atomically_restores_only_present_files() {
        let temp = tempfile::tempdir().unwrap();
        let db_path = temp.path().join("music-core.sqlite3");
        let music = temp.path().join("音乐");
        let nested = music.join("Nested");
        fs::create_dir_all(&nested).unwrap();
        let kept = nested.join("kept.mp3");
        let missing = music.join("missing.mp3");
        mp3(&kept);
        mp3(&missing);
        fs::write(music.join("fake.flac"), b"not audio").unwrap();
        let mut history = History::open(db_path.clone(), music.clone()).unwrap();
        let mut library = Library::new();
        let discovered = scan(&music).unwrap();
        assert_eq!(discovered.len(), 2);
        merge_directory(&mut history, "parent", &music, &discovered, true).unwrap();
        merge_directory(
            &mut history,
            "child",
            &nested,
            &scan(&nested).unwrap(),
            true,
        )
        .unwrap();
        import(&mut history, &[kept.canonicalize().unwrap()]).unwrap();
        history
            .add(SavedDownload {
                id: "saved".into(),
                identity: json!({"providerId":"qq","platformId":"fixture"}),
                title: "Published".into(),
                artist: String::new(),
                path: kept.clone(),
                format: "mp3".into(),
                size_bytes: fs::metadata(&kept).unwrap().len(),
                saved_at: 1,
                source_preserved: false,
            })
            .unwrap();
        let id = path_key(&kept);
        let missing_id = path_key(&missing);
        let before = view(&mut library, &history);
        let songs = before["songs"].as_array().unwrap();
        assert_eq!(songs.len(), 2);
        let track = songs.iter().find(|row| row["id"] == id).unwrap();
        assert_eq!(track["directories"], json!(["parent", "child"]));
        assert_eq!(track["manual"], true);
        assert_eq!(track["title"], "Published");
        assert_eq!(before["downloads"][0]["recordId"], "saved");

        history.remove_song(&kept, &id, false).unwrap();
        history.remove_song(&missing, &missing_id, false).unwrap();
        assert!(kept.is_file() && missing.is_file());
        let outside = temp.path().join("outside.mp3");
        fs::rename(&missing, &outside).unwrap();
        drop(library);
        drop(history);
        let mut history = History::open(db_path, music.clone()).unwrap();
        let mut library = Library::new();
        assert_eq!(view(&mut library, &history)["songs"], json!([]));
        merge_directory(
            &mut history,
            "parent",
            &music,
            &scan(&music).unwrap(),
            false,
        )
        .unwrap();
        assert!(history.is_excluded(&missing_id).unwrap());
        assert_eq!(
            view(&mut library, &history)["songs"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        assert_eq!(view(&mut library, &history)["downloads"], json!([]));
        fs::rename(outside, &missing).unwrap();
        merge_directory(
            &mut history,
            "parent",
            &music,
            &scan(&music).unwrap(),
            false,
        )
        .unwrap();
        fs::remove_file(&missing).unwrap();
        merge_directory(
            &mut history,
            "parent",
            &music,
            &scan(&music).unwrap(),
            false,
        )
        .unwrap();
        let restored = view(&mut library, &history);
        let songs = restored["songs"].as_array().unwrap();
        assert_eq!(songs.len(), 2);
        assert!(songs
            .iter()
            .any(|song| song["id"] == missing_id && song["available"] == false));

        history
            .transact(|tx| {
                tx.execute(
                    "DELETE FROM library_directories WHERE directory_id='child'",
                    [],
                )?;
                storage::prune_files(tx)
            })
            .unwrap();
        let result = view(&mut library, &history);
        assert!(result["songs"]
            .as_array()
            .unwrap()
            .iter()
            .any(|song| song["id"] == id
                && song["directories"] == json!(["parent"])
                && song["manual"] == true));
    }

    #[test]
    fn restored_import_and_pending_recycle_cannot_overwrite_each_other() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("same.mp3");
        mp3(&path);
        let path = path.canonicalize().unwrap();
        let id = key(&path);
        let mut history = History::new(Database::memory(), root.path().into());
        history.reject_writes(true);
        assert!(!history.complete_recycle(&id, &[], true));
        assert!(history.is_excluded(&id).unwrap());
        assert!(import(&mut history, std::slice::from_ref(&path)).is_err());
        assert!(sources(&history.db.lock()).unwrap().manual.is_empty());
        history.reject_writes(false);
        import(&mut history, &[path]).unwrap();
        assert!(history.reconcile());
        assert!(!history.is_excluded(&id).unwrap());
    }
}
