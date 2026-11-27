use crate::{
    covers, delete_plan,
    downloads::{DirectoryAction, Naming},
    fallback, local_library, lyrics, media_cache, provider, sessions, Desktop,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

#[derive(Deserialize)]
#[serde(
    tag = "op",
    content = "payload",
    rename_all = "camelCase",
    deny_unknown_fields
)]
enum Operation {
    ProvidersList,
    SearchPage(Search),
    LyricsGet(Identity),
    PaletteRelay(Palette),
    CachedCover(CachedCover),
    QueueCovers(QueueCovers),
    CacheSettings,
    CacheOpen,
    CacheClear(CacheClear),
    DownloadOptions(DownloadInput),
    DownloadCreate(DownloadInput),
    DownloadsList,
    DownloadCancel(Id),
    DownloadRetry(Id),
    DownloadDismiss(Id),
    DownloadSettings,
    DownloadNaming(DownloadNaming),
    DownloadDirectory(DownloadDirectory),
    LibraryList,
    LibraryImport,
    LibraryChooseDirectory,
    LibraryRefreshDirectory(Id),
    LibraryRemoveDirectory(Id),
    LibraryOpen(Id),
    LibraryReveal(Id),
    LibraryRemove(Id),
    RecyclePrepare(RecycleTarget),
    RecycleCancel(Token),
    RecycleExecute(Token),
    PlaybackOpen(PlaybackOpen),
    PlaybackRenew(Lease),
    PlaybackClose(Lease),
}

#[derive(Deserialize, Serialize, Clone, Copy)]
#[serde(rename_all = "lowercase")]
enum Source {
    Kuwo,
    Qq,
    Netease,
    Migu,
}

impl Source {
    fn id(self) -> &'static str {
        match self {
            Self::Kuwo => "kuwo",
            Self::Qq => "qq",
            Self::Netease => "netease",
            Self::Migu => "migu",
        }
    }
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Identity {
    provider_id: Source,
    platform_id: String,
}

impl Identity {
    fn validate(&self) -> Result<(), String> {
        if !provider::common::valid_id(self.provider_id.id(), &self.platform_id) {
            return Err("invalid_input".into());
        }
        Ok(())
    }

