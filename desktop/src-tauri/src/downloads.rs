use crate::{provider::common, storage::Database};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
#[cfg(test)]
use std::io::{Read, Seek, SeekFrom};
use std::{
    collections::HashMap,
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::io::AsyncWriteExt;
use tokio_util::sync::CancellationToken;

// 与 Python DownloadSettings 默认值一致，自动取得的高解析度 FLAC 不再被旧 100 MiB 上限挡住。
pub(crate) const MAX_DOWNLOAD_BYTES: u64 = 1024 * 1024 * 1024;

fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_millis() as u64
}
#[derive(Clone)]
struct Recording {
    quality: String,
    cover: Option<String>,
    identity: Value,
    title: String,
    artist: String,
    duration: f64,
}
struct Job {
    public: Value,
    recording: Recording,
    target: PathBuf,
    part: PathBuf,
    cancel: CancellationToken,
    owns_part: bool,
    owns_output: bool,
}
// 沿用当前界面使用的命名枚举与默认值。
#[derive(Clone, Copy, Default, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum Naming {
    Title,
    #[default]
    ArtistTitle,
    TitleArtist,
}

fn suggested_name(recording: &Recording, naming: Naming) -> String {
    let parts = match naming {
        Naming::Title => vec![recording.title.as_str()],
        Naming::ArtistTitle => vec![recording.artist.as_str(), recording.title.as_str()],
        Naming::TitleArtist => vec![recording.title.as_str(), recording.artist.as_str()],
    };
    let stem = parts
        .into_iter()
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join(" - ");
    let stem = if stem.is_empty() {
        key(&recording.identity)
    } else {
        stem
    };
    let mut clean = String::new();
    let mut units = 0;
    for c in stem.trim_matches([' ', '.']).chars() {
        let c = if c.is_control() || "<>:\"/\\|?*".contains(c) {
            '_'
        } else {
            c
        };
        if units + c.len_utf16() > 120 {
            break;
        }
        clean.push(c);
        units += c.len_utf16();
    }
    let clean = clean.trim_end_matches([' ', '.']);
    let clean = if clean.is_empty() { "未命名" } else { clean };
    let device = clean.split('.').next().unwrap().to_uppercase();
    let reserved = ["CON", "PRN", "AUX", "NUL"].contains(&device.as_str())
        || ["COM", "LPT"].iter().any(|prefix| {
            device
                .strip_prefix(prefix)
                .is_some_and(|s| s.chars().count() == 1 && "123456789¹²³".contains(s))
        });
    format!("{}{clean}.mp3", if reserved { "_" } else { "" })
}
#[derive(Clone, Default)]
pub struct Downloads {
    recordings: Arc<Mutex<HashMap<String, Recording>>>,
    jobs: Arc<Mutex<HashMap<String, Job>>>,
    closing: CancellationToken,
    finished: Arc<tokio::sync::Notify>,
    pub tools_dir: Option<PathBuf>,
    history: Option<Arc<Mutex<crate::download_history::History>>>,
    pub media_covers: crate::covers::Covers,
}
fn key(identity: &Value) -> String {
    format!(
        "{}:{}",
        identity["providerId"].as_str().unwrap_or(""),
        identity["platformId"].as_str().unwrap_or("")
    )
}

/// 与网页下载流程对齐：搜索的全局收费/试听标记不能代表所选品质的实际下载响应。
/// 明确 cannotDownload 才在入口拒绝；缺失字段允许用户按需检查。
pub fn eligibility(row: &Value) -> Option<bool> {
    match &row["payInfo"]["cannotDownload"] {
        v if v == 1 || v == "1" => Some(false),
        v if v == 0 || v == "0" => Some(true),
        _ => None,
    }
}
#[cfg(test)]
pub fn frame(header: [u8; 4]) -> Option<(u64, u64, usize)> {
    let h = u32::from_be_bytes(header);
    let version = (h >> 19) & 3;
    let layer = (h >> 17) & 3;
    let index = (h >> 12) & 15;
    let sr = (h >> 10) & 3;
    if h >> 21 != 2047 || version != 3 || layer != 1 || index != 9 || sr == 3 {
        return None;
    }
    let rate = [44100u64, 48000, 32000][sr as usize];
    Some((
        128000,
        rate,
        (144 * 128000 / rate + ((h >> 9) & 1) as u64) as usize,
    ))
}
#[cfg(test)]
fn audio_start(file: &mut std::fs::File) -> Result<u64, String> {
    let mut h = [0; 10];
    file.read_exact(&mut h)
        .map_err(|_| "upstream_invalid_response")?;
    let offset = if &h[..3] == b"ID3" {
        if h[6..10].iter().any(|b| b & 128 != 0) {
            return Err("upstream_invalid_response".into());
        }
        10 + h[6..10].iter().fold(0u64, |n, b| (n << 7) | *b as u64)
            + if h[5] & 16 != 0 { 10 } else { 0 }
    } else {
        0
    };
    if offset > 1024 * 1024 {
        return Err("upstream_invalid_response".into());
    }
    file.seek(SeekFrom::Start(offset))
        .map_err(|_| "file_io_error")?;
    Ok(offset)
}
/// 扫描整份原文件的 MPEG 帧，核实 CBR 128k、边界和实际时长；不解码、不改写。
#[cfg(test)]
pub fn inspect(path: &Path, expected: f64) -> Result<Value, String> {
    let mut file = std::fs::File::open(path).map_err(|_| "file_io_error")?;
    let size = file.metadata().map_err(|_| "file_io_error")?.len();
    let mut pos = audio_start(&mut file)?;
    let mut samples = 0u64;
    let mut rate = 0;
    while pos < size {
        if size - pos == 128 {
            let mut tag = [0; 3];
            file.read_exact(&mut tag)
                .map_err(|_| "upstream_invalid_response")?;
            if &tag == b"TAG" {
                break;
            }
            file.seek(SeekFrom::Start(pos))
                .map_err(|_| "file_io_error")?;
        }
        let mut h = [0; 4];
        file.read_exact(&mut h)
            .map_err(|_| "upstream_invalid_response")?;
        let (_, sample_rate, length) = frame(h).ok_or("upstream_invalid_response")?;
        if rate != 0 && rate != sample_rate || pos + length as u64 > size {
            return Err("upstream_invalid_response".into());
        }
        rate = sample_rate;
        samples += 1152;
        pos += length as u64;
        file.seek(SeekFrom::Start(pos))
            .map_err(|_| "file_io_error")?;
    }
    if rate == 0
        || !expected.is_finite()
        || expected <= 0.0
        || (samples as f64 / rate as f64 - expected).abs() > 2.0f64.max(expected * 0.02)
    {
        return Err("source_verification_failed".into());
    }
    Ok(
        json!({"container":"mpeg-audio","codec":"mp3","bitrateBps":128000,"sampleRateHz":rate,"lossless":false,"sizeBytes":size,"providerQualityId":"standard"}),
    )
}
pub fn publish(part: &Path, target: &Path) -> Result<(), String> {
    // 同盘硬链接是无覆盖的原子发布，目标在任何时刻都不暴露半成品。
    std::fs::hard_link(part, target).map_err(|e| {
        if e.kind() == std::io::ErrorKind::AlreadyExists {
            "file_exists"
        } else {
            "file_io_error"
        }
    })?;
    Ok(())
}
pub fn reveal_file(path: &Path) -> Result<(), String> {
    std::process::Command::new("explorer.exe")
        .arg("/select,")
        .arg(path)
        .spawn()
        .map_err(|_| "file_io_error")?;
    Ok(())
}
async fn remove_temporary(path: &Path) -> std::io::Result<()> {
    for attempt in 0..20 {
        match tokio::fs::remove_file(path).await {
            Ok(()) => return Ok(()),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(()),
            Err(e) if attempt == 19 => return Err(e),
            Err(_) => tokio::time::sleep(Duration::from_millis(50)).await,
        }
    }
    Ok(())
}
async fn clean_owned_parts(part: &Path, owns_part: bool, owns_output: bool) -> (bool, bool) {
    let output = part.with_extension("mp3.part");
    tokio::join!(
        async { owns_part && remove_temporary(part).await.is_err() },
        async { owns_output && remove_temporary(&output).await.is_err() },
    )
}

async fn resolve(client: &reqwest::Client, r: &Recording) -> Result<String, String> {
    let id = r.identity["platformId"].as_str().ok_or("invalid_input")?;
    // 重试及新任务都重新核对原平台录音的当前下载限制，不复用播放地址或旧权限快照。
    let metadata = common::bytes(
        client
            .get("https://www.kuwo.cn/search/searchMusicBykeyWord")
            .query(&[
                ("all", r.title.as_str()),
                ("ft", "music"),
                ("client", "kt"),
                ("vipver", "1"),
                ("pn", "0"),
                ("rn", "100"),
                ("rformat", "json"),
                ("encoding", "utf8"),
                ("mobi", "1"),
            ]),
    )
    .await
    .map_err(|_| "upstream_failure")?;
    let metadata: Value =
        json5::from_str(std::str::from_utf8(&metadata).map_err(|_| "upstream_invalid_response")?)
            .map_err(|_| "upstream_invalid_response")?;
    let row = metadata["abslist"]
        .as_array()
        .and_then(|rows| {
            rows.iter().find(|row| {
                row["MUSICRID"]
                    .as_str()
                    .is_some_and(|value| value.strip_prefix("MUSIC_") == Some(id))
            })
        })
        .ok_or("access_denied")?;
    if eligibility(row) == Some(false) {
        return Err("access_denied".into());
    }
    if r.duration <= 0.0 {
        return Err("source_verification_failed".into());
    }
    // 沿用 Python resolve：官方 playUrl 明确权限拒绝不能跳过；只有已知上下文拒绝可走 mobi。
    let gate = common::bytes(
        client
            .get("https://www.kuwo.cn/api/v1/www/music/playUrl")
            .query(&[("mid", id), ("type", "music"), ("httpsStatus", "1")]),
    )
    .await
    .map_err(|_| "upstream_failure")?;
    let gate: Value = serde_json::from_slice(&gate).map_err(|_| "upstream_invalid_response")?;
    let context_rejected = gate["success"] == false
        && gate.get("code").is_none()
        && gate["message"] == "The request is illegal!";
    if !context_rejected {
        if gate["success"] == false
            || [json!(401), json!(403), json!("401"), json!("403")].contains(&gate["code"])
        {
            return Err("access_denied".into());
        }
        if ![json!(0), json!(200), json!("0"), json!("200")].contains(&gate["code"])
            || !gate["data"].is_object()
        {
            return Err("upstream_invalid_response".into());
        }
    }
    if r.quality == "auto" && !context_rejected {
        let url = gate["data"]["url"]
            .as_str()
            .filter(|s| !s.is_empty())
            .ok_or("media_unavailable")?;
        common::validate_media("kuwo", url).map_err(|_| "untrusted_media")?;
        return Ok(url.to_owned());
    }
    let mut params = vec![
        ("user", "0"),
        ("corp", "kuwo"),
        ("source", "kwplayer_ar_5.1.0.0_B_jiakong_vh.apk"),
        ("p2p", "1"),
        ("type", "convert_url2"),
        ("sig", "0"),
        (
            "format",
            if r.quality == "lossless" {
                "flac"
            } else {
                "mp3"
            },
        ),
        ("rid", id),
    ];
    if r.quality == "standard" {
        params.push(("br", "128k"));
    }
    if r.quality == "high" {
        params.push(("br", "320k"));
    }
    let bytes = common::bytes(
        client
            .get("https://mobi.kuwo.cn/mobi.s")
            .header("User-Agent", "okhttp/3.10.0")
            .query(&params),
    )
    .await
    .map_err(|_| "upstream_failure")?;
    let text = std::str::from_utf8(&bytes).map_err(|_| "upstream_invalid_response")?;
    let mut fields = HashMap::new();
    for (k, v) in text.lines().filter_map(|s| s.split_once('=')) {
        if fields.insert(k, v.trim()).is_some() {
            return Err("upstream_invalid_response".into());
        }
    }
    if fields.get("rid") != Some(&id) {
        return Err("upstream_invalid_response".into());
    }
    let url = fields
        .get("url")
        .filter(|s| !s.is_empty())
        .ok_or("media_unavailable")?;
    common::validate_media("kuwo", url).map_err(|_| "untrusted_media")?;
    Ok(url.to_string())
}
async fn prefix(client: &reqwest::Client, r: &Recording) -> Result<Value, String> {
    if r.identity["providerId"] != "kuwo" {
        let resolved = crate::download_resolver::resolve(
            client,
            &crate::fallback::Config::from_env()?,
            &r.identity,
            &r.quality,
            &r.title,
            &r.artist,
        )
        .await?;
        let mut rep = resolved.representation;
        rep["route"] = json!(resolved.route);
        rep["providerQualityId"] = json!(r.quality);
        return Ok(rep);
    }
    let url = resolve(client, r).await?;
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert("user-agent", "okhttp/3.10.0".parse().unwrap());
    let mut rep =
        crate::download_resolver::probe(client, &crate::provider::Media { url, headers }).await?;
    if !crate::download_media::satisfies(&rep, &r.quality) {
        return Err("media_unavailable".into());
    }
    rep["providerQualityId"] = json!(r.quality);
    rep["route"] = json!("native");
    Ok(rep)
}

