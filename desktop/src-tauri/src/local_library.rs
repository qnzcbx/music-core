use crate::download_history::SavedDownload;
use serde::{Deserialize, Serialize};
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

#[derive(Clone, Serialize, Deserialize)]
struct Directory {
    id: String,
    path: PathBuf,
    files: Vec<PathBuf>,
}

#[derive(Clone, Default, Serialize, Deserialize)]
struct Stored {
    manual: Vec<PathBuf>,
    directories: Vec<Directory>,
}

pub struct Library {
    path: PathBuf,
    stored: Stored,
    media: BTreeMap<String, CachedMedia>,
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

fn key(path: &Path) -> String {
    let path = path.to_string_lossy().replace('/', "\\");
    let normalized = if let Some(unc) = path.strip_prefix(r"\\?\UNC\") {
        format!(r"\\{unc}")
    } else {
        path.strip_prefix(r"\\?\").unwrap_or(&path).to_string()
    };
    format!("{:x}", Sha256::digest(normalized.to_lowercase().as_bytes()))
}

pub(crate) fn path_key(path: &Path) -> String {
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

pub(crate) fn delete_audio_file(path: &Path, expected_size: Option<u64>) -> Result<(), String> {
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Ok(metadata)
            if metadata.is_file()
                && !link(&metadata)
                && expected_size.is_none_or(|size| metadata.len() == size) => {}
        _ => return Err("local_file_delete_failed".into()),
    }
    fs::remove_file(path).map_err(|_| "local_file_delete_failed".into())
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

impl Library {
    pub fn open(path: PathBuf) -> Result<Self, String> {
        let stored = match fs::read(&path) {
            Ok(bytes) => serde_json::from_slice(&bytes).map_err(|_| "local_library_unavailable")?,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Stored::default(),
            Err(_) => return Err("local_library_unavailable".into()),
        };
        Ok(Self {
            path,
            stored,
            media: BTreeMap::new(),
        })
    }

    fn commit(&mut self, next: Stored) -> Result<(), String> {
        crate::download_history::write_snapshot(&self.path, &next)
            .map_err(|_| "local_library_unavailable")?;
        self.stored = next;
        Ok(())
    }

    pub fn songs(&self, downloads: Vec<SavedDownload>) -> BTreeMap<String, Song> {
        fn entry(songs: &mut BTreeMap<String, Song>, path: PathBuf) -> Option<&mut Song> {
            let format = file_format(&path)?;
            let id = path_key(&path);
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
            if let Some(song) = entry(&mut songs, saved.path) {
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
        for path in &self.stored.manual {
            if let Some(song) = entry(&mut songs, path.clone()) {
                song.manual = true;
            }
        }
        for dir in &self.stored.directories {
            for path in &dir.files {
                if let Some(song) = entry(&mut songs, path.clone()) {
                    if !song.directories.contains(&dir.id) {
                        song.directories.push(dir.id.clone());
                    }
                }
            }
        }
        songs
    }

    pub fn view(&mut self, downloads: Vec<SavedDownload>, excluded: &BTreeSet<String>) -> Value {
        let directories: Vec<_> = self
            .stored
            .directories
            .iter()
            .map(|dir| {
                json!({
                    "id":dir.id,"path":dir.path,"available":dir.path.is_dir()
                })
            })
            .collect();
        let mut songs = self.songs(downloads.clone());
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
                let id = path_key(&saved.path);
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

pub async fn change(
    library: &std::sync::Mutex<Library>,
    body: &Value,
) -> Result<Vec<String>, String> {
    let action = body["action"].as_str().ok_or("invalid_input")?;
    match action {
        "files" => {
            let Some(files) = rfd::AsyncFileDialog::new()
                .set_title("添加歌曲")
                .add_filter("音乐", &["mp3", "flac"])
                .pick_files()
                .await
            else {
                return Ok(Vec::new());
            };
            let paths = tokio::task::spawn_blocking(move || {
                files
                    .iter()
                    .filter_map(|f| playable_import(f.path()))
                    .collect::<Vec<_>>()
            })
            .await
            .map_err(|_| "local_library_unavailable")?;
            if paths.is_empty() {
                return Err("local_unsupported".into());
            }
            let mut library = library.lock().unwrap();
            let mut next = library.stored.clone();
            let ids = paths.iter().map(|path| key(path)).collect();
            for path in paths {
                if !next.manual.iter().any(|old| key(old) == key(&path)) {
                    next.manual.push(path);
                }
            }
            library.commit(next)?;
            return Ok(ids);
        }
        "choose" | "refresh" => {
            let (id, path) = if action == "choose" {
                let Some(folder) = rfd::AsyncFileDialog::new()
                    .set_title("添加文件夹")
                    .pick_folder()
                    .await
                else {
                    return Ok(Vec::new());
                };
                let path = folder
                    .path()
                    .canonicalize()
                    .map_err(|_| "local_directory_unavailable")?;
                (key(&path), path)
            } else {
                let library = library.lock().unwrap();
                let dir = library
                    .stored
                    .directories
                    .iter()
                    .find(|d| d.id == body["id"])
                    .ok_or("track_not_found")?;
                (dir.id.clone(), dir.path.clone())
            };
            let scan_path = path.clone();
            let files = tokio::task::spawn_blocking(move || scan(&scan_path))
                .await
                .map_err(|_| "local_library_unavailable")??;
            let mut library = library.lock().unwrap();
            let mut next = library.stored.clone();
            if let Some(dir) = next.directories.iter_mut().find(|dir| dir.id == id) {
                // 保留已不可访问的旧条目，回来后刷新可再次播放。
                let merged: BTreeMap<_, _> = dir
                    .files
                    .iter()
                    .chain(&files)
                    .map(|path| (key(path), path.clone()))
                    .collect();
                dir.files = merged.into_values().collect();
            } else if action == "choose" {
                next.directories.push(Directory { id, path, files });
            }
            library.commit(next)?;
        }
        "remove" => {
            let mut library = library.lock().unwrap();
            let mut next = library.stored.clone();
            next.directories.retain(|dir| dir.id != body["id"]);
            library.commit(next)?;
        }
        _ => return Err("invalid_input".into()),
    }
    Ok(Vec::new())
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
    fn removing_a_scanned_song_survives_reopening_and_rescanning() {
        let temp = tempfile::tempdir().unwrap();
        let config = temp.path().join("library.json");
        let music = temp.path().join("Music");
        fs::create_dir(&music).unwrap();
        let kept = music.join("kept.mp3");
        let deleted = music.join("deleted.mp3");
        mp3(&kept);
        mp3(&deleted);
        let mut library = Library::open(config.clone()).unwrap();
        let mut state = Stored::default();
        state.directories.push(Directory {
            id: "music".into(),
            path: music.clone(),
            files: scan(&music).unwrap(),
        });
        library.commit(state).unwrap();
        let history_path = temp.path().join("downloads.json");
        let mut history =
            crate::download_history::History::open(history_path.clone(), music.clone()).unwrap();
        history
            .add(SavedDownload {
                id: "saved".into(),
                identity: json!({}),
                title: "Kept".into(),
                artist: String::new(),
                path: kept.clone(),
                format: "mp3".into(),
                size_bytes: fs::metadata(&kept).unwrap().len(),
                saved_at: 1,
                source_preserved: false,
            })
            .unwrap();
        let before = library.view(history.list(), history.excluded_songs());
        assert_eq!(before["downloads"][0]["id"], path_key(&kept));
        assert_eq!(before["songs"].as_array().unwrap().len(), 2);
        history.remove_song(&kept, &path_key(&kept), false).unwrap();
        history
            .remove_song(&deleted, &path_key(&deleted), true)
            .unwrap();
        assert!(kept.is_file());
        assert!(!deleted.exists());

        let mut library = Library::open(config).unwrap();
        let mut rescanned = library.stored.clone();
        rescanned.directories[0].files = scan(&music).unwrap();
        library.commit(rescanned).unwrap();
        let mut history = crate::download_history::History::open(history_path, music).unwrap();
        let after = library.view(history.list(), history.excluded_songs());
        assert!(after["songs"].as_array().unwrap().is_empty());
        assert!(after["downloads"].as_array().unwrap().is_empty());
        history.restore_songs(&[path_key(&kept)]).unwrap();
        assert_eq!(
            library.view(history.list(), history.excluded_songs())["songs"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
    }

    #[tokio::test]
    async fn explicit_scan_merges_sources_and_keeps_missing_directory_records() {
        let temp = tempfile::tempdir().unwrap();
        let config = temp.path().join("library.json");
        let music = temp.path().join("Music");
        let download = music.join("拾音/song.mp3");
        let manual = music.join("manual.mp3");
        let scanned = music.join("scanned.mp3");
        fs::create_dir_all(download.parent().unwrap()).unwrap();
        for p in [&download, &manual, &scanned] {
            mp3(p);
        }
        fs::write(music.join("fake.flac"), b"not audio").unwrap();
        let mut library = Library::open(config.clone()).unwrap();
        assert!(library.songs(vec![]).is_empty());
        let saved = SavedDownload {
            id: "download".into(),
            identity: json!({"providerId":"qq","platformId":"song"}),
            title: "song".into(),
            artist: "artist".into(),
            path: download.clone(),
            format: "mp3".into(),
            size_bytes: 8340,
            saved_at: 1,
            source_preserved: false,
        };
        assert_eq!(library.songs(vec![saved.clone()]).len(), 1);
        let files = scan(&music).unwrap();
        assert_eq!(files.len(), 3);
        library
            .commit(Stored {
                manual: vec![manual.clone()],
                directories: vec![
                    Directory {
                        id: "parent".into(),
                        path: music.clone(),
                        files,
                    },
                    Directory {
                        id: "overlap".into(),
                        path: download.parent().unwrap().to_owned(),
                        files: vec![download.clone()],
                    },
                ],
                ..Stored::default()
            })
            .unwrap();
        let library = std::sync::Mutex::new(Library::open(config).unwrap());
        let songs = library.lock().unwrap().songs(vec![saved.clone()]);
        assert_eq!(songs.len(), 3);
        let song = &songs[&key(&download.canonicalize().unwrap())];
        assert!(song.downloaded);
        assert_eq!(song.directories.len(), 2);
        let absent = temp.path().join("temporarily-offline");
        fs::rename(&music, &absent).unwrap();
        assert!(change(&library, &json!({"action":"refresh","id":"parent"}))
            .await
            .is_err());
        let available = library.lock().unwrap().view(
            vec![
                saved.clone(),
                SavedDownload {
                    id: "second-download".into(),
                    path: manual.clone(),
                    ..saved.clone()
                },
            ],
            &BTreeSet::new(),
        );
        let downloaded = available["downloads"].as_array().unwrap();
        assert_eq!(downloaded.len(), 2);
        assert_ne!(downloaded[0]["id"], downloaded[1]["id"]);
        for row in downloaded {
            assert!(available["songs"]
                .as_array()
                .unwrap()
                .iter()
                .any(|song| song["id"] == row["id"]));
        }
        let view = library
            .lock()
            .unwrap()
            .view(vec![saved.clone()], &BTreeSet::new());
        assert_eq!(view["directories"][0]["available"], false);
        assert_eq!(view["songs"].as_array().unwrap().len(), 3);
        fs::rename(&absent, &music).unwrap();
        change(&library, &json!({"action":"refresh","id":"parent"}))
            .await
            .unwrap();
        change(&library, &json!({"action":"remove","id":"parent"}))
            .await
            .unwrap();
        let songs = library.lock().unwrap().songs(vec![saved]);
        assert_eq!(songs.len(), 2);
        assert!(songs.values().any(|s| s.manual));
        assert!(songs
            .values()
            .any(|s| s.downloaded && s.directories == ["overlap"]));
        assert!(scanned.is_file());
    }
}