    fn checked(self) -> Result<Value, String> {
        self.validate()?;
        serde_json::to_value(self).map_err(|_| "invalid_input".into())
    }
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Search {
    provider_id: Source,
    query: String,
    limit: u16,
    cursor: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Palette {
    url: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CachedCover {
    identity: Identity,
    cover: Option<String>,
}

#[derive(Deserialize)]
#[serde(untagged, deny_unknown_fields)]
enum QueueCover {
    Local {
        #[serde(rename = "fileId")]
        file_id: String,
    },
    Online {
        track: Identity,
    },
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct QueueCovers {
    entries: Vec<QueueCover>,
}

#[derive(Deserialize)]
#[serde(rename_all = "lowercase")]
enum Scope {
    Cover,
    Lyrics,
    All,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CacheClear {
    scope: Scope,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Id {
    id: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Token {
    token: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Lease {
    playback_id: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct RecycleTarget {
    id: String,
    path_hint: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PlaybackOpen {
    identity: Identity,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DownloadNaming {
    naming: Naming,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DownloadDirectory {
    action: DirectoryAction,
}

#[derive(Deserialize, Serialize, Default)]
#[serde(rename_all = "lowercase")]
enum Quality {
    #[default]
    Auto,
    Standard,
    High,
    Lossless,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum OutputMode {
    Original,
    #[serde(rename = "mp3_320")]
    Mp3_320,
    #[serde(rename = "mp3_192")]
    Mp3_192,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
enum Codec {
    Flac,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct DownloadInput {
    identity: Identity,
    #[serde(default)]
    quality: Quality,
    output_mode: Option<OutputMode>,
    expected_source_codec: Option<Codec>,
    #[serde(default)]
    save_as: bool,
    title: Option<String>,
    artist: Option<String>,
    album: Option<String>,
    cover: Option<String>,
}

impl DownloadInput {
    fn checked(self) -> Result<Value, String> {
        self.identity.validate()?;
        serde_json::to_value(self).map_err(|_| "invalid_input".into())
    }
}

#[derive(Debug, Serialize)]
pub(crate) struct Fault {
    code: &'static str,
    message: &'static str,
    status: u16,
    retryable: bool,
}

impl Fault {
    fn from_code(code: &str) -> Self {
        let (code, status, retryable, message) = match code {
            "invalid_input" => ("invalid_input", 422, false, "输入参数无效"),
            "playback_expired" => ("playback_expired", 410, false, "播放会话已过期，请重新播放"),
            "track_not_found" => ("track_not_found", 404, false, "该记录不存在"),
            "access_denied" => ("access_denied", 403, false, "来源未授权此操作"),
            "capability_unsupported" => (
                "capability_unsupported",
                415,
                false,
                "当前来源或位置暂不支持此操作",
            ),
            "untrusted_media" => (
                "untrusted_media",
                502,
                false,
                "来源返回了不受信任的媒体地址",
            ),
            "anonymous_media_unavailable" | "media_unavailable" => {
                ("media_unavailable", 409, true, "当前媒体或所选品质不可用")
            }
            "auth_required" => ("auth_required", 403, false, "此曲目需要来源授权"),
            "preview_only" => ("preview_only", 403, false, "此曲目只提供试听"),
            "encrypted_media" => ("encrypted_media", 415, false, "此曲目使用不支持的加密媒体"),
            "upstream_failure" => ("upstream_failure", 502, true, "来源暂时无法连接，请重试"),
            "source_verification_failed" => (
                "source_verification_failed",
                502,
                false,
                "无法确认来源提供的曲目身份或格式",
            ),
            "media_capacity" => ("media_capacity", 503, true, "媒体容量已满，请稍后重试"),
            "upstream_timeout" => ("upstream_timeout", 504, true, "来源请求超时，请重试"),
            "upstream_invalid_response" => {
                ("upstream_invalid_response", 502, true, "来源返回的响应异常")
            }
            "upstream_rate_limited" => (
                "upstream_rate_limited",
                429,
                true,
                "来源请求过于频繁，请稍后再试",
            ),
            "provider_context_rejected" => (
                "provider_context_rejected",
                502,
                false,
                "来源未接受当前请求上下文",
            ),
            "download_shutting_down" => (
                "download_shutting_down",
                409,
                false,
                "拾音正在退出，无法开始新下载",
            ),
            "download_history_unavailable" => (
                "download_history_unavailable",
                503,
                true,
                "无法读取或保存下载设置与记录，请检查应用配置目录",
            ),
            "download_history_invalid" => (
                "download_history_invalid",
                503,
                false,
                "下载记录文件无法读取，原文件未改动",
            ),
            "local_directory_unavailable" => (
                "local_directory_unavailable",
                503,
                true,
                "目录暂不可用，已有记录已保留",
            ),
            "local_library_unavailable" => (
                "local_library_unavailable",
                503,
                true,
                "无法读取或保存本地歌曲记录",
            ),
            "local_recycle_unavailable" => (
                "local_recycle_unavailable",
                415,
                false,
                "此位置无法使用系统回收站。可取消勾选，仅从曲库移除。",
            ),
            "local_recycle_identity_unavailable" => (
                "local_recycle_identity_unavailable",
                409,
                false,
                "Windows 无法读取此文件的身份，无法安全回收。",
            ),
            "local_recycle_unsafe_path" => (
                "local_recycle_unsafe_path",
                403,
                false,
                "此文件位置无法安全回收。",
            ),
            "local_recycle_changed" => (
                "local_recycle_changed",
                409,
                false,
                "文件或曲库记录已变化，请刷新列表后重新确认。",
            ),
            "local_recycle_plan_invalid" => (
                "local_recycle_plan_invalid",
                410,
                false,
                "删除确认已过期或失效，请重新打开删除窗口。",
            ),
            "local_recycle_cancelled" => (
                "local_recycle_cancelled",
                409,
                false,
                "系统已取消回收，曲库记录已保留。",
            ),
            "local_recycle_failed" => (
                "local_recycle_failed",
                503,
                false,
                "系统回收失败，请检查文件占用及回收站。",
            ),
            "local_recycle_uncertain" => (
                "local_recycle_uncertain",
                503,
                false,
                "系统没有确认回收结果。请检查原文件和回收站，曲库记录已保留。",
            ),
            "local_unsupported" => (
                "local_unsupported",
                415,
                false,
                "请选择可播放的 MP3 或 FLAC 文件",
            ),
            "saved_file_missing" => (
                "saved_file_missing",
                404,
                false,
                "文件已移动或删除，记录中的原位置已不存在",
            ),
            "file_exists" => (
                "file_exists",
                409,
                false,
                "目标文件已存在，请选择其他名称或位置",
            ),
            "file_io_error" => ("file_io_error", 503, true, "无法访问文件，请检查所选位置"),
            _ => ("internal_error", 500, false, "桌面操作失败，请重试"),
        };
        Self {
            code,
            message,
            status,
            retryable,
        }
    }
}

fn selection(value: Value) -> Value {
    if value.is_null() {
        json!({ "status": "cancelled" })
    } else {
        json!({ "status": "selected", "value": value })
    }
}

fn renew(sessions: &sessions::Sessions, id: &str) -> Result<Value, String> {
    if !sessions.renew(id) {
        return Err("playback_expired".into());
    }
    Ok(Value::Null)
}

async fn download_settings(state: &Desktop, naming: Option<Naming>) -> Result<Value, String> {
    let downloads = state.downloads.clone();
    tauri::async_runtime::spawn_blocking(move || downloads.settings(naming))
        .await
        .map_err(|_| "download_history_unavailable")?
}

#[tauri::command]
pub(crate) async fn core_request(
    window: tauri::WebviewWindow,
    request: Value,
    state: tauri::State<'_, Desktop>,
) -> Result<Value, Fault> {
    if window.label() != "main" {
        return Err(Fault::from_code("access_denied"));
    }
    let request = serde_json::from_value(request).map_err(|_| Fault::from_code("invalid_input"))?;
    dispatch(&state, request)
        .await
        .map_err(|code| Fault::from_code(&code))
}

async fn dispatch(state: &Desktop, request: Operation) -> Result<Value, String> {
    use Operation::*;
    match request {
        ProvidersList => Ok(provider::catalog()),
        SearchPage(input) => {
            let body = serde_json::to_value(input).map_err(|_| "invalid_input")?;
            let mut page = provider::search(&state.client, &body).await?;
            covers::Covers::map_page(&mut page);
            state.downloads.register(&mut page);
            Ok(page)
        }
        PaletteRelay(input) => {
            let url = &input.url;
            let relay = state
                .covers
                .register_palette(url, state.port)
                .ok_or("untrusted_media")?;
            Ok(json!({"url": relay}))
        }
        LyricsGet(identity) => {
            let body = identity.checked()?;
            match &state.covers.1 {
                Some(cache) => cache.lyrics(&state.client, &body).await,
                None => lyrics::get(&state.client, &body).await,
            }
        }
        CachedCover(input) => {
            let identity = input.identity.checked()?;
            let cover = match &state.covers.1 {
                Some(cache) => {
                    cache
                        .cover(&state.covers, &identity, input.cover.as_deref(), state.port)
                        .await
                }
                None => None,
            };
            Ok(json!({"cover":cover}))
        }
        QueueCovers(input) => {
            if input.entries.len() > 200 {
                return Err("invalid_input".into());
            }
            let entries = input
                .entries
                .into_iter()
                .map(|entry| match entry {
                    QueueCover::Local { file_id } => Ok(json!({ "fileId": file_id })),
                    QueueCover::Online { track } => Ok(json!({ "track": track.checked()? })),
                })
                .collect::<Result<Vec<_>, String>>()?;
            let (downloads, cache, port) =
                (state.downloads.clone(), state.covers.1.clone(), state.port);
            tauri::async_runtime::spawn_blocking(move || {
                let mut local = std::collections::HashMap::new();
                if entries.iter().any(|entry| entry["fileId"].is_string()) {
                    let (records, excluded) = downloads.library_snapshot()?;
                    let mut keys = std::collections::HashMap::new();
                    for record in records {
                        let id = keys
                            .entry(record.path.clone())
                            .or_insert_with(|| local_library::path_key(&record.path));
                        if !excluded.contains(id) {
                            local.entry(id.clone()).or_insert(record.identity);
                        }
                    }
                }
                let tracks = entries
                    .iter()
                    .map(|entry| match entry["fileId"].as_str() {
                        Some(id) => local.get(id),
                        None => entry.get("track"),
                    })
                    .collect::<Vec<_>>();
                let urls = cache.map_or_else(
                    || vec![None; entries.len()],
                    |cache| cache.indexed_covers(&tracks, port),
                );
                Ok(json!(urls))
            })
            .await
            .map_err(|_| "local_library_unavailable")?
        }
        CacheSettings | CacheOpen => {
            let cache = state.covers.1.as_ref().ok_or("capability_unsupported")?;
            if matches!(request, CacheOpen) {
                std::process::Command::new("explorer.exe")
                    .arg(cache.directory())
                    .spawn()
                    .map_err(|_| "file_io_error")?;
            }
            Ok(json!({"directory":cache.directory()}))
        }
        CacheClear(input) => {
            let scope = match input.scope {
                Scope::Cover => media_cache::ClearScope::Cover,
                Scope::Lyrics => media_cache::ClearScope::Lyrics,
                Scope::All => media_cache::ClearScope::All,
            };
            let downloads = state.downloads.clone();
            tauri::async_runtime::spawn_blocking(move || downloads.clear_media_cache(scope))
                .await
                .map_err(|_| "file_io_error")??;
            Ok(Value::Null)
        }
        DownloadOptions(input) => Ok(state
            .downloads
            .options(&state.client, &input.checked()?)
            .await),
        DownloadCreate(input) => state
            .downloads
            .create(&state.client, &input.checked()?)
            .await
            .map(selection),
        DownloadsList => {
            let downloads = state.downloads.clone();
            tauri::async_runtime::spawn_blocking(move || downloads.poll())
                .await
                .map_err(|_| "download_history_unavailable")?
        }
        DownloadSettings => download_settings(state, None).await,
        DownloadNaming(input) => download_settings(state, Some(input.naming)).await,
        DownloadDirectory(input) => state.downloads.directory(input.action).await.map(selection),
        request @ (LibraryList
        | LibraryImport
        | LibraryChooseDirectory
        | LibraryRefreshDirectory(_)
        | LibraryRemoveDirectory(_)) => {
            let change = match request {
                LibraryImport => Some(local_library::Change::Import),
                LibraryChooseDirectory => Some(local_library::Change::ChooseDirectory),
                LibraryRefreshDirectory(input) => {
                    Some(local_library::Change::RefreshDirectory(input.id))
                }
                LibraryRemoveDirectory(input) => {
                    Some(local_library::Change::RemoveDirectory(input.id))
                }
                _ => None,
            };
            let changed = change.is_some();
            if let Some(change) = change {
                if !local_library::change(&state.downloads, change).await? {
                    return Ok(selection(Value::Null));
                }
            }
            let downloads = state.downloads.clone();
            let library = state.library.clone();
            let (cache, port) = (state.covers.1.clone(), state.port);
            let snapshot = tauri::async_runtime::spawn_blocking(move || {
                let (records, excluded, sources) = downloads.access_history(|history| {
                    history.reconcile();
                    let db = history.db.lock();
                    let (records, excluded) = history.snapshot(&db)?;
                    Ok((records, excluded, local_library::sources(&db)?))
                })?;
                let mut view = library
                    .lock()
                    .unwrap()
                    .view(&sources, records.clone(), &excluded);
                if let Some(cache) = cache {
                    cache.decorate_library(&mut view, &records, port);
                }
                Ok::<_, String>(view)
            })
            .await
            .map_err(|_| "local_library_unavailable")??;
            Ok(if changed {
                selection(snapshot)
            } else {
                snapshot
            })
        }
        RecyclePrepare(input) => {
            let id = input.id;
            let path_hint = input.path_hint.map(std::path::PathBuf::from);
            let downloads = state.downloads.clone();
            let protected = state.protected_paths.clone();
            let target = tauri::async_runtime::spawn_blocking(move || {
                downloads.access_history(|history| {
                    delete_plan::Target::resolve(history, &id, path_hint.as_deref(), &protected)
                })
            })
            .await
            .map_err(|_| "local_library_unavailable")??;
            let name = target
                .path
                .file_name()
                .map(|name| name.to_string_lossy().into_owned());
            let token = state.delete_plans.lock().unwrap().prepare(target);
            Ok(json!({"token": token, "name": name}))
        }
        RecycleCancel(input) => {
            let token = &input.token;
            state.delete_plans.lock().unwrap().cancel(token);
            Ok(Value::Null)
        }
        RecycleExecute(input) => {
            let token = &input.token;
            let target = state.delete_plans.lock().unwrap().take(token)?;
            let downloads = state.downloads.clone();
            let protected = state.protected_paths.clone();
            tauri::async_runtime::spawn_blocking(move || {
                downloads.access_history(|history| {
                    let saved = target.execute(history, &protected)?;
                    Ok(json!({"historySaved": saved}))
                })
            })
            .await
            .map_err(|_| "local_recycle_uncertain")?
        }
        LibraryOpen(Id { ref id })
        | LibraryReveal(Id { ref id })
        | LibraryRemove(Id { ref id }) => {
            let remove = matches!(request, LibraryRemove(_));
            let reveal = matches!(request, LibraryReveal(_));
            let id = id.clone();
            let downloads = state.downloads.clone();
            let (covers, port) = (state.covers.clone(), state.port);
            let (client, sessions) = (state.client.clone(), state.sessions.clone());
            tauri::async_runtime::spawn_blocking(move || {
                let song = downloads.access_history(|history| {
                    history.reconcile();
                    let (records, excluded, sources) = {
                        let db = history.db.lock();
                        let (records, excluded) = history.snapshot(&db)?;
                        if excluded.contains(&id) {
                            return Err("saved_file_missing".into());
                        }
                        (records, excluded, local_library::sources(&db)?)
                    };
                    let mut songs =
                        local_library::Library::songs(&sources, records, &mut Default::default());
                    let song = songs
                        .remove(&id)
                        .filter(|song| !excluded.contains(&song.id))
                        .ok_or("saved_file_missing")?;
                    if remove {
                        history.remove_song(&song.path, &id)?;
                        return Ok(None);
                    }
                    Ok(Some(song))
                })?;
                let Some(song) = song else {
                    return Ok(Value::Null);
                };
                let file = song.playback_path()?;
                if reveal {
                    crate::downloads::reveal_file(&file)?;
                    return Ok(Value::Null);
                }
                let track = song.download_identity.as_ref();
                let cache = covers.1.as_ref();
                let cover = track.and_then(|track| cache?.cached_for_track(track, port));
                let lyrics = track.and_then(|track| cache?.cached_lyrics(track));
                if cover.is_none() || lyrics.is_none() {
                    if let (Some(track), Some(cache)) = (track.cloned(), cache.cloned()) {
                        tauri::async_runtime::spawn(async move {
                            let _ = tokio::join!(
                                cache.cover(&covers, &track, None, port),
                                cache.lyrics(&client, &track)
                            );
                        });
                    }
                }
                let mime = match song.format {
                    "mp3" => "audio/mpeg",
                    "flac" => "audio/flac",
                    _ => "audio/mp4",
                };
                let playback_id = sessions.insert_local(file, mime);
                Ok(json!({"playbackId":playback_id,"streamUrl":format!(
                    "http://127.0.0.1:{port}/api/playback/{playback_id}/stream"
                ),"cover":cover,"lyrics":lyrics}))
            })
            .await
            .map_err(|_| "local_library_unavailable")?
        }
        PlaybackOpen(input) => {
            let identity = input.identity.checked()?;
            let (media, _, _) = fallback::resolve(&state.client, &state.fallbacks, &identity).await?;
            let id = state.sessions.insert_media(media);
            Ok(json!({
                "playbackId": id,
                "streamUrl": format!("http://127.0.0.1:{}/api/playback/{id}/stream", state.port),
                "expiresInSeconds": 120,
                "identity": identity
            }))
        }
        DownloadCancel(input) => {
            state
                .downloads
                .operate(&input.id, "cancel", &state.client)
                .await
        }
        DownloadRetry(input) => state
            .downloads
            .operate(&input.id, "retry", &state.client)
            .await
            .map(selection),
        DownloadDismiss(input) => {
            state
                .downloads
                .operate(&input.id, "remove", &state.client)
                .await
        }
        PlaybackClose(input) => {
            state.sessions.close(&input.playback_id);
            Ok(Value::Null)
        }
        PlaybackRenew(input) => renew(&state.sessions, &input.playback_id),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_untyped_operations_and_incorrect_payloads() {
        for request in [
            json!({ "path": "/api/providers", "body": null }),
            json!({ "op": "downloadCreate", "payload": { "identity": {"providerId":"qq","platformId":"ab"}, "path": "song.mp3" } }),
            json!({ "op": "recycleExecute", "payload": { "token": 1 } }),
            json!({ "op": "libraryRemove", "payload": { "id": "test", "deleteFile": true } }),
        ] {
            assert!(serde_json::from_value::<Operation>(request).is_err());
        }
    }

    #[test]
    fn shared_online_identity_uses_the_command_validator() {
        let rows: Vec<Value> = serde_json::from_str(include_str!(
            "../../../tests/fixtures/contracts/identity.json"
        ))
        .unwrap();
        for row in rows {
            let op = serde_json::from_value::<Operation>(json!({
                "op": "lyricsGet", "payload": row["identity"]
            }));
            let accepted =
                matches!(op, Ok(Operation::LyricsGet(identity)) if identity.validate().is_ok());
            assert_eq!(
                accepted,
                row["valid"].as_bool().unwrap(),
                "{}",
                row["identity"]
            );
        }
    }

    #[test]
    fn missing_session_is_expired_and_close_is_idempotent() {
        let sessions = sessions::Sessions::new();
        sessions.close("missing");
        sessions.close("missing");
        let fault = Fault::from_code(&renew(&sessions, "missing").unwrap_err());
        assert_eq!(fault.code, "playback_expired");
        assert_eq!(fault.status, 410);
        assert!(!fault.retryable);
    }
}