fn full_response_size(
    status: u16,
    length: Option<u64>,
    range: Option<&str>,
) -> Result<Option<u64>, String> {
    if !matches!(status, 200 | 206) {
        return Err("upstream_invalid_response".into());
    }
    if let Some(range) = range {
        let (span, total) = range
            .strip_prefix("bytes ")
            .and_then(|v| v.split_once('/'))
            .ok_or("upstream_invalid_response")?;
        let (start, end) = span.split_once('-').ok_or("upstream_invalid_response")?;
        let total: u64 = total.parse().map_err(|_| "upstream_invalid_response")?;
        let end: u64 = end.parse().map_err(|_| "upstream_invalid_response")?;
        if start != "0"
            || total == 0
            || end.checked_add(1) != Some(total)
            || length.is_some_and(|n| n != total)
        {
            return Err("upstream_invalid_response".into());
        }
        Ok(Some(total))
    } else if status == 200 {
        Ok(length)
    } else {
        Err("upstream_invalid_response".into())
    }
}
impl Downloads {
    pub(crate) fn with_database(db: Database, default_directory: PathBuf) -> Self {
        Self {
            history: Some(Arc::new(Mutex::new(crate::download_history::History::new(
                db,
                default_directory,
            )))),
            ..Self::default()
        }
    }

    #[cfg(test)]
    fn with_history(path: PathBuf, default_directory: PathBuf) -> Result<Self, String> {
        let db = Database::open(&path).map_err(|error| error.to_string())?;
        Ok(Self::with_database(db, default_directory))
    }

    pub fn clear_media_cache(&self, scope: crate::media_cache::ClearScope) -> Result<(), String> {
        let cache = self.media_covers.1.as_ref().ok_or("媒体缓存不可用")?;
        self.access_history(|history| {
            let mut existence = HashMap::new();
            let live = history
                .list()?
                .into_iter()
                .filter_map(|row| {
                    let available = *existence
                        .entry(row.path.clone())
                        .or_insert_with(|| row.path.is_file());
                    available.then_some(row.id)
                })
                .collect::<Vec<_>>();
            // 持业务锁排序下载登记与清理，文件探测期间不占用 SQLite 连接。
            cache
                .clear(&live, scope)
                .map_err(|_| "媒体缓存清理失败".into())
        })
    }
    #[cfg(test)]
    pub fn saved(&self) -> Result<Value, String> {
        Ok(json!(self.saved_records()?))
    }

    #[cfg(test)]
    pub fn saved_records(&self) -> Result<Vec<crate::download_history::SavedDownload>, String> {
        let history = self
            .history
            .as_ref()
            .ok_or("capability_unsupported")?
            .lock()
            .unwrap();
        history.list()
    }

    #[cfg(test)]
    pub fn saved_path(&self, id: &str) -> Result<PathBuf, String> {
        let history = self
            .history
            .as_ref()
            .ok_or("capability_unsupported")?
            .lock()
            .unwrap();
        history
            .list()?
            .into_iter()
            .find(|row| row.id == id)
            .map(|row| row.path)
            .ok_or_else(|| "track_not_found".into())
    }

    pub fn access_history<T>(
        &self,
        action: impl FnOnce(&mut crate::download_history::History) -> Result<T, String>,
    ) -> Result<T, String> {
        let mut history = self
            .history
            .as_ref()
            .ok_or("capability_unsupported")?
            .lock()
            .unwrap();
        action(&mut history)
    }

    pub fn library_snapshot(
        &self,
    ) -> Result<
        (
            Vec<crate::download_history::SavedDownload>,
            std::collections::BTreeSet<String>,
        ),
        String,
    > {
        self.access_history(|history| {
            history.reconcile();
            history.snapshot(&history.db.lock())
        })
    }

    pub async fn directory(&self, body: &Value) -> Result<Value, String> {
        let manager = self.clone();
        let current = tokio::task::spawn_blocking(move || {
            manager.access_history(|history| history.directory())
        })
        .await
        .map_err(|_| "download_history_unavailable")??;
        let directory = match body["action"].as_str() {
            Some("choose") => {
                let Some(folder) = rfd::AsyncFileDialog::new()
                    .set_title("更改下载目录")
                    .set_directory(&current)
                    .pick_folder()
                    .await
                else {
                    return Ok(Value::Null);
                };
                Some(Some(folder.path().to_owned()))
            }
            Some("reset") => Some(None),
            Some("open") => None,
            _ => return Err("invalid_input".into()),
        };
        let manager = self.clone();
        tokio::task::spawn_blocking(move || {
            if let Some(directory) = directory {
                manager.access_history(|history| history.set_directory(directory))?;
            } else {
                std::fs::create_dir_all(&current).map_err(|_| "file_io_error")?;
                std::process::Command::new("explorer.exe")
                    .arg(&current)
                    .spawn()
                    .map_err(|_| "file_io_error")?;
            }
            manager.settings(&Value::Null)
        })
        .await
        .map_err(|_| "download_history_unavailable")?
    }

    fn automatic_target(&self, name: &str) -> Result<PathBuf, String> {
        let directory = self
            .history
            .as_ref()
            .ok_or("capability_unsupported")?
            .lock()
            .unwrap()
            .directory()?;
        std::fs::create_dir_all(&directory).map_err(|_| "file_io_error")?;
        let jobs = self.jobs.lock().unwrap();
        let original = directory.join(name);
        let stem = original
            .file_stem()
            .and_then(|s| s.to_str())
            .ok_or("invalid_input")?;
        let extension = original
            .extension()
            .and_then(|s| s.to_str())
            .ok_or("invalid_input")?;
        for index in 1..=10000 {
            let path = if index == 1 {
                original.clone()
            } else {
                directory.join(format!("{stem} ({index}).{extension}"))
            };
            let reserved = jobs.values().any(|j| {
                j.target == path
                    && matches!(
                        j.public["status"].as_str(),
                        Some("resolving" | "downloading")
                    )
            });
            if !path.exists() && !reserved {
                return Ok(path);
            }
        }
        Err("file_exists".into())
    }

    async fn record_saved(
        &self,
        id: &str,
        target: &Path,
        rep: &Value,
        source_preserved: bool,
    ) -> Result<(), String> {
        let Some(history) = &self.history else {
            return Ok(());
        };
        let r = self
            .jobs
            .lock()
            .unwrap()
            .get(id)
            .ok_or("track_not_found")?
            .recording
            .clone();
        let record = crate::download_history::SavedDownload {
            id: uuid::Uuid::new_v4().simple().to_string(),
            identity: r.identity,
            title: r.title,
            artist: r.artist,
            path: target.to_owned(),
            format: rep["extension"]
                .as_str()
                .ok_or("source_verification_failed")?
                .into(),
            size_bytes: rep["sizeBytes"]
                .as_u64()
                .ok_or("source_verification_failed")?,
            saved_at: now(),
            source_preserved,
        };
        let saved_id = record.id.clone();
        let history = history.clone();
        let saved = tokio::task::spawn_blocking(move || history.lock().unwrap().add(record))
            .await
            .unwrap_or_else(|_| Err("download_history_unavailable".into()));
        if let Err(error) = saved {
            self.update(id, json!({"historyError":error}));
            return Err(error);
        }
        self.update(id, json!({"savedId":saved_id}));
        Ok(())
    }

    pub fn settings(&self, body: &Value) -> Result<Value, String> {
        self.access_history(|history| {
            if !body.is_null() {
                let naming: Naming = serde_json::from_value(body["naming"].clone()).map_err(|_| "invalid_input")?;
                let value = serde_json::to_value(naming).map_err(|_| "invalid_input")?;
                history.transact(|tx| {
                    tx.execute("UPDATE download_settings SET naming=?1 WHERE singleton=1", [value.as_str()])?;
                    Ok(())
                }).map_err(|_| "file_io_error")?;
            }
            let (custom, naming) = history.settings()?;
            let default = history.default_directory();
            Ok(json!({
                "mode":"desktop", "naming":naming, "canManage":false, "deploymentLocked":false, "error":null,
                "directory":custom.as_deref().unwrap_or(default), "defaultDirectory":default,
                "usingDefaultDirectory":custom.is_none()
            }))
        })
    }

    fn naming(&self) -> Result<Naming, String> {
        if self.history.is_none() {
            return Ok(Naming::default());
        }
        self.access_history(|history| {
            serde_json::from_value(json!(history.settings()?.1))
                .map_err(|_| "download_history_unavailable".into())
        })
    }

    pub fn register(&self, page: &mut Value) {
        let mut records = self.recordings.lock().unwrap();
        if records.len() > 256 {
            records.clear();
        }
        if let Some(items) = page["items"].as_array_mut() {
            for row in items {
                let supported = ["kuwo", "qq", "netease", "migu"]
                    .iter()
                    .any(|p| row["identity"]["providerId"] == *p);
                if !supported {
                    row["downloadAllowed"] = json!(false);
                }
                if supported && row["downloadAllowed"] != false {
                    records.insert(
                        key(&row["identity"]),
                        Recording {
                            cover: row["cover"].as_str().map(str::to_owned),
                            quality: "standard".into(),
                            identity: row["identity"].clone(),
                            title: row["title"].as_str().unwrap_or("歌曲").into(),
                            artist: row["artists"]
                                .as_array()
                                .into_iter()
                                .flatten()
                                .filter_map(Value::as_str)
                                .collect::<Vec<_>>()
                                .join("、"),
                            duration: row["durationSeconds"].as_f64().unwrap_or(0.0),
                        },
                    );
                }
            }
        }
    }
    fn recording(&self, body: &Value) -> Result<Recording, String> {
        if body.get("path").is_some()
            || body.get("url").is_some()
            || body["outputMode"]
                .as_str()
                .is_some_and(|s| !["original", "mp3_320", "mp3_192"].contains(&s))
            || !["auto", "standard", "high", "lossless"]
                .contains(&body["quality"].as_str().unwrap_or(""))
        {
            return Err("capability_unsupported".into());
        }
        let mut recording = self
            .recordings
            .lock()
            .unwrap()
            .get(&key(&body["identity"]))
            .cloned()
            .ok_or("access_denied")?;
        recording.quality = body["quality"].as_str().unwrap().into();
        Ok(recording)
    }

    pub async fn options(&self, client: &reqwest::Client, body: &Value) -> Value {
        let value = async {
            let r = self.recording(body)?;
            tokio::time::timeout(Duration::from_secs(50), prefix(client, &r))
                .await
                .map_err(|_| "upstream_timeout".to_string())?
        }
        .await;
        match value {
            Ok(rep) => {
                json!({"quality":body["quality"],"availability":"available","representation":rep,"errorCode":null,"conversion":{"available":self.converter_available(),"reason":""}})
            }
            Err(error) => {
                json!({"quality":body["quality"],"availability":"unavailable","representation":null,"errorCode":error})
            }
        }
    }
    pub fn poll(&self) -> Result<Value, String> {
        self.access_history(|history| {
            history.reconcile();
            let mut jobs = self.jobs.lock().unwrap();
            jobs.retain(|_, job| {
                !matches!(
                    job.public["status"].as_str(),
                    Some("completed" | "cancelled")
                )
            });
            let tasks = jobs
                .values()
                .map(|job| job.public.clone())
                .collect::<Vec<_>>();
            drop(jobs);
            let saved = history
                .list()?
                .into_iter()
                .filter(|row| row.path.is_file())
                .map(|row| json!({"id": row.id, "identity": row.identity}))
                .collect::<Vec<_>>();
            Ok(json!({"tasks":tasks,"saved":saved}))
        })
    }

