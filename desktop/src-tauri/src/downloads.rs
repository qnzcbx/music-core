use crate::provider::common;
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

fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_millis() as u64
}
#[derive(Clone)]
struct Recording {
    quality: String,
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
}
// 沿用网页版设置的枚举及默认值；只保存命名偏好，不保存任务或目录。
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
    naming: Arc<Mutex<Naming>>,
    settings_path: Option<PathBuf>,
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
    let bytes = common::bytes(
        client
            .get("https://mobi.kuwo.cn/mobi.s")
            .header("User-Agent", "okhttp/3.10.0")
            .query(&[
                ("user", "0"),
                ("corp", "kuwo"),
                ("source", "kwplayer_ar_5.1.0.0_B_jiakong_vh.apk"),
                ("p2p", "1"),
                ("type", "convert_url2"),
                ("sig", "0"),
                ("format", "mp3"),
                ("br", "128k"),
                ("rid", id),
            ]),
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
    let mut response = client
        .get(url)
        .header("User-Agent", "okhttp/3.10.0")
        .header("Range", "bytes=0-65535")
        .header("Accept-Encoding", "identity")
        .send()
        .await
        .map_err(|_| "upstream_failure")?;
    if !matches!(response.status().as_u16(), 200 | 206) {
        return Err("access_denied".into());
    }
    if response
        .headers()
        .get("content-encoding")
        .is_some_and(|v| v != "identity")
        || (response.status() == 206
            && !response
                .headers()
                .get("content-range")
                .and_then(|v| v.to_str().ok())
                .is_some_and(|v| v.starts_with("bytes 0-")))
    {
        return Err("upstream_invalid_response".into());
    }
    let mut raw = Vec::new();
    while raw.len() < 65536 {
        let Some(chunk) = response.chunk().await.map_err(|_| "upstream_failure")? else {
            break;
        };
        raw.extend_from_slice(&chunk[..chunk.len().min(65536 - raw.len())]);
    }
    let mut offset = 0;
    if raw.starts_with(b"ID3") && raw.len() >= 10 {
        if raw[6..10].iter().any(|b| b & 128 != 0) {
            return Err("media_unavailable".into());
        }
        offset = 10
            + raw[6..10]
                .iter()
                .fold(0usize, |n, b| (n << 7) | *b as usize);
    }
    let mut verified = None;
    for pos in offset..raw.len().saturating_sub(4).min(offset + 4096) {
        if let Some((_, rate, length)) = frame(raw[pos..pos + 4].try_into().unwrap()) {
            if pos + length + 4 <= raw.len()
                && frame(raw[pos + length..pos + length + 4].try_into().unwrap()).is_some()
            {
                verified = Some(rate);
                break;
            }
        }
    }
    let rate = verified.ok_or("media_unavailable")?;
    Ok(
        json!({"codec":"mp3","container":"mpeg-audio","bitrateBps":128000,"sampleRateHz":rate,"lossless":false,"providerQualityId":"standard"}),
    )
}
// 部分 CDN 在完整 200 响应中仍带 Content-Range；只接受明确覆盖全文件的区间。
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
    pub fn new(settings_path: PathBuf) -> Self {
        let naming = std::fs::read(&settings_path)
            .ok()
            .and_then(|bytes| serde_json::from_slice::<Naming>(&bytes).ok())
            .unwrap_or_default();
        Self {
            naming: Arc::new(Mutex::new(naming)),
            settings_path: Some(settings_path),
            ..Self::default()
        }
    }
    pub fn settings(&self, body: &Value) -> Result<Value, String> {
        let mut naming = self.naming.lock().unwrap();
        if !body.is_null() {
            let next: Naming =
                serde_json::from_value(body["naming"].clone()).map_err(|_| "invalid_input")?;
            if let Some(path) = &self.settings_path {
                std::fs::create_dir_all(path.parent().ok_or("file_io_error")?)
                    .map_err(|_| "file_io_error")?;
                std::fs::write(path, serde_json::to_vec(&next).unwrap())
                    .map_err(|_| "file_io_error")?;
            }
            *naming = next;
        }
        Ok(
            json!({"mode":"desktop", "naming":*naming, "canManage":false, "deploymentLocked":false, "error":null}),
        )
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
            || body["outputMode"].as_str().is_some_and(|s| s != "original")
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
        if recording.identity["providerId"] == "kuwo" && recording.quality != "standard" {
            return Err("capability_unsupported".into());
        }
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
                json!({"quality":body["quality"],"availability":"available","representation":rep,"errorCode":null,"conversion":{"available":false,"reason":"桌面版仅保存原格式"}})
            }
            Err(error) => {
                json!({"quality":body["quality"],"availability":"unavailable","representation":null,"errorCode":error})
            }
        }
    }
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
        let mut recording = self.recording(body)?;
        let rep = tokio::time::timeout(Duration::from_secs(50), prefix(client, &recording))
            .await
            .map_err(|_| "upstream_timeout")??;
        if let Some(duration) = rep["expectedDurationSeconds"].as_f64().filter(|n| *n > 0.0) {
            recording.duration = duration;
        }
        let extension = rep["extension"].as_str().unwrap_or("mp3");
        let name = suggested_name(&recording, *self.naming.lock().unwrap())
            .trim_end_matches(".mp3")
            .to_owned()
            + "."
            + extension;
        let Some(file) = rfd::AsyncFileDialog::new()
            .set_title("保存原格式音频")
            .add_filter("原格式音频", &[extension])
            .set_file_name(name)
            .save_file()
            .await
        else {
            return Ok(Value::Null);
        };
        self.start(recording, file.path().to_owned(), client.clone())
    }
    fn start(
        &self,
        r: Recording,
        target: PathBuf,
        client: reqwest::Client,
    ) -> Result<Value, String> {
        if target
            .extension()
            .and_then(|s| s.to_str())
            .is_none_or(|s| !["mp3", "m4a", "flac"].contains(&s.to_ascii_lowercase().as_str()))
        {
            return Err("file_io_error".into());
        }
        if target.exists() {
            return Err("file_exists".into());
        }
        let id = uuid::Uuid::new_v4().simple().to_string();
        let part = target.with_file_name(format!(".music-core-{id}.part"));
        let cancel = CancellationToken::new();
        let public = json!({"id":id,"identity":r.identity,"title":r.title,"artist":r.artist,"quality":r.quality,"outputMode":"original","deliveryMode":"desktop","status":"resolving","receivedBytes":0,"createdAt":now(),"updatedAt":now()});
        {
            let mut jobs = self.jobs.lock().unwrap();
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
                },
            );
        }
        let manager = self.clone();
        tokio::spawn(async move {
            manager.run(&id, &client, cancel).await;
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
    async fn run(&self, id: &str, client: &reqwest::Client, cancel: CancellationToken) {
        let (r, target, part) = {
            let jobs = self.jobs.lock().unwrap();
            let j = &jobs[id];
            (j.recording.clone(), j.target.clone(), j.part.clone())
        };
        self.finish(
            id,
            &target,
            &part,
            cancel,
            self.transfer(id, client, &r, &target, &part),
        )
        .await;
    }
    async fn finish(
        &self,
        id: &str,
        target: &Path,
        part: &Path,
        cancel: CancellationToken,
        transfer: impl std::future::Future<Output = Result<Value, String>>,
    ) {
        let result = tokio::select! {
            biased;
            _ = cancel.cancelled() => Err("cancelled".to_string()),
            result = transfer => result,
        };
        let owned = self
            .jobs
            .lock()
            .unwrap()
            .get(id)
            .is_some_and(|j| j.owns_part);
        let cleanup = if owned {
            tokio::fs::remove_file(&part).await
        } else {
            Ok(())
        };
        if cleanup
            .as_ref()
            .is_err_and(|e| e.kind() != std::io::ErrorKind::NotFound)
        {
            self.update(
                id,
                json!({"status":"failed","errorCode":"temporary_cleanup_failed"}),
            );
            return;
        }
        match result {
            Ok(rep) => self.update(
                id,
                json!({
                    "status": "completed", "phase": "completed",
                    "filename": target.file_name().and_then(|s| s.to_str()),
                    "format": rep["extension"].as_str().unwrap_or("mp3"), "route":rep["route"], "actualMedia": rep,
                    "finalSizeBytes": rep["sizeBytes"], "progress": 1,
                }),
            ),
            Err(error) => self.update(
                id,
                json!({
                    "status": if error == "cancelled" { "cancelled" } else { "failed" },
                    "errorCode": if error == "cancelled" { Value::Null } else { json!(error) },
                }),
            ),
        }
    }
    async fn transfer(
        &self,
        id: &str,
        client: &reqwest::Client,
        r: &Recording,
        target: &Path,
        part: &Path,
    ) -> Result<Value, String> {
        let mut checked = r.clone();
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
        if total.is_some_and(|n| n == 0 || n > 100 * 1024 * 1024) {
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
        while let Some(chunk) = response.chunk().await.map_err(|_| "upstream_failure")? {
            received += chunk.len() as u64;
            if received > 100 * 1024 * 1024 {
                return Err("media_capacity".into());
            }
            file.write_all(&chunk).await.map_err(|_| "file_io_error")?;
            self.update(
                id,
                json!({"receivedBytes":received,"progress":total.map(|n|received as f64/n as f64)}),
            );
        }
        file.sync_all().await.map_err(|_| "file_io_error")?;
        drop(file);
        if received == 0 || total.is_some_and(|n| n != received) {
            return Err("source_verification_failed".into());
        }
        self.update(id, json!({"phase":"verifying"}));
        let rep = crate::download_media::inspect_original(part, &r.quality)?;
        // 酷我标准档仍沿用已开放的 MP3 128k 品质，不再额外扫描整首。
        if r.identity["providerId"] == "kuwo"
            && (rep["codec"] != "mp3"
                || !rep["bitrateBps"]
                    .as_u64()
                    .is_some_and(|n| n.abs_diff(128000) <= 1000))
        {
            return Err("media_unavailable".into());
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
        publish(part, target)?;
        Ok(rep)
    }
    pub async fn operate(
        &self,
        id: &str,
        operation: &str,
        client: &reqwest::Client,
    ) -> Result<Value, String> {
        let (r, target, status, cancel) = {
            let jobs = self.jobs.lock().unwrap();
            let j = jobs.get(id).ok_or("track_not_found")?;
            (
                j.recording.clone(),
                j.target.clone(),
                j.public["status"].as_str().unwrap_or("").to_string(),
                j.cancel.clone(),
            )
        };
        match operation {
            "cancel" => {
                if matches!(status.as_str(), "resolving" | "downloading") {
                    cancel.cancel();
                }
                Ok(self.jobs.lock().unwrap()[id].public.clone())
            }
            "retry" if matches!(status.as_str(), "failed" | "cancelled") => {
                self.create(
                    client,
                    &json!({"identity":r.identity,"quality":r.quality,"outputMode":"original"}),
                )
                .await
            }
            "reveal" if status == "completed" => {
                std::process::Command::new("explorer.exe")
                    // 参数和路径分别传递，让 Windows 正确引用含空格的文件名。
                    .arg("/select,")
                    .arg(&target)
                    .spawn()
                    .map_err(|_| "file_io_error")?;
                Ok(Value::Null)
            }
            _ => Err("capability_unsupported".into()),
        }
    }
    pub fn active(&self) -> bool {
        self.jobs.lock().unwrap().values().any(|j| {
            matches!(
                j.public["status"].as_str(),
                Some("resolving" | "downloading")
            )
        })
    }
    pub async fn shutdown(&self) {
        for job in self.jobs.lock().unwrap().values() {
            job.cancel.cancel();
        }
        for _ in 0..200 {
            if !self.active() {
                return;
            }
            tokio::time::sleep(Duration::from_millis(25)).await;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
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
        let cancel = CancellationToken::new();
        manager.jobs.lock().unwrap().insert(
            "original-fixture".into(),
            Job {
                public: json!({"status":"resolving"}),
                recording: r.clone(),
                target: target.into(),
                part: part.into(),
                cancel: cancel.clone(),
                owns_part: false,
            },
        );
        manager
            .finish(
                "original-fixture",
                target,
                part,
                cancel,
                manager.save_response("original-fixture", r, target, part, response),
            )
            .await;
        assert!(!part.exists(), "本任务临时文件应已清理");
        manager.list()[0].clone()
    }
    #[tokio::test]
    async fn original_response_basics() {
        let dir = folder();
        let target = dir.join("saved.mp3");
        let part = dir.join("owned.part");
        let manager = Downloads::default();
        let mut r = Recording {
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
        let dir = folder();
        let path = dir.join("naming.json");
        let manager = Downloads::new(path.clone());
        assert_eq!(
            manager.settings(&Value::Null).unwrap()["naming"],
            "artist_title"
        );
        let mut recording = Recording {
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
                suggested_name(&recording, *manager.naming.lock().unwrap()),
                expected
            );
            assert_eq!(
                Downloads::new(path.clone()).settings(&Value::Null).unwrap()["naming"],
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
        std::fs::remove_file(path).unwrap();
        std::fs::remove_dir(dir).unwrap();
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
                    &part,
                    cancel,
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
            .transfer("fixture", &client, &r, &target, &part)
            .await;
        println!("kuwo/151826227 standard result={result:?}");
        let _ = std::fs::remove_file(&part);
        let _ = std::fs::remove_file(&target);
        std::fs::remove_dir(dir).unwrap();
        assert!(result.is_ok());
    }
}
