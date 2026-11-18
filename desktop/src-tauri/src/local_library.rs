use crate::download_history::SavedDownload;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
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
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Song {
    pub id: String,
    path: PathBuf,
    title: String,
    artist: String,
    pub format: &'static str,
    available: bool,
    downloaded: bool,
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

impl Library {
    pub fn open(path: PathBuf) -> Result<Self, String> {
        let stored = match fs::read(&path) {
            Ok(bytes) => serde_json::from_slice(&bytes).map_err(|_| "local_library_unavailable")?,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Stored::default(),
            Err(_) => return Err("local_library_unavailable".into()),
        };
        Ok(Self { path, stored })
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
            let canonical = path.canonicalize();
            let id = key(canonical.as_ref().unwrap_or(&path));
            Some(songs.entry(id.clone()).or_insert_with(|| {
                Song {
                    id,
                    format,
                    title: path
                        .file_stem()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .into_owned(),
                    artist: String::new(),
                    available: path.is_file(),
                    path,
                    downloaded: false,
                    manual: false,
                    directories: Vec::new(),
                }
            }))
        }
        let mut songs = BTreeMap::new();
        for saved in downloads {
            if let Some(song) = entry(&mut songs, saved.path) {
                song.downloaded = true;
                song.title = saved.title;
                song.artist = saved.artist;
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

    pub fn view(&self, downloads: Vec<SavedDownload>) -> Value {
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
        json!({"songs":self.songs(downloads).into_values().collect::<Vec<_>>(), "directories":directories})
    }
}

pub async fn change(library: &std::sync::Mutex<Library>, body: &Value) -> Result<bool, String> {
    let action = body["action"].as_str().ok_or("invalid_input")?;
    match action {
        "files" => {
            let Some(files) = rfd::AsyncFileDialog::new()
                .set_title("添加歌曲")
                .add_filter("音乐", &["mp3", "flac"])
                .pick_files()
                .await
            else {
                return Ok(false);
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
            for path in paths {
                if !next.manual.iter().any(|old| key(old) == key(&path)) {
                    next.manual.push(path);
                }
            }
            library.commit(next)?;
        }
        "choose" | "refresh" => {
            let (id, path) = if action == "choose" {
                let Some(folder) = rfd::AsyncFileDialog::new()
                    .set_title("添加文件夹")
                    .pick_folder()
                    .await
                else {
                    return Ok(false);
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
    Ok(true)
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
        let view = library.lock().unwrap().view(vec![saved.clone()]);
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