    #[cfg(test)]
    pub fn list(&self) -> Value {
        json!(self
            .jobs
            .lock()
            .unwrap()
            .values()
            .map(|j| j.public.clone())
            .collect::<Vec<_>>())
    }
    pub async fn create(&self, client: &reqwest::Client, body: &Value) -> Result<Value, String> {
        self.check_open()?;
        let mut recording = self.recording(body)?;
        let rep = tokio::select! {
            biased;
            _ = self.closing.cancelled() => return Err("download_shutting_down".into()),
            result = tokio::time::timeout(Duration::from_secs(50), prefix(client, &recording)) =>
                result.map_err(|_| "upstream_timeout")??,
        };
        if let Some(duration) = rep["expectedDurationSeconds"].as_f64().filter(|n| *n > 0.0) {
            recording.duration = duration;
        }
        let mode = body["outputMode"].as_str().unwrap_or("original");
        if mode != "original" && (rep["codec"] != "flac" || !self.converter_available()) {
            return Err("capability_unsupported".into());
        }
        let extension = if mode == "original" {
            rep["extension"].as_str().unwrap_or("mp3")
        } else {
            "mp3"
        };
        let manager = self.clone();
        let naming = tokio::task::spawn_blocking(move || manager.naming())
            .await
            .map_err(|_| "download_history_unavailable")??;
        let name = suggested_name(&recording, naming)
            .trim_end_matches(".mp3")
            .to_owned()
            + "."
            + extension;
        let save_as = body
            .get("saveAs")
            .map(|v| v.as_bool().ok_or("invalid_input"))
            .transpose()?
            .unwrap_or(false);
        self.check_open()?;
        let target = if save_as {
            let mut picker = rfd::AsyncFileDialog::new()
                .set_title("另存为音频")
                .add_filter("音频", &[extension])
                .set_file_name(name);
            if self.history.is_some() {
                let manager = self.clone();
                let directory = tokio::task::spawn_blocking(move || {
                    manager.access_history(|history| history.directory())
                })
                .await
                .map_err(|_| "download_history_unavailable")??;
                picker = picker.set_directory(directory);
            }
            let Some(file) = (tokio::select! {
                biased;
                _ = self.closing.cancelled() => return Err("download_shutting_down".into()),
                file = picker.save_file() => file,
            }) else {
                return Ok(Value::Null);
            };
            file.path().to_owned()
        } else {
            let manager = self.clone();
            tokio::task::spawn_blocking(move || manager.automatic_target(&name))
                .await
                .map_err(|_| "download_history_unavailable")??
        };
        self.start_mode(recording, target, client.clone(), mode)
    }

    fn check_open(&self) -> Result<(), String> {
        if self.closing.is_cancelled() {
            return Err("download_shutting_down".into());
        }
        Ok(())
    }

    fn converter_available(&self) -> bool {
        self.tools_dir
            .as_ref()
            .is_some_and(|dir| crate::transcode::available(dir))
    }
    fn start_mode(
        &self,
        r: Recording,
        target: PathBuf,
        client: reqwest::Client,
        mode: &str,
    ) -> Result<Value, String> {
        self.check_open()?;
        if target
            .extension()
            .and_then(|s| s.to_str())
            .is_none_or(|s| !["mp3", "m4a", "flac"].contains(&s.to_ascii_lowercase().as_str()))
        {
            return Err("file_io_error".into());
        }
        if mode != "original"
            && !target
                .extension()
                .is_some_and(|s| s.eq_ignore_ascii_case("mp3"))
        {
            return Err("invalid_input".into());
        }
        if target.exists() {
            return Err("file_exists".into());
        }
        let id = uuid::Uuid::new_v4().simple().to_string();
        let part = target.with_file_name(format!(".music-core-{id}.part"));
        let cancel = CancellationToken::new();
        let public = json!({"id":id,"identity":r.identity,"title":r.title,"artist":r.artist,"quality":r.quality,"outputMode":mode,"deliveryMode":"desktop","status":"resolving","receivedBytes":0,"createdAt":now(),"updatedAt":now()});
        {
            let mut jobs = self.jobs.lock().unwrap();
            self.check_open()?;
            if jobs.len() >= 128
                || jobs
                    .values()
                    .filter(|j| {
                        matches!(
                            j.public["status"].as_str(),
                            Some("resolving" | "downloading")
                        )
                    })
                    .count()
                    >= 3
            {
                return Err("media_capacity".into());
            }
            jobs.insert(
                id.clone(),
                Job {
                    public: public.clone(),
                    recording: r,
                    target,
                    part,
                    cancel: cancel.clone(),
                    owns_part: false,
                    owns_output: false,
                },
            );
        }
        let manager = self.clone();
        tokio::spawn(async move {
            let recording = manager.run(&id, &client, cancel).await;
            if let (Some(recording), Some(cache)) = (recording, manager.media_covers.1.as_ref()) {
                let _ = tokio::join!(
                    cache.cover(
                        &manager.media_covers,
                        &recording.identity,
                        recording.cover.as_deref(),
                        0
                    ),
                    cache.lyrics(&client, &recording.identity)
                );
            }
        });
        Ok(public)
    }
    fn update(&self, id: &str, fields: Value) {
        if let Some(j) = self.jobs.lock().unwrap().get_mut(id) {
            for (k, v) in fields.as_object().unwrap() {
                j.public[k] = v.clone();
            }
            j.public["updatedAt"] = json!(now());
        }
    }
    async fn run(
        &self,
        id: &str,
        client: &reqwest::Client,
        cancel: CancellationToken,
    ) -> Option<Recording> {
        let (r, target, part) = {
            let jobs = self.jobs.lock().unwrap();
            let j = &jobs[id];
            (j.recording.clone(), j.target.clone(), j.part.clone())
        };
        self.finish(
            id,
            &target,
            self.transfer(id, client, &r, &target, &part, &cancel),
        )
        .await
    }

    async fn cleanup_job(&self, id: &str) -> bool {
        let parts = self
            .jobs
            .lock()
            .unwrap()
            .get(id)
            .map(|job| (job.part.clone(), job.owns_part, job.owns_output));
        let Some((part, owns_part, owns_output)) = parts else {
            return false;
        };
        let (part_left, output_left) = clean_owned_parts(&part, owns_part, owns_output).await;
        if let Some(job) = self.jobs.lock().unwrap().get_mut(id) {
            job.owns_part = part_left;
            job.owns_output = output_left;
        }
        part_left || output_left
    }

    async fn finish(
        &self,
        id: &str,
        target: &Path,
        transfer: impl std::future::Future<Output = Result<Value, String>>,
    ) -> Option<Recording> {
        // 传输只在没有子进程的阶段丢弃等待。转换先等待自己的子进程退出。
        let result = transfer.await;
        let cleanup_failed = self.cleanup_job(id).await;
        let saved = self
            .jobs
            .lock()
            .unwrap()
            .get(id)
            .filter(|job| job.public["savedId"].is_string())
            .map(|job| job.recording.clone());
        let mut terminal = match result {
            Ok(rep) => json!({
                "status": if cleanup_failed { "failed" } else { "completed" },
                "phase": "completed",
                "errorCode": if cleanup_failed { Some("saved_temporary_cleanup_failed") } else { None },
                "filename": target.file_name().and_then(|s| s.to_str()),
                "format": rep["extension"].as_str().unwrap_or("mp3"), "route":rep["route"], "actualMedia": rep,
                "finalSizeBytes": rep["sizeBytes"], "progress": 1,
            }),
            Err(error) if error == "cancelled" && !cleanup_failed => {
                json!({"status":"cancelled","errorCode":null})
            }
            Err(error) => json!({
                "status":"failed",
                "errorCode": if error == "cancelled" { "temporary_cleanup_failed".into() } else { error },
            }),
        };
        if cleanup_failed {
            eprintln!("下载任务 {id} 的临时文件未全部清理");
            terminal["cleanupError"] = json!("temporary_cleanup_failed");
        }
        self.update(id, terminal);
        self.finished.notify_one();
        saved
    }
    async fn transfer(
        &self,
        id: &str,
        client: &reqwest::Client,
        r: &Recording,
        target: &Path,
        part: &Path,
        cancel: &CancellationToken,
    ) -> Result<Value, String> {
        let mut checked = r.clone();
        let (route, response) = tokio::select! {
            biased;
            _ = cancel.cancelled() => return Err("cancelled".into()),
            result = async {
                let (media, route) = if r.identity["providerId"] == "kuwo" {
                    let url = tokio::time::timeout(Duration::from_secs(20), resolve(client, r))
                        .await
                        .map_err(|_| "upstream_timeout")??;
                    let mut headers = reqwest::header::HeaderMap::new();
                    headers.insert("user-agent", "okhttp/3.10.0".parse().unwrap());
                    (
                        crate::provider::Media { url, headers },
                        "native".to_string(),
                    )
                } else {
                    let resolved = tokio::time::timeout(
                        Duration::from_secs(50),
                        crate::download_resolver::resolve(
                            client,
                            &crate::fallback::Config::from_env()?,
                            &r.identity,
                            &r.quality,
                            &r.title,
                            &r.artist,
                        ),
                    )
                    .await
                    .map_err(|_| "upstream_timeout")??;
                    if let Some(duration) = resolved.representation["expectedDurationSeconds"]
                        .as_f64()
                        .filter(|n| *n > 0.0)
                    {
                        checked.duration = duration;
                    }
                    (resolved.media, resolved.route)
                };
                self.update(id, json!({"route":route}));
                let response = client
                    .get(media.url)
                    .headers(media.headers)
                    .header("Accept-Encoding", "identity")
                    .send()
                    .await
                    .map_err(|_| "upstream_failure")?;
                Ok::<_, String>((route, response))
            } => result?,
        };
        let mut rep = self
            .save_response(id, &checked, target, part, response)
            .await?;
        rep["route"] = json!(route);
        rep["providerQualityId"] = json!(r.quality);
        Ok(rep)
    }
    async fn save_response(
        &self,
        id: &str,
        r: &Recording,
        target: &Path,
        part: &Path,
        mut response: reqwest::Response,
    ) -> Result<Value, String> {
        let cancel = self.jobs.lock().unwrap()[id].cancel.clone();
        if cancel.is_cancelled() {
            return Err("cancelled".into());
        }
        if response
            .headers()
            .get("content-encoding")
            .is_some_and(|v| v != "identity")
        {
            return Err("upstream_invalid_response".into());
        }
        let range = response
            .headers()
            .get("content-range")
            .map(|v| v.to_str())
            .transpose()
            .map_err(|_| "upstream_invalid_response")?;
        let declared = response
            .headers()
            .get("content-length")
            .map(|value| {
                let text = value.to_str().map_err(|_| "upstream_invalid_response")?;
                if text.is_empty() || !text.bytes().all(|b| b.is_ascii_digit()) {
                    return Err("upstream_invalid_response");
                }
                text.parse::<u64>().map_err(|_| "upstream_invalid_response")
            })
            .transpose()?;
        let transport_length = response.content_length();
        if declared.zip(transport_length).is_some_and(|(a, b)| a != b) {
            return Err("upstream_invalid_response".into());
        }
        let total = full_response_size(
            response.status().as_u16(),
            declared.or(transport_length),
            range,
        )?;
        if total.is_some_and(|n| n == 0 || n > MAX_DOWNLOAD_BYTES) {
            return Err("media_capacity".into());
        }
        self.update(
            id,
            json!({"status":"downloading","phase":"downloading","totalBytes":total}),
        );
        let mut file = tokio::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(part)
            .await
            .map_err(|_| "file_io_error")?;
        if let Some(job) = self.jobs.lock().unwrap().get_mut(id) {
            job.owns_part = true;
        }
        let mut received = 0u64;
        let writing = async {
            loop {
                let chunk = tokio::select! {
                    biased;
                    _ = cancel.cancelled() => return Err("cancelled".into()),
                    chunk = response.chunk() => chunk.map_err(|_| "upstream_failure")?,
                };
                let Some(chunk) = chunk else { break };
                received += chunk.len() as u64;
                if received > MAX_DOWNLOAD_BYTES {
                    return Err("media_capacity".into());
                }
                file.write_all(&chunk).await.map_err(|_| "file_io_error")?;
                self.update(
                    id,
                    json!({"receivedBytes":received,"progress":total.map(|n|received as f64/n as f64)}),
                );
            }
            Ok::<_, String>(())
        }.await;
        if let Err(error) = writing {
            // Tokio 文件写入可能还有后台工作，先释放句柄再清理任务文件。
            let _ = file.flush().await;
            return Err(error);
        }
        file.sync_all().await.map_err(|_| "file_io_error")?;
        drop(file);
        if cancel.is_cancelled() {
            return Err("cancelled".into());
        }
        if received == 0 || total.is_some_and(|n| n != received) {
            return Err("source_verification_failed".into());
        }
        self.update(id, json!({"phase":"verifying"}));
        let rep = crate::download_media::inspect_original(part, &r.quality)?;
        // 仅明确标准档要求 128k；自动和其他显式档由实际表示匹配。
        if r.identity["providerId"] == "kuwo"
            && r.quality == "standard"
            && (rep["codec"] != "mp3"
                || !rep["bitrateBps"]
                    .as_u64()
                    .is_some_and(|n| n.abs_diff(128000) <= 1000))
        {
            return Err("media_unavailable".into());
        }
        let mode = self.jobs.lock().unwrap()[id].public["outputMode"]
            .as_str()
            .unwrap_or("original")
            .to_owned();
        if cancel.is_cancelled() {
            return Err("cancelled".into());
        }
        if mode != "original" {
            if rep["codec"] != "flac" {
                return Err("source_verification_failed".into());
            }
            self.update(id, json!({"phase":"transcoding", "sourceMedia":rep}));
            let output = part.with_extension("mp3.part");
            let converted = async {
                let file = std::fs::OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .open(&output)
                    .map_err(|_| "file_io_error")?;
                drop(file);
                self.jobs.lock().unwrap().get_mut(id).unwrap().owns_output = true;
                let dir = self.tools_dir.as_ref().ok_or("conversion_unavailable")?;
                crate::transcode::convert(
                    dir,
                    part,
                    &output,
                    if mode == "mp3_320" { 320000 } else { 192000 },
                    &cancel,
                )
                .await
            }
            .await;
            let converted = match converted {
                Ok(value) => value,
                Err(error)
                    if matches!(error.as_str(), "cancelled" | "conversion_cleanup_failed") =>
                {
                    return Err(error)
                }
                Err(error) => {
                    self.save_failed_original(id, part, target, &rep, &error)
                        .await?;
                    return Err(if error == "conversion_timeout" {
                        error
                    } else {
                        "conversion_failed".into()
                    });
                }
            };
            if !target
                .extension()
                .is_some_and(|s| s.eq_ignore_ascii_case("mp3"))
            {
                self.save_failed_original(id, part, target, &rep, "invalid_output_extension")
                    .await?;
                return Err("conversion_failed".into());
            }
            self.update(id, json!({"phase":"publishing", "transcoded":true}));
            if let Err(error) = self.publish_if_active(id, &output, target) {
                if error == "cancelled" {
                    return Err(error);
                }
                self.save_failed_original(id, part, target, &rep, &error)
                    .await?;
                return Err("conversion_failed".into());
            }
            self.record_saved(id, target, &converted, false).await?;
            return Ok(converted);
        }
        let extension = rep["extension"].as_str().unwrap_or("mp3");
        if !target
            .extension()
            .and_then(|s| s.to_str())
            .is_some_and(|s| s.eq_ignore_ascii_case(extension))
        {
            return Err("source_verification_failed".into());
        }
        // 校验与无覆盖发布之间没有 await；取消不会留下未登记的正式文件。
        self.publish_if_active(id, part, target)?;
        self.record_saved(id, target, &rep, false).await?;
        Ok(rep)
    }
    async fn discard_failed_job(&self, id: &str) -> Result<(), String> {
        let job = {
            let mut jobs = self.jobs.lock().unwrap();
            self.check_open()?;
            if jobs
                .get(id)
                .is_none_or(|job| job.public["status"] != "failed")
            {
                return Err("track_not_found".into());
            }
            jobs.remove(id).unwrap()
        };
        let (part_left, output_left) =
            clean_owned_parts(&job.part, job.owns_part, job.owns_output).await;
        if part_left || output_left {
            eprintln!("放弃下载任务 {id} 时仍有临时文件未清理");
        }
        Ok(())
    }

    pub async fn operate(
        &self,
        id: &str,
        operation: &str,
        client: &reqwest::Client,
    ) -> Result<Value, String> {
        if operation == "remove" {
            self.discard_failed_job(id).await?;
            return Ok(Value::Null);
        }
        let body = {
            let jobs = self.jobs.lock().unwrap();
            let job = jobs.get(id).ok_or("track_not_found")?;
            let failed = job.public["status"] == "failed";
            match operation {
                "cancel" => {
                    if matches!(
                        job.public["status"].as_str(),
                        Some("resolving" | "downloading")
                    ) {
                        job.cancel.cancel();
                    }
                    return Ok(job.public.clone());
                }
                "retry" if failed => {
                    json!({
                        "identity":job.recording.identity, "quality":job.recording.quality,
                        "outputMode":job.public["outputMode"],
                        "title":job.recording.title, "artist":job.recording.artist, "cover":job.recording.cover,
                    })
                }
                _ => return Err("capability_unsupported".into()),
            }
        };
        let result = self.create(client, &body).await?;
        // 退出已接管剩余任务清理时，保留原记录交给退出流程。
        let _ = self.discard_failed_job(id).await;
        Ok(result)
    }
    fn publish_if_active(&self, id: &str, part: &Path, target: &Path) -> Result<(), String> {
        // 取消、退出与硬链接发布共用任务锁。发布成功后登记和收尾不再响应取消。
        let jobs = self.jobs.lock().unwrap();
        if self.closing.is_cancelled() || jobs[id].cancel.is_cancelled() {
            return Err("cancelled".into());
        }
        publish(part, target)
    }

    async fn save_failed_original(
        &self,
        id: &str,
        part: &Path,
        target: &Path,
        rep: &Value,
        error: &str,
    ) -> Result<(), String> {
        // 使用用户已选目录和文件名；后缀与原文件一致，同名时只添加序号，绝不覆盖。
        let stem = target.file_stem().unwrap_or_default().to_string_lossy();
        let extension = rep["extension"].as_str().unwrap_or("flac");
        let saved = (1..=10000)
            .find_map(|index| {
                let name = if index == 1 {
                    format!("{stem}.{extension}")
                } else {
                    format!("{stem} ({index}).{extension}")
                };
                let path = target.with_file_name(name);
                match self.publish_if_active(id, part, &path) {
                    Ok(()) => Some(Ok(path)),
                    Err(reason) if reason == "file_exists" => None,
                    Err(reason) => Some(Err(reason)),
                }
            })
            .unwrap_or_else(|| Err("file_exists".into()));
        match saved {
            Ok(path) => {
                let history_error = self.record_saved(id,&path,rep,true).await.err();
                self.update(id,json!({"sourcePreserved":true,"sourceFilename":path.file_name().and_then(|s|s.to_str()),"sourceSaveError":null,"conversionError":error,"historyError":history_error,"transcoded":false}));
            },
            Err(reason) if reason == "cancelled" => return Err(reason),
            Err(reason) => self.update(id,json!({"sourcePreserved":false,"sourceSaveError":reason,"conversionError":error,"transcoded":false})),
        }
        Ok(())
    }
    pub fn active(&self) -> bool {
        self.jobs.lock().unwrap().values().any(|j| {
            matches!(
                j.public["status"].as_str(),
                Some("resolving" | "downloading")
            )
        })
    }
    pub fn begin_shutdown(&self) -> bool {
        let jobs = self.jobs.lock().unwrap();
        if self.closing.is_cancelled() {
            return false;
        }
        self.closing.cancel();
        for job in jobs.values() {
            job.cancel.cancel();
        }
        true
    }

    pub async fn wait_for_shutdown(&self, timeout: Duration) -> bool {
        tokio::time::timeout(timeout, async {
            while self.active() {
                self.finished.notified().await;
            }
            let remaining: Vec<_> = self
                .jobs
                .lock()
                .unwrap()
                .iter()
                .filter(|(_, job)| job.owns_part || job.owns_output)
                .map(|(id, _)| id.clone())
                .collect();
            let results =
                futures_util::future::join_all(remaining.iter().map(|id| self.cleanup_job(id)))
                    .await;
            let residual = results.into_iter().filter(|failed| *failed).count();
            if residual != 0 {
                eprintln!("退出时仍有 {residual} 个任务的临时文件未完全清理");
            }
        })
        .await
        .is_ok()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use futures_util::StreamExt;
    #[tokio::test]
    async fn cleanup_failure_does_not_skip_other_owned_file() {
        let root = tempfile::tempdir().unwrap();
        let manager = Downloads::default();
        let part = root.path().join("owned.part");
        let target = root.path().join("saved.mp3");
        let output = part.with_extension("mp3.part");
        std::fs::write(&part, b"owned").unwrap();
        #[cfg(windows)]
        let locked = {
            use std::os::windows::fs::OpenOptionsExt;
            std::fs::write(&output, b"locked").unwrap();
            std::fs::OpenOptions::new()
                .read(true)
                .share_mode(1)
                .open(&output)
                .unwrap()
        };
        #[cfg(not(windows))]
        std::fs::create_dir(&output).unwrap();
        std::fs::write(&target, b"published").unwrap();
        let cancel = CancellationToken::new();
        manager.jobs.lock().unwrap().insert(
            "fixture".into(),
            Job {
                public: json!({"status":"downloading", "savedId":"saved"}),
                recording: Recording {
                    quality: "auto".into(),
                    cover: None,
                    identity: json!({}),
                    title: "fixture".into(),
                    artist: String::new(),
                    duration: 0.0,
                },
                target: target.clone(),
                part: part.clone(),
                cancel: cancel.clone(),
                owns_part: true,
                owns_output: true,
            },
        );
        manager
            .finish("fixture", &target, async { Ok(json!({})) })
            .await;
        assert!(!part.exists());
        assert!(output.exists());
        assert_eq!(
            manager.jobs.lock().unwrap()["fixture"].public["errorCode"],
            "saved_temporary_cleanup_failed"
        );
        assert_eq!(std::fs::read(target).unwrap(), b"published");
        #[cfg(windows)]
        {
            drop(locked);
            manager.discard_failed_job("fixture").await.unwrap();
            assert!(!output.exists());
        }
    }

    #[tokio::test]
    async fn shutdown_is_one_shot_and_waits_for_both_jobs() {
        let root = tempfile::tempdir().unwrap();
        let manager = Downloads::default();
        let recording = Recording {
            quality: "auto".into(),
            cover: None,
            identity: json!({}),
            title: "fixture".into(),
            artist: String::new(),
            duration: 0.0,
        };
        let client = reqwest::Client::new();
        assert!(manager.wait_for_shutdown(Duration::from_secs(1)).await);
        let finish_gate = CancellationToken::new();
        let mut workers = Vec::new();
        for id in ["first", "second"] {
            let part = root.path().join(format!("{id}.part"));
            let target = root.path().join(format!("{id}.mp3"));
            let cancel = CancellationToken::new();
            std::fs::write(&part, b"owned").unwrap();
            manager.jobs.lock().unwrap().insert(
                id.into(),
                Job {
                    public: json!({"id":id,"status":"downloading"}),
                    recording: recording.clone(),
                    target: target.clone(),
                    part,
                    cancel: cancel.clone(),
                    owns_part: true,
                    owns_output: false,
                },
            );
            let manager = manager.clone();
            let finish_gate = finish_gate.clone();
            workers.push(tokio::spawn(async move {
                manager
                    .finish(id, &target, async {
                        cancel.cancelled().await;
                        finish_gate.cancelled().await;
                        Err("cancelled".into())
                    })
                    .await;
            }));
        }
        assert!(manager.begin_shutdown());
        assert!(!manager.begin_shutdown());
        assert_eq!(
            manager.create(&client, &Value::Null).await.unwrap_err(),
            "download_shutting_down"
        );
        assert_eq!(
            manager
                .start_mode(recording, root.path().join("late.mp3"), client, "original")
                .unwrap_err(),
            "download_shutting_down"
        );
        assert!(!manager.wait_for_shutdown(Duration::from_millis(30)).await);
        assert!(root.path().join("first.part").exists());
        finish_gate.cancel();
        assert!(manager.wait_for_shutdown(Duration::from_secs(2)).await);
        for worker in workers {
            worker.await.unwrap();
        }
        assert!(!root.path().join("first.part").exists());
        assert!(!root.path().join("second.part").exists());
        assert!(manager
            .list()
            .as_array()
            .unwrap()
            .iter()
            .all(|job| job["status"] == "cancelled"));
    }

    #[tokio::test]
    async fn streaming_cancel_and_post_publish_cancel_have_distinct_results() {
        let root = tempfile::tempdir().unwrap();
        let manager = Downloads::with_history(
            root.path().join("config/music-core.sqlite3"),
            root.path().into(),
        )
        .unwrap();
        let recording = Recording {
            quality: "auto".into(),
            cover: None,
            identity: json!({"providerId":"qq","platformId":"fixture"}),
            title: "fixture".into(),
            artist: String::new(),
            duration: 0.0,
        };
        for after_publish in [false, true] {
            let id = if after_publish { "saved" } else { "streaming" };
            let part = root.path().join(format!("{id}.part"));
            let target = root.path().join(format!("{id}.mp3"));
            let cancel = CancellationToken::new();
            manager.jobs.lock().unwrap().insert(
                id.into(),
                Job {
                    public: json!({"id":id,"status":"downloading"}),
                    recording: recording.clone(),
                    target: target.clone(),
                    part: part.clone(),
                    cancel: cancel.clone(),
                    owns_part: false,
                    owns_output: false,
                },
            );
            if after_publish {
                manager
                    .finish(id, &target, async {
                        let result = manager
                            .save_response(
                                id,
                                &recording,
                                &target,
                                &part,
                                original_response(fixture(20), None, 200),
                            )
                            .await;
                        assert!(target.is_file());
                        cancel.cancel();
                        tokio::task::yield_now().await;
                        result
                    })
                    .await;
                assert!(target.is_file());
                assert_eq!(
                    manager.jobs.lock().unwrap()[id].public["status"],
                    "completed"
                );
            } else {
                let (sender, receiver) = tokio::sync::oneshot::channel();
                let body =
                    futures_util::stream::once(async { Ok::<_, std::io::Error>(fixture(20)) })
                        .chain(futures_util::stream::once(async {
                            sender.send(()).unwrap();
                            futures_util::future::pending::<Result<Vec<u8>, std::io::Error>>().await
                        }));
                let response = reqwest::Response::from(axum::http::Response::new(
                    reqwest::Body::wrap_stream(body),
                ));
                tokio::join!(
                    manager.finish(
                        id,
                        &target,
                        manager.save_response(id, &recording, &target, &part, response)
                    ),
                    async {
                        receiver.await.unwrap();
                        assert!(part.is_file());
                        cancel.cancel();
                    }
                );
                assert!(!target.exists());
                assert_eq!(
                    manager.jobs.lock().unwrap()[id].public["status"],
                    "cancelled"
                );
            }
            assert!(!part.exists());
        }
        assert_eq!(manager.saved().unwrap().as_array().unwrap().len(), 1);
    }

    fn original_response(body: Vec<u8>, length: Option<u64>, status: u16) -> reqwest::Response {
        let chunks = futures_util::stream::once(async move { Ok::<_, std::io::Error>(body) });
        let mut response = axum::http::Response::builder().status(status);
        if let Some(length) = length {
            response = response.header("content-length", length);
        }
        reqwest::Response::from(response.body(reqwest::Body::wrap_stream(chunks)).unwrap())
    }
    async fn original_save(
        manager: &Downloads,
        r: &Recording,
        target: &Path,
        part: &Path,
        response: reqwest::Response,
    ) -> Value {
        fixture_save(manager, r, target, part, response, "original").await
    }
    #[tokio::test]
    #[ignore = "现有四份 FLAC 正式任务路径：源轻量探查、容错转换、成品严格完整解码"]
    async fn retained_conversion_jobs() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        let dir = root.join(".runtime/task22").join(format!(
            "formal-tolerant-jobs-{}",
            uuid::Uuid::new_v4().simple()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let tools = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources/tools");
        assert!(crate::transcode::available(&tools));
        let samples = [
            (
                "normal",
                root.join(".runtime/task20/qq/RyaVocal - 晴天 (原唱 周杰伦).flac"),
            ),
            (
                "tang-faruxue",
                root.join(
                    ".runtime/tang-retained-20261117-8b1d94a3/QQ-0027oMO61wWi55-Tang-original.flac",
                ),
            ),
            (
                "yiluxiangbei",
                root.join(".runtime/task22/周杰伦 - 一路向北.flac"),
            ),
            (
                "qifengle",
                root.join(".runtime/task22/吴青峰 - 起风了.flac"),
            ),
        ];
        let mut records = Vec::new();
        for (label, path) in samples {
            let bytes = std::fs::read(&path).unwrap();
            let info = u64::from_be_bytes(bytes[18..26].try_into().unwrap());
            let declared_samples = info & ((1u64 << 36) - 1);
            let source_rate = info >> 44;
            for mode in ["mp3_320", "mp3_192"] {
                let manager = Downloads {
                    tools_dir: Some(tools.clone()),
                    ..Downloads::default()
                };
                let r = Recording {
                    cover: None,
                    quality: if ["yiluxiangbei", "qifengle"].contains(&label) {
                        "auto"
                    } else {
                        "lossless"
                    }
                    .into(),
                    identity: json!({"providerId":"qq","platformId":"existing-fixture"}),
                    title: label.into(),
                    artist: "task22".into(),
                    duration: 0.0,
                };
                let target = dir.join(format!("{label}-{mode}.mp3"));
                let part = dir.join(format!(".{label}-{mode}-source.part"));
                let task = fixture_save(
                    &manager,
                    &r,
                    &target,
                    &part,
                    original_response(bytes.clone(), Some(bytes.len() as u64), 200),
                    mode,
                )
                .await;
                assert_eq!(task["status"], "completed", "{task}");
                assert_eq!(
                    task["actualMedia"]["bitrateBps"],
                    if mode == "mp3_320" { 320000 } else { 192000 }
                );
                let rep = &task["actualMedia"];
                let duration = rep["decodedSamples"].as_u64().unwrap() as f64
                    / rep["sampleRateHz"].as_u64().unwrap() as f64;
                assert!(
                    (duration - declared_samples as f64 / source_rate as f64).abs()
                        <= 2.0 / rep["sampleRateHz"].as_u64().unwrap() as f64
                );
                assert!(target.exists());
                assert!(!part.exists() && !part.with_extension("mp3.part").exists());
                records.push(json!({"sample":label,"input":path,"declaredSourceSamples":declared_samples,"mode":mode,"target":target,"task":task}));
            }
        }
        std::fs::write(
            dir.join("conversion-results.json"),
            serde_json::to_vec_pretty(&records).unwrap(),
        )
        .unwrap();
        std::fs::write(
            root.join(".runtime/task22/formal-tolerant-results-current.txt"),
            dir.to_string_lossy().as_bytes(),
        )
        .unwrap();
        println!("formal conversion results: {}", dir.display());
    }
    #[tokio::test]
    #[ignore = "已有 FLAC：失败自动落盘原文件、冲突、取消及容量保护"]
    async fn conversion_job_edges() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        let dir = root.join(".runtime/task22").join(format!(
            "automatic-original-{}",
            uuid::Uuid::new_v4().simple()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let bytes =
            std::fs::read(root.join(".runtime/task20/qq/RyaVocal - 晴天 (原唱 周杰伦).flac"))
                .unwrap();
        let r = Recording {
            cover: None,
            quality: "auto".into(),
            identity: json!({"providerId":"qq","platformId":"fixture"}),
            title: "fixture".into(),
            artist: "task22".into(),
            duration: 0.0,
        };
        let manager = Downloads::default();
        assert!(!manager.converter_available());
        let target = dir.join("chosen.mp3");
        let part = dir.join("owned.part");
        let original = dir.join("chosen.flac");
        // 缺工具也不影响原格式保存。
        let task = original_save(
            &manager,
            &r,
            &original,
            &part,
            original_response(bytes.clone(), None, 200),
        )
        .await;
        assert_eq!(task["status"], "completed");
        assert_eq!(std::fs::read(&original).unwrap(), bytes);
        std::fs::write(&original, b"existing original").unwrap();
        let task = fixture_save(
            &manager,
            &r,
            &target,
            &part,
            original_response(bytes.clone(), None, 200),
            "mp3_320",
        )
        .await;
        assert_eq!(task["status"], "failed");
        assert_eq!(task["errorCode"], "conversion_failed");
        assert_eq!(task["sourcePreserved"], true);
        assert_eq!(task["sourceFilename"], "chosen (2).flac");
        assert_eq!(std::fs::read(&original).unwrap(), b"existing original");
        assert_eq!(std::fs::read(dir.join("chosen (2).flac")).unwrap(), bytes);
        let sentinel = part.with_extension("mp3.part");
        std::fs::write(&sentinel, b"not owned").unwrap();
        let task = fixture_save(
            &manager,
            &r,
            &target,
            &part,
            original_response(bytes.clone(), None, 200),
            "mp3_192",
        )
        .await;
        assert_eq!(task["sourcePreserved"], true);
        assert_eq!(std::fs::read(&sentinel).unwrap(), b"not owned");
        std::fs::remove_file(&sentinel).unwrap();
        let manager = Downloads {
            tools_dir: Some(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources/tools")),
            ..Downloads::default()
        };
        let cancel = async {
            loop {
                let token = {
                    manager
                        .jobs
                        .lock()
                        .unwrap()
                        .get("original-fixture")
                        .filter(|j| j.owns_output)
                        .map(|j| j.cancel.clone())
                };
                if let Some(token) = token {
                    tokio::time::sleep(Duration::from_millis(20)).await;
                    token.cancel();
                    break;
                }
                tokio::time::sleep(Duration::from_millis(1)).await;
            }
        };
        let (task, ()) = tokio::join!(
            fixture_save(
                &manager,
                &r,
                &target,
                &part,
                original_response(bytes.clone(), None, 200),
                "mp3_320"
            ),
            cancel
        );
        assert_eq!(task["status"], "cancelled");
        assert_ne!(task["sourcePreserved"], true);
        assert!(!target.exists() && !part.exists() && !sentinel.exists());
        let truncated = &bytes[..bytes.len() - 10000];
        let task = fixture_save(
            &manager,
            &r,
            &target,
            &part,
            original_response(truncated.to_vec(), None, 200),
            "mp3_192",
        )
        .await;
        assert_eq!(task["status"], "failed");
        assert_eq!(task["sourcePreserved"], true);
        assert!(!target.exists());
        let saved = dir.join(task["sourceFilename"].as_str().unwrap());
        assert_eq!(std::fs::read(&saved).unwrap(), truncated);
        assert!(manager.begin_shutdown());
        assert!(manager.wait_for_shutdown(Duration::from_secs(8)).await);
        assert!(saved.exists(), "退出只清理临时文件，不能删除已保存的原文件");
        // 原文件也无法发布时，不得报告已保存。
        let absent = dir.join("absent").join("chosen.mp3");
        let task = fixture_save(
            &manager,
            &r,
            &absent,
            &part,
            original_response(truncated.to_vec(), None, 200),
            "mp3_320",
        )
        .await;
        assert_eq!(task["status"], "failed");
        assert_eq!(task["sourcePreserved"], false);
        assert!(!part.exists());
        std::fs::write(dir.join("results.json"),serde_json::to_vec_pretty(&json!({"missingToolsOriginal":true,"conversionFailureAutomaticallySavesOriginal":true,"originalBytesIdentical":true,"sameNameNeverOverwritten":true,"unownedOutputPreserved":true,"cancelledChildCleanup":true,"incompleteMP3NotPublished":true,"savedOriginalSurvivesShutdown":true,"failedOriginalSaveNeverClaimsSaved":true})).unwrap()).unwrap();
        std::fs::write(
            root.join(".runtime/task22/automatic-original-results-current.txt"),
            dir.to_string_lossy().as_bytes(),
        )
        .unwrap();
    }
    async fn fixture_save(
        manager: &Downloads,
        r: &Recording,
        target: &Path,
        part: &Path,
        response: reqwest::Response,
        mode: &str,
    ) -> Value {
        let cancel = CancellationToken::new();
        manager.jobs.lock().unwrap().insert(
            "original-fixture".into(),
            Job {
                public: json!({"status":"resolving","outputMode":mode}),
                recording: r.clone(),
                target: target.into(),
                part: part.into(),
                cancel: cancel.clone(),
                owns_part: false,
                owns_output: false,
            },
        );
        manager
            .finish(
                "original-fixture",
                target,
                manager.save_response("original-fixture", r, target, part, response),
            )
            .await;
        assert!(
            !part.exists(),
            "本任务临时文件应已清理，保底原文件已正式发布"
        );
        manager.list()[0].clone()
    }

    #[cfg(windows)]
    #[tokio::test]
    #[ignore = "Windows 回收站专项，需要随包 FFmpeg，使用合成音频和临时目录"]
    async fn published_downloads_recycle_after_part_cleanup() {
        use crate::{
            delete_plan::{Plans, Target},
            file_recycle, local_library,
        };

        let root = tempfile::tempdir().unwrap();
        let settings = root.path().join("config/music-core.sqlite3");
        let tools = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources/tools");
        assert!(
            crate::transcode::available(&tools),
            "请先准备 FFmpeg 和 FFprobe"
        );
        let pcm = root.path().join("synthetic.pcm");
        let samples: Vec<u8> = (0..3 * 44_100)
            .flat_map(|sample| {
                let phase = f64::from(sample) * std::f64::consts::TAU * 480.0 / 44_100.0;
                ((phase.sin() * 4_000.0) as i16).to_le_bytes()
            })
            .collect();
        std::fs::write(&pcm, samples).unwrap();
        let source = root.path().join("synthetic.flac");
        let output = std::process::Command::new(tools.join("ffmpeg.exe"))
            .args([
                "-nostdin", "-v", "error", "-f", "s16le", "-ar", "44100", "-ac", "1", "-i",
            ])
            .arg(&pcm)
            .args(["-c:a", "flac"])
            .arg(&source)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        let bytes = std::fs::read(&source).unwrap();
        let recording = Recording {
            cover: None,
            quality: "auto".into(),
            identity: json!({"providerId":"qq","platformId":"fixture"}),
            title: "临时测试音频".into(),
            artist: "测试".into(),
            duration: 0.0,
        };
        let mut plans = Plans::default();

        for (label, extension, mode, has_tools) in [
            ("original", "flac", "original", true),
            ("converted", "mp3", "mp3_320", true),
            ("retained", "mp3", "mp3_320", false),
            ("existing", "flac", "original", true),
        ] {
            let mut manager =
                Downloads::with_history(settings.clone(), root.path().into()).unwrap();
            manager.tools_dir = has_tools.then(|| tools.clone());
            let target = root.path().join(format!(
                "music-core-{label}-{}.{}",
                uuid::Uuid::new_v4().simple(),
                extension
            ));
            let part = target.with_extension("part");
            let job = fixture_save(
                &manager,
                &recording,
                &target,
                &part,
                original_response(bytes.clone(), None, 200),
                mode,
            )
            .await;
            let published = if has_tools {
                assert_eq!(job["status"], "completed", "{job}");
                target
            } else {
                assert_eq!(job["errorCode"], "conversion_failed");
                assert_eq!(job["sourcePreserved"], true);
                target.with_extension("flac")
            };
            assert!(!part.with_extension("mp3.part").exists());
            let mut expected = std::fs::read(&published).unwrap();
            if extension == "flac" || !has_tools {
                assert_eq!(expected, bytes);
            }

            if label == "existing" {
                // 经本地播放代理读完音频并释放会话，再模拟外部标签编辑与应用重启。
                let sessions = crate::sessions::Sessions::new();
                let session = sessions.insert_local(published.clone(), "audio/flac");
                let client = reqwest::Client::new();
                let port = crate::transport::start(crate::transport::Transport {
                    sessions: sessions.clone(),
                    client: client.clone(),
                })
                .await
                .unwrap();
                let url = format!("http://127.0.0.1:{port}/api/playback/{session}/stream");
                let response = client
                    .get(&url)
                    .send()
                    .await
                    .unwrap()
                    .error_for_status()
                    .unwrap();
                assert_eq!(response.bytes().await.unwrap().as_ref(), expected);
                sessions.close(&session);
                assert_eq!(client.get(&url).send().await.unwrap().status(), 410);

                let tagged = root.path().join("tagged.flac");
                let output = std::process::Command::new(tools.join("ffmpeg.exe"))
                    .args(["-nostdin", "-v", "error", "-i"])
                    .arg(&published)
                    .args(["-c", "copy", "-metadata", "title=Updated title"])
                    .arg(&tagged)
                    .output()
                    .unwrap();
                assert!(
                    output.status.success(),
                    "{}",
                    String::from_utf8_lossy(&output.stderr)
                );
                std::fs::rename(tagged, &published).unwrap();
                let updated = std::fs::read(&published).unwrap();
                assert_ne!(updated, expected);
                expected = updated;

                drop(manager);
                manager = Downloads::with_history(settings.clone(), root.path().into()).unwrap();
            }
            let id = local_library::path_key(&published);
            let plan = manager
                .access_history(|history| Target::resolve(history, &id, None, &[]))
                .unwrap();
            let token = plans.prepare(plan);
            assert!(manager
                .access_history(|history| plans.take(&token)?.execute(history, &[]))
                .unwrap());
            assert!(plans.take(&token).is_err());
            assert!(!published.exists());
            file_recycle::restore_test_file(&published);
            assert_eq!(std::fs::read(&published).unwrap(), expected);
            let reopened = Downloads::with_history(settings.clone(), root.path().into()).unwrap();
            assert!(reopened.library_snapshot().unwrap().0.is_empty());
        }
    }

    #[tokio::test]
    async fn published_audio_survives_sql_failure_and_shutdown_waits_for_slow_history() {
        let root = tempfile::tempdir().unwrap();
        let manager = Downloads::with_database(Database::memory(), root.path().into());
        let recording = Recording {
            cover: None,
            quality: "auto".into(),
            identity: json!({"providerId":"qq","platformId":"fixture"}),
            title: "fixture".into(),
            artist: String::new(),
            duration: 0.0,
        };
        let raw = fixture(20);
        let failed = root.path().join("failed.mp3");
        manager
            .access_history(|history| {
                history.reject_writes(true);
                Ok(())
            })
            .unwrap();
        let task = original_save(
            &manager,
            &recording,
            &failed,
            &root.path().join("failed.part"),
            original_response(raw.clone(), None, 200),
        )
        .await;
        assert_eq!(task["historyError"], "download_history_unavailable");
        assert_eq!(task["status"], "failed");
        assert!(task["savedId"].is_null());
        assert_eq!(std::fs::read(&failed).unwrap(), raw);
        assert!(manager.saved_records().unwrap().is_empty());
        manager
            .access_history(|history| {
                history.reject_writes(false);
                Ok(())
            })
            .unwrap();

        let (release, wait) = std::sync::mpsc::channel();
        let (held, ready) = tokio::sync::oneshot::channel();
        let locking = manager.clone();
        let history_task = tokio::task::spawn_blocking(move || {
            locking.access_history(|_| {
                held.send(()).unwrap();
                let _ = wait.recv();
                Ok(())
            })
        });
        ready.await.unwrap();
        let target = root.path().join("slow.mp3");
        let part = root.path().join("slow.part");
        let saving = manager.clone();
        let saved_path = target.clone();
        let job = tokio::spawn(async move {
            original_save(
                &saving,
                &recording,
                &saved_path,
                &part,
                original_response(raw, None, 200),
            )
            .await
        });
        tokio::time::timeout(Duration::from_secs(5), async {
            while !target.is_file() {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .unwrap();
        assert!(manager.begin_shutdown());
        assert!(!manager.wait_for_shutdown(Duration::from_millis(30)).await);
        release.send(()).unwrap();
        history_task.await.unwrap().unwrap();
        assert_eq!(job.await.unwrap()["status"], "completed");
        assert!(manager.wait_for_shutdown(Duration::from_secs(1)).await);
        assert_eq!(manager.saved_records().unwrap()[0].path, target);
    }

    #[tokio::test]
    async fn desktop_poll_hands_off_products_and_retires_finalized_jobs() {
        let root = tempfile::tempdir().unwrap();
        let manager = Downloads::with_history(
            root.path().join("config/music-core.sqlite3"),
            root.path().into(),
        )
        .unwrap();
        let recording = Recording {
            cover: None,
            quality: "auto".into(),
            identity: json!({"providerId":"qq","platformId":"fixture"}),
            title: "fixture".into(),
            artist: "test".into(),
            duration: 0.0,
        };
        let part = root.path().join("job.part");
        let first = root.path().join("first.mp3");
        let second = root.path().join("second.mp3");
        for target in [&first, &second] {
            let task = original_save(
                &manager,
                &recording,
                target,
                &part,
                original_response(fixture(20), None, 200),
            )
            .await;
            assert_eq!(task["status"], "completed");
            let snapshot = manager.poll().unwrap();
            assert_eq!(snapshot["tasks"], json!([]));
            assert!(manager.jobs.lock().unwrap().is_empty());
        }

        let initial = manager.poll().unwrap();
        assert_eq!(initial["saved"].as_array().unwrap().len(), 2);
        assert!(initial["saved"]
            .as_array()
            .unwrap()
            .iter()
            .all(|row| row["identity"] == recording.identity));
        manager
            .access_history(|history| {
                history.remove_song(&first, &crate::local_library::path_key(&first), false)
            })
            .unwrap();
        assert!(first.is_file());
        assert_eq!(
            manager.poll().unwrap()["saved"].as_array().unwrap().len(),
            1
        );
        std::fs::rename(second, root.path().join("moved.mp3")).unwrap();
        assert_eq!(manager.poll().unwrap()["saved"], json!([]));

        for (id, status) in [
            ("cancelled", "cancelled"),
            ("failed", "failed"),
            ("active", "downloading"),
        ] {
            manager.jobs.lock().unwrap().insert(
                id.into(),
                Job {
                    public: json!({"id":id,"status":status}),
                    recording: recording.clone(),
                    target: first.clone(),
                    part: part.clone(),
                    cancel: CancellationToken::new(),
                    owns_part: false,
                    owns_output: false,
                },
            );
        }
        assert_eq!(
            manager.poll().unwrap()["tasks"].as_array().unwrap().len(),
            2
        );
        assert!(!manager.jobs.lock().unwrap().contains_key("cancelled"));
        let client = reqwest::Client::new();
        manager.operate("failed", "remove", &client).await.unwrap();
        assert_eq!(
            manager.poll().unwrap()["tasks"],
            json!([{"id":"active","status":"downloading"}])
        );
    }

    #[tokio::test]
    async fn saved_products_survive_restart_in_default_and_save_as_locations() {
        let root = tempfile::tempdir().unwrap();
        let settings = root.path().join("config/music-core.sqlite3");
        let default = root.path().join("redirected-system-music/拾音");
        let outside = root.path().join("outside-library");
        std::fs::create_dir_all(&outside).unwrap();
        let manager = Downloads::with_history(settings.clone(), default.clone()).unwrap();
        let r = Recording {
            cover: None,
            quality: "auto".into(),
            identity: json!({"providerId":"qq","platformId":"fixture"}),
            title: "已有测试音频".into(),
            artist: "测试".into(),
            duration: 0.0,
        };
        let bytes = fixture(20);
        let first = manager.automatic_target("测试 - 已有测试音频.mp3").unwrap();
        assert_eq!(first.parent().unwrap(), default);
        let task = original_save(
            &manager,
            &r,
            &first,
            &first.with_extension("part"),
            original_response(bytes.clone(), None, 200),
        )
        .await;
        assert_eq!(task["status"], "completed");
        let second = outside.join("用户另存名称.mp3");
        let task = original_save(
            &manager,
            &r,
            &second,
            &second.with_extension("part"),
            original_response(bytes.clone(), None, 200),
        )
        .await;
        assert_eq!(task["status"], "completed");
        assert_eq!(std::fs::read(&first).unwrap(), bytes);
        assert_eq!(std::fs::read(&second).unwrap(), bytes);
        let reopened = Downloads::with_history(settings.clone(), default.clone()).unwrap();
        assert_eq!(
            reopened.list().as_array().unwrap().len(),
            0,
            "不伪造持久任务"
        );
        let saved = reopened.saved().unwrap();
        assert_eq!(saved.as_array().unwrap().len(), 2);
        assert!(saved[0].get("fileId").is_none());
        assert_eq!(
            reopened
                .saved_path(saved[0]["id"].as_str().unwrap())
                .unwrap(),
            second
        );
        assert_eq!(
            reopened
                .saved_path(saved[1]["id"].as_str().unwrap())
                .unwrap(),
            first
        );
        assert_eq!(saved[0]["format"], "mp3");
        assert!(saved[0]["savedAt"].as_u64().unwrap() > 0);
        assert_ne!(
            reopened
                .automatic_target("测试 - 已有测试音频.mp3")
                .unwrap(),
            first,
            "同名不能覆盖"
        );
        let changed = root.path().join("new-default");
        reopened
            .history
            .as_ref()
            .unwrap()
            .lock()
            .unwrap()
            .set_directory(Some(changed.clone()))
            .unwrap();
        assert_eq!(
            reopened
                .automatic_target("later.mp3")
                .unwrap()
                .parent()
                .unwrap(),
            changed
        );
        let reopened = Downloads::with_history(settings, default).unwrap();
        assert_eq!(
            reopened.settings(&Value::Null).unwrap()["directory"],
            json!(changed)
        );
        assert_eq!(reopened.saved().unwrap(), saved, "改目录不重写旧记录路径");
        assert!(first.exists() && second.exists());
        assert_eq!(reopened.settings(&Value::Null).unwrap()["mode"], "desktop");
        let failed = outside.join("failed.mp3");
        let task = original_save(
            &reopened,
            &r,
            &failed,
            &failed.with_extension("part"),
            original_response(Vec::new(), None, 200),
        )
        .await;
        assert_eq!(task["status"], "failed");
        assert_eq!(reopened.saved().unwrap(), saved, "未落盘不登记成品");
    }

    #[tokio::test]
    async fn cancelled_transfer_never_registers_a_product() {
        let root = tempfile::tempdir().unwrap();
        let manager = Downloads::with_history(
            root.path().join("config/music-core.sqlite3"),
            root.path().join("music/拾音"),
        )
        .unwrap();
        let target = manager.automatic_target("cancelled.mp3").unwrap();
        let part = target.with_extension("part");
        let r = Recording {
            cover: None,
            quality: "auto".into(),
            identity: json!({"providerId":"qq","platformId":"fixture"}),
            title: "cancel".into(),
            artist: "test".into(),
            duration: 0.0,
        };
        let cancel = CancellationToken::new();
        cancel.cancel();
        manager.jobs.lock().unwrap().insert(
            "cancel".into(),
            Job {
                public: json!({"status":"downloading"}),
                recording: r.clone(),
                target: target.clone(),
                part: part.clone(),
                cancel: cancel.clone(),
                owns_part: false,
                owns_output: false,
            },
        );
        manager
            .finish(
                "cancel",
                &target,
                manager.save_response(
                    "cancel",
                    &r,
                    &target,
                    &part,
                    original_response(fixture(20), None, 200),
                ),
            )
            .await;
        assert_eq!(manager.list()[0]["status"], "cancelled");
        assert!(!target.exists() && !part.exists());
        assert!(manager.saved().unwrap().as_array().unwrap().is_empty());
    }

    #[tokio::test]
    #[ignore = "已有 FLAC：原格式、转码和回退成品的持久记录；不访问网络"]
    async fn actual_products_and_history_roundtrip() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        let dir = root.join(".runtime").join(format!(
            "download-history-{}",
            uuid::Uuid::new_v4().simple()
        ));
        let settings = dir.join("config/music-core.sqlite3");
        let default = dir.join("music/拾音");
        let bytes =
            std::fs::read(root.join(".runtime/task20/qq/RyaVocal - 晴天 (原唱 周杰伦).flac"))
                .unwrap();
        let mut manager = Downloads::with_history(settings.clone(), default.clone()).unwrap();
        manager.tools_dir = Some(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources/tools"));
        let r = Recording {
            cover: None,
            quality: "lossless".into(),
            identity: json!({"providerId":"netease","platformId":"2668397359"}),
            title: "晴天 (原唱 周杰伦)".into(),
            artist: "RyaVocal".into(),
            duration: 0.0,
        };
        for (name, mode, fallback) in [
            ("original.flac", "original", false),
            ("converted.mp3", "mp3_320", false),
            ("failed-conversion.mp3", "mp3_192", true),
        ] {
            if fallback {
                manager.tools_dir = None;
            }
            let target = manager.automatic_target(name).unwrap();
            let part = target.with_extension("part");
            let task = fixture_save(
                &manager,
                &r,
                &target,
                &part,
                original_response(bytes.clone(), None, 200),
                mode,
            )
            .await;
            assert_eq!(
                task["status"],
                if fallback { "failed" } else { "completed" }
            );
            assert_eq!(task["sourcePreserved"] == true, fallback);
            assert!(task["savedId"].is_string());
        }
        let reopened = Downloads::with_history(settings, default).unwrap();
        let records = reopened.saved().unwrap();
        assert_eq!(records.as_array().unwrap().len(), 3);
        assert_eq!(records[0]["format"], "flac");
        assert_eq!(records[0]["sourcePreserved"], true);
        assert_eq!(records[1]["format"], "mp3");
        assert_eq!(records[2]["format"], "flac");
        for record in records.as_array().unwrap() {
            let path = reopened.saved_path(record["id"].as_str().unwrap()).unwrap();
            assert!(path.is_file());
            if record["format"] == "flac" {
                assert_eq!(std::fs::read(path).unwrap(), bytes);
            }
        }
        std::fs::write(
            dir.join("results.json"),
            serde_json::to_vec_pretty(&records).unwrap(),
        )
        .unwrap();
        println!("history validation: {}", dir.display());
    }

    #[tokio::test]
    async fn preserved_original_is_a_saved_product_not_a_successful_conversion() {
        let root = tempfile::tempdir().unwrap();
        let settings = root.path().join("config/music-core.sqlite3");
        let default = root.path().join("music/拾音");
        let manager = Downloads::with_history(settings.clone(), default.clone()).unwrap();
        let target = manager.automatic_target("chosen.mp3").unwrap();
        let part = target.with_extension("part");
        let bytes = fixture(20);
        std::fs::write(&part, &bytes).unwrap();
        let r = Recording {
            cover: None,
            quality: "auto".into(),
            identity: json!({"providerId":"qq","platformId":"fixture"}),
            title: "fallback".into(),
            artist: "test".into(),
            duration: 0.0,
        };
        manager.jobs.lock().unwrap().insert(
            "fallback".into(),
            Job {
                public: json!({"status":"downloading","outputMode":"mp3_320"}),
                recording: r,
                target: target.clone(),
                part: part.clone(),
                cancel: CancellationToken::new(),
                owns_part: true,
                owns_output: false,
            },
        );
        let rep = crate::download_media::inspect_original(&part, "auto").unwrap();
        manager
            .save_failed_original("fallback", &part, &target, &rep, "fixture_encoder_failure")
            .await
            .unwrap();
        manager
            .finish("fallback", &target, async {
                Err("conversion_failed".into())
            })
            .await;
        assert_eq!(manager.list()[0]["status"], "failed");
        assert_eq!(manager.list()[0]["sourcePreserved"], true);
        let reopened = Downloads::with_history(settings, default).unwrap();
        let saved = reopened.saved().unwrap();
        assert_eq!(saved.as_array().unwrap().len(), 1);
        assert_eq!(saved[0]["format"], "mp3");
        assert_eq!(saved[0]["sourcePreserved"], true);
        let path = reopened
            .saved_path(saved[0]["id"].as_str().unwrap())
            .unwrap();
        assert_eq!(std::fs::read(path).unwrap(), bytes);
        assert!(!part.exists());
    }

    #[tokio::test]
    async fn auto_large_source_reaches_transfer_checks() {
        let dir = folder();
        let manager = Downloads::default();
        let r = Recording {
            cover: None,
            quality: "auto".into(),
            identity: json!({"providerId":"qq","platformId":"fixture"}),
            title: "auto".into(),
            artist: "test".into(),
            duration: 0.0,
        };
        let target = dir.join("large.flac");
        let part = dir.join("large.part");
        // 200 MiB 允许进入接收流程，空 body 只因实际长度不足失败；不是容量拒绝。
        let task = original_save(
            &manager,
            &r,
            &target,
            &part,
            original_response(Vec::new(), Some(200 * 1024 * 1024), 200),
        )
        .await;
        assert_eq!(task["errorCode"], "source_verification_failed");
        let task = original_save(
            &manager,
            &r,
            &target,
            &part,
            original_response(Vec::new(), Some(MAX_DOWNLOAD_BYTES + 1), 200),
        )
        .await;
        assert_eq!(task["errorCode"], "media_capacity");
        assert!(!target.exists());
        std::fs::remove_dir(dir).unwrap();
    }
    #[tokio::test]
    async fn original_response_basics() {
        let dir = folder();
        let target = dir.join("saved.mp3");
        let part = dir.join("owned.part");
        let manager = Downloads::default();
        let mut r = Recording {
            cover: None,
            quality: "standard".into(),
            identity: json!({"providerId":"qq","platformId":"fixture"}),
            title: "夹具".into(),
            artist: "测试".into(),
            duration: 0.0,
        };
        let normal = fixture(20);
        // 已知长度和未知长度均可正常保存；没有时长不引入整首时长校验门槛。
        for total in [Some(normal.len() as u64), None] {
            let task = original_save(
                &manager,
                &r,
                &target,
                &part,
                original_response(normal.clone(), total, 200),
            )
            .await;
            assert_eq!(task["status"], "completed");
            if total.is_none() {
                assert!(task["totalBytes"].is_null());
            }
            assert_eq!(std::fs::read(&target).unwrap(), normal);
            std::fs::remove_file(&target).unwrap();
        }
        for (body, total, status) in [
            (b"<html>not audio</html>".to_vec(), None, 200),
            (Vec::new(), None, 200),
            (normal[..417].to_vec(), Some(normal.len() as u64), 200),
            (normal.clone(), Some(normal.len() as u64), 500),
        ] {
            let task = original_save(
                &manager,
                &r,
                &target,
                &part,
                original_response(body, total, status),
            )
            .await;
            assert_eq!(task["status"], "failed");
            assert!(!target.exists());
        }
        r.quality = "lossless".into();
        let task = original_save(
            &manager,
            &r,
            &target,
            &part,
            original_response(normal, None, 200),
        )
        .await;
        assert_eq!(task["status"], "failed");
        assert!(!target.exists());
        r.quality = "standard".into();
        let wrong_extension = dir.join("wrong.flac");
        let task = original_save(
            &manager,
            &r,
            &wrong_extension,
            &part,
            original_response(fixture(20), None, 200),
        )
        .await;
        assert_eq!(task["status"], "failed");
        assert!(!wrong_extension.exists());
        std::fs::remove_dir(dir).unwrap();
    }
    #[tokio::test]
    #[ignore = "仅回放已有本地 Tang 文件，不取链、不访问网络；保留原样保存结果供人工复核"]
    async fn original_retained_file_roundtrip() {
        original_local_file_roundtrip("QQ-0027oMO61wWi55-Tang-original.flac", "lossless", "flac")
            .await;
    }
    #[tokio::test]
    #[ignore = "仅回放已有正常 MP3 文件，不取链、不访问网络"]
    async fn original_normal_file_roundtrip() {
        original_local_file_roundtrip("QQ-0027oMO61wWi55-Tang-320kbps-preview.mp3", "high", "mp3")
            .await;
    }
    async fn original_local_file_roundtrip(name: &str, quality: &str, codec: &str) {
        use tokio::io::AsyncReadExt;
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap();
        let source = root
            .join(".runtime/tang-retained-20261117-8b1d94a3")
            .join(name);
        let size = std::fs::metadata(&source).unwrap().len();
        let dir = root
            .join(".runtime/task21")
            .join(format!("original-roundtrip-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&dir).unwrap();
        let target = dir.join(name);
        let part = dir.join("owned.part");
        let file = tokio::fs::File::open(&source).await.unwrap();
        let chunks = futures_util::stream::try_unfold(file, |mut file| async move {
            let mut chunk = vec![0; 65536];
            let count = file.read(&mut chunk).await?;
            if count == 0 {
                Ok::<_, std::io::Error>(None)
            } else {
                chunk.truncate(count);
                Ok(Some((chunk, file)))
            }
        });
        let response = reqwest::Response::from(
            axum::http::Response::builder()
                .status(200)
                .header("content-length", size)
                .body(reqwest::Body::wrap_stream(chunks))
                .unwrap(),
        );
        let r = Recording {
            cover: None,
            quality: quality.into(),
            identity: json!({"providerId":"qq","platformId":"0027oMO61wWi55"}),
            title: "发如雪".into(),
            artist: "周杰伦".into(),
            duration: 299.0,
        };
        let task = original_save(&Downloads::default(), &r, &target, &part, response).await;
        assert_eq!(task["status"], "completed");
        assert_eq!(task["actualMedia"]["codec"], codec);
        assert_eq!(std::fs::metadata(&target).unwrap().len(), size);
        // 比较全部字节，包含原文件的尾随数据，不裁剪或修复。
        let mut left = std::fs::File::open(&source).unwrap();
        let mut right = std::fs::File::open(&target).unwrap();
        let mut remaining = size;
        let mut a = [0; 65536];
        let mut b = [0; 65536];
        while remaining > 0 {
            let n = remaining.min(a.len() as u64) as usize;
            std::io::Read::read_exact(&mut left, &mut a[..n]).unwrap();
            std::io::Read::read_exact(&mut right, &mut b[..n]).unwrap();
            assert_eq!(&a[..n], &b[..n]);
            remaining -= n as u64;
        }
        println!(
            "original_retained_file_roundtrip: {}",
            json!({"status":task["status"],"sizeBytes":size,"allBytesEqual":true,"output":target})
        );
    }
    #[test]
    fn full_ranges_are_not_partial_files() {
        assert_eq!(
            full_response_size(200, Some(100), Some("bytes 0-99/100")).unwrap(),
            Some(100)
        );
        assert_eq!(
            full_response_size(206, None, Some("bytes 0-99/100")).unwrap(),
            Some(100)
        );
        for (length, range) in [
            (Some(99), "bytes 0-99/100"),
            (Some(99), "bytes 1-99/100"),
            (Some(50), "bytes 0-49/100"),
            (None, "bytes 0-99/*"),
        ] {
            assert!(full_response_size(200, length, Some(range)).is_err());
        }
        assert!(full_response_size(206, Some(100), None).is_err());
    }
    #[test]
    fn naming_rules_settings_and_windows_cleanup() {
        let root = tempfile::tempdir().unwrap();
        let dir = root.path().to_owned();
        let path = dir.join("music-core.sqlite3");
        let manager = Downloads::with_history(path.clone(), dir.clone()).unwrap();
        assert_eq!(
            manager.settings(&Value::Null).unwrap()["naming"],
            "artist_title"
        );
        let mut recording = Recording {
            cover: None,
            quality: "standard".into(),
            identity: json!({"providerId":"kuwo","platformId":"151826227"}),
            title: "贝多芬：致爱丽丝".into(),
            artist: "Various Artists".into(),
            duration: 235.0,
        };
        for (rule, expected) in [
            ("title", "贝多芬：致爱丽丝.mp3"),
            ("artist_title", "Various Artists - 贝多芬：致爱丽丝.mp3"),
            ("title_artist", "贝多芬：致爱丽丝 - Various Artists.mp3"),
        ] {
            manager.settings(&json!({"naming":rule})).unwrap();
            assert_eq!(
                suggested_name(&recording, manager.naming().unwrap()),
                expected
            );
            assert_eq!(
                Downloads::with_history(path.clone(), dir.clone())
                    .unwrap()
                    .settings(&Value::Null)
                    .unwrap()["naming"],
                rule
            );
        }
        assert!(manager.settings(&json!({"naming":"arbitrary"})).is_err());
        recording.title = " CON. ".into();
        assert_eq!(suggested_name(&recording, Naming::Title), "_CON.mp3");
        recording.title = "a/b:*?\"<>|\n".into();
        assert_eq!(suggested_name(&recording, Naming::Title), "a_b_______.mp3");
        recording.title = "😀".repeat(100);
        assert_eq!(
            suggested_name(&recording, Naming::Title)
                .encode_utf16()
                .count(),
            124
        );
    }
    fn folder() -> PathBuf {
        let path = std::env::current_dir()
            .unwrap()
            .join(".runtime")
            .join(format!("download-test-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&path).unwrap();
        path
    }
    fn fixture(frames: usize) -> Vec<u8> {
        let mut raw = Vec::new();
        for _ in 0..frames {
            let mut frame = vec![0u8; 417];
            frame[..4].copy_from_slice(&[255, 251, 144, 0]);
            raw.extend(frame);
        }
        raw
    }
    #[test]
    fn complete_frames_quality_duration_and_no_overwrite() {
        let dir = folder();
        let part = dir.join("owned.part");
        let target = dir.join("audio.mp3");
        let raw = fixture(20);
        std::fs::write(&part, &raw).unwrap();
        let duration = 20.0 * 1152.0 / 44100.0;
        assert_eq!(inspect(&part, duration).unwrap()["bitrateBps"], 128000);
        assert!(inspect(&part, 30.0).is_err());
        let mut wrong_quality = raw.clone();
        wrong_quality[2] = 0xB0; // 实际 192k 不冒充用户选择的标准 128k。
        std::fs::write(&part, wrong_quality).unwrap();
        assert!(inspect(&part, duration).is_err());
        std::fs::write(&part, &raw[..raw.len() - 1]).unwrap();
        assert!(inspect(&part, duration).is_err());
        std::fs::write(&part, &raw).unwrap();
        std::fs::write(&target, b"existing").unwrap();
        assert_eq!(publish(&part, &target).unwrap_err(), "file_exists");
        assert_eq!(std::fs::read(&target).unwrap(), b"existing");
        std::fs::remove_file(&target).unwrap();
        publish(&part, &target).unwrap();
        assert_eq!(std::fs::read(&target).unwrap(), raw);
        std::fs::remove_file(part).unwrap();
        std::fs::remove_file(target).unwrap();
        std::fs::remove_dir(dir).unwrap();
    }
    #[test]
    fn permission_and_input_never_infer_from_playback() {
        assert_eq!(eligibility(&json!({})), None);
        assert_eq!(
            eligibility(&json!({"payInfo":{"cannotDownload":"1"}})),
            Some(false)
        );
        let unknown = Downloads::default();
        let mut page = json!({"items":[{"identity":{"providerId":"kuwo","platformId":"123"},"downloadAllowed":null,"title":"缺字段","artists":[]}]});
        unknown.register(&mut page);
        assert!(page["items"][0]["downloadAllowed"].is_null());
        assert!(unknown
            .recording(
                &json!({"identity":{"providerId":"kuwo","platformId":"123"},"quality":"standard"})
            )
            .is_ok());
        let free = json!({"payInfo":{"cannotDownload":"0","listen_fragment":"0","local_encrypt":"0","paytype":0,"feeType":{"album":"0","bookvip":"0","song":"0","vip":"0"}}});
        assert_eq!(eligibility(&free), Some(true));
        assert_eq!(eligibility(&json!({})), None);
        let mut paid = free.clone();
        paid["payInfo"]["feeType"]["vip"] = json!("1");
        assert_eq!(eligibility(&paid), Some(true));
        let manager = Downloads::default();
        assert!(manager
            .recording(
                &json!({"identity":{"providerId":"qq","platformId":"123"},"quality":"standard"})
            )
            .is_err());
        assert!(manager
            .recording(&json!({"path":"arbitrary","quality":"standard"}))
            .is_err());
        assert!(manager.recording(&json!({"quality":"lossless"})).is_err());
    }
    #[tokio::test]
    async fn interrupted_retry_and_cancel_clean_only_owned_parts() {
        use tokio::io::AsyncReadExt;
        let dir = folder();
        let target = dir.join("sample.mp3");
        let part = dir.join("owned.part");
        let untouched = dir.join("other.part");
        std::fs::write(&untouched, b"other task").unwrap();
        let manager = Downloads::default();
        let r = Recording {
            cover: None,
            quality: "standard".into(),
            identity: json!({"providerId":"kuwo","platformId":"fixture"}),
            title: "夹具".into(),
            artist: "测试".into(),
            duration: 20.0 * 1152.0 / 44100.0,
        };
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            // 首次连接中断，重试完整响应，第三次停在半途供取消验证。
            for attempt in 0..3 {
                let (mut socket, _) = listener.accept().await.unwrap();
                let mut request = [0; 4096];
                socket.read(&mut request).await.unwrap();
                let raw = fixture(20);
                socket
                    .write_all(
                        format!(
                            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                            raw.len()
                        )
                        .as_bytes(),
                    )
                    .await
                    .unwrap();
                socket
                    .write_all(if attempt == 1 { &raw } else { &raw[..417] })
                    .await
                    .unwrap();
                if attempt == 2 {
                    tokio::time::sleep(Duration::from_secs(10)).await;
                }
            }
        });
        let client = reqwest::Client::new();
        for attempt in 0..3 {
            let cancel = CancellationToken::new();
            manager.jobs.lock().unwrap().insert(
                "fixture".into(),
                Job {
                    public: json!({"status":"resolving"}),
                    recording: r.clone(),
                    target: target.clone(),
                    part: part.clone(),
                    cancel: cancel.clone(),
                    owns_part: false,
                    owns_output: false,
                },
            );
            if attempt == 2 {
                let token = cancel.clone();
                tokio::spawn(async move {
                    tokio::time::sleep(Duration::from_millis(100)).await;
                    token.cancel();
                });
            }
            let response = client
                .get(format!("http://{address}/same-recording-standard"))
                .send()
                .await
                .unwrap();
            manager
                .finish(
                    "fixture",
                    &target,
                    manager.save_response("fixture", &r, &target, &part, response),
                )
                .await;
            assert!(!part.exists());
            assert_eq!(std::fs::read(&untouched).unwrap(), b"other task");
            let status = manager.list()[0]["status"].clone();
            if attempt == 1 {
                assert_eq!(status, "completed");
                assert_eq!(std::fs::read(&target).unwrap(), fixture(20));
                std::fs::remove_file(&target).unwrap();
            } else {
                assert_eq!(status, if attempt == 0 { "failed" } else { "cancelled" });
                assert!(!target.exists());
            }
        }
        server.abort();
        std::fs::remove_file(untouched).unwrap();
        std::fs::remove_dir(dir).unwrap();
    }
    #[tokio::test]
    #[ignore = "真实原生下载；输出仅记录身份、格式和大小"]
    async fn live_standard_download() {
        let client = reqwest::Client::builder()
            .user_agent("Mozilla/5.0")
            .redirect(reqwest::redirect::Policy::none())
            .read_timeout(Duration::from_secs(30))
            .build()
            .unwrap();
        let r = Recording {
            cover: None,
            quality: "standard".into(),
            identity: json!({"providerId":"kuwo","platformId":"151826227"}),
            title: "贝多芬：致爱丽丝".into(),
            artist: "Various Artists".into(),
            duration: 235.0,
        };
        let rep = prefix(&client, &r).await.unwrap();
        assert_eq!(rep["bitrateBps"], 128000);
        let dir = folder();
        let target = dir.join("sample.mp3");
        let part = dir.join("sample.part");
        let manager = Downloads::default();
        let result = manager
            .transfer(
                "fixture",
                &client,
                &r,
                &target,
                &part,
                &CancellationToken::new(),
            )
            .await;
        println!("kuwo/151826227 standard result={result:?}");
        let _ = std::fs::remove_file(&part);
        let _ = std::fs::remove_file(&target);
        std::fs::remove_dir(dir).unwrap();
        assert!(result.is_ok());
    }
}
