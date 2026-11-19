#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod covers;
mod desktop_lyrics;
mod download_history;
mod download_media;
mod download_resolver;
mod downloads;
mod fallback;
mod local_library;
mod lyrics;
mod media_cache;
mod provider;
mod sessions;
mod transcode;
mod transport;
use serde_json::{json, Value};
use tauri::{Emitter, Manager};

struct Desktop {
    sessions: sessions::Sessions,
    client: reqwest::Client,
    port: u16,
    fallbacks: fallback::Config,
    covers: covers::Covers,
    downloads: downloads::Downloads,
    library: std::sync::Arc<std::sync::Mutex<local_library::Library>>,
}

#[tauri::command]
async fn desktop_request(
    path: String,
    body: Value,
    state: tauri::State<'_, Desktop>,
) -> Result<Value, String> {
    match path.as_str() {
        "/api/providers" => Ok(provider::catalog()),
        "/api/search" => {
            let mut page = provider::search(&state.client, &body).await?;
            covers::Covers::map_page(&mut page);
            state.downloads.register(&mut page);
            Ok(page)
        }
        "/api/covers/palette" => {
            let url = body["url"].as_str().ok_or("封面地址无效")?;
            let relay = state
                .covers
                .register_palette(url, state.port)
                .ok_or("封面地址不支持代理")?;
            Ok(json!({"url": relay}))
        }
        "/api/lyrics" => match &state.covers.1 {
            Some(cache) => cache.lyrics(&state.client, &body).await,
            None => lyrics::get(&state.client, &body).await,
        },
        "/api/media-cache/cover" => {
            let cover = match &state.covers.1 {
                Some(cache) => {
                    cache
                        .cover(
                            &state.covers,
                            &body["identity"],
                            body["cover"].as_str(),
                            state.port,
                        )
                        .await
                }
                None => None,
            };
            Ok(json!({"cover":cover}))
        }
        "/api/media-cache/queue-covers" => {
            let entries = body["entries"]
                .as_array()
                .filter(|entries| entries.len() <= 200)
                .ok_or("invalid_input")?;
            let mut urls = Vec::with_capacity(entries.len());
            let mut local = std::collections::HashMap::new();
            if entries.iter().any(|entry| entry["fileId"].is_string()) {
                let (records, excluded) = state.downloads.library_snapshot()?;
                for record in records {
                    let id = local_library::path_key(&record.path);
                    if !excluded.contains(&id) {
                        local.entry(id).or_insert(record.identity);
                    }
                }
            }
            for entry in entries {
                let identity = match entry["fileId"].as_str() {
                    Some(id) => local.get(id),
                    None => entry.get("track"),
                };
                urls.push(identity.and_then(|identity| {
                    state.covers.1.as_ref()?.indexed_cover(identity, state.port)
                }));
            }
            Ok(json!(urls))
        }
        "/api/media-cache/settings" => {
            let cache = state.covers.1.as_ref().ok_or("媒体缓存不可用")?;
            if body["action"] == "open" {
                std::process::Command::new("explorer.exe")
                    .arg(cache.directory())
                    .spawn()
                    .map_err(|_| "无法打开缓存文件夹")?;
            } else if !body.is_null() {
                return Err("invalid_input".into());
            }
            Ok(json!({"directory":cache.directory()}))
        }
        "/api/media-cache/clear" => {
            use media_cache::ClearScope;
            let scope = match body["scope"].as_str() {
                Some("cover") => ClearScope::Cover,
                Some("lyrics") => ClearScope::Lyrics,
                Some("all") => ClearScope::All,
                None if body.is_null() => ClearScope::All,
                _ => return Err("invalid_input".into()),
            };
            state.downloads.clear_media_cache(scope)?;
            Ok(Value::Null)
        }
        "/api/downloads/options" => Ok(state.downloads.options(&state.client, &body).await),
        "/api/downloads" => {
            if body.is_null() {
                Ok(state.downloads.list())
            } else {
                state.downloads.create(&state.client, &body).await
            }
        }
        "/api/downloads/settings" => state.downloads.settings(&body),
        "/api/downloads/settings/directory" => state.downloads.directory(&body).await,
        "/api/downloads/saved" => state.downloads.saved(),
        "/api/local-library" => {
            if !body.is_null() {
                let restored = local_library::change(&state.library, &body).await?;
                if !restored.is_empty() {
                    state.downloads.restore_library_songs(&restored)?;
                }
            }
            let (downloads, excluded) = state.downloads.library_snapshot()?;
            let library = state.library.clone();
            let (cache, port) = (state.covers.1.clone(), state.port);
            tauri::async_runtime::spawn_blocking(move || {
                let mut view = library.lock().unwrap().view(downloads.clone(), &excluded);
                if let Some(cache) = cache {
                    cache.decorate_library(&mut view, &downloads, port);
                }
                view
            })
            .await
            .map_err(|_| "local_library_unavailable".into())
        }
        "/api/local-library/open" | "/api/local-library/reveal" | "/api/local-library/remove" => {
            let id = body["id"].as_str().ok_or("invalid_input")?;
            let (downloads, excluded) = state.downloads.library_snapshot()?;
            if excluded.contains(id) {
                return Err("saved_file_missing".into());
            }
            let songs = state.library.lock().unwrap().songs(downloads);
            let song = songs.get(id).ok_or("saved_file_missing")?;
            if path == "/api/local-library/remove" {
                let delete_file = body["deleteFile"].as_bool().ok_or("invalid_input")?;
                state
                    .downloads
                    .remove_library_song(&song.path, id, delete_file)?;
                return Ok(Value::Null);
            }
            let file = song.playback_path()?;
            let track = song.download_identity.as_ref();
            let cache = state.covers.1.as_ref();
            let cover = track.and_then(|track| cache?.cached_for_track(track, state.port));
            let lyrics = track.and_then(|track| cache?.cached_lyrics(track));
            if path == "/api/local-library/open" && (cover.is_none() || lyrics.is_none()) {
                if let (Some(track), Some(cache)) = (track.cloned(), cache.cloned()) {
                    let (client, covers, port) =
                        (state.client.clone(), state.covers.clone(), state.port);
                    tauri::async_runtime::spawn(async move {
                        let _ = tokio::join!(
                            cache.cover(&covers, &track, None, port),
                            cache.lyrics(&client, &track)
                        );
                    });
                }
            }
            if path == "/api/local-library/reveal" {
                downloads::reveal_file(&file)?;
                return Ok(Value::Null);
            }
            let mime = match song.format {
                "mp3" => "audio/mpeg",
                "flac" => "audio/flac",
                _ => "audio/mp4",
            };
            let id = state.sessions.insert_local(file, mime);
            Ok(
                json!({"playbackId":id,"streamUrl":format!("http://127.0.0.1:{}/api/playback/{id}/stream",state.port),"cover":cover,"lyrics":lyrics}),
            )
        }
        "/api/playback/open" => {
            let identity = &body["identity"];
            let (media, resolver) =
                fallback::resolve(&state.client, &state.fallbacks, identity).await?;
            let id = state.sessions.insert_media(media);
            let now = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_millis() as u64;
            Ok(
                json!({"playbackId":id,"streamUrl":format!("http://127.0.0.1:{}/api/playback/{}/stream",state.port,id),
                "resolver":resolver,"expiresInSeconds":120,"media":{"id":id,"identity":identity,"protocol":"progressive",
                "representation":{},"resolvedAt":now,"validUntil":null}}),
            )
        }
        _ => {
            let parts: Vec<_> = path.split('/').collect();
            if parts.len() == 6
                && parts[1] == "api"
                && parts[2] == "downloads"
                && parts[3] == "saved"
                && parts[5] == "reveal"
            {
                return state.downloads.reveal_saved(parts[4]);
            }
            if parts.len() == 5 && parts[1] == "api" && parts[2] == "downloads" {
                return state
                    .downloads
                    .operate(parts[3], parts[4], &state.client)
                    .await;
            }
            if parts.len() == 5 && parts[1] == "api" && parts[2] == "playback" {
                match parts[4] {
                    "close" => {
                        state.sessions.close(parts[3]);
                        return Ok(Value::Null);
                    }
                    "renew" => {
                        return if state.sessions.renew(parts[3]) {
                            Ok(Value::Null)
                        } else {
                            Err("播放会话已过期，请重新播放".into())
                        }
                    }
                    _ => {}
                }
            }
            Err("此功能尚未迁移到桌面版（本机音乐库及目录管理暂不可用）".into())
        }
    }
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let fallbacks = fallback::Config::from_env().map_err(std::io::Error::other)?;
            let sessions = sessions::Sessions::new();
            let client = reqwest::Client::builder()
                .user_agent("Mozilla/5.0")
                .referer(false)
                .redirect(reqwest::redirect::Policy::none())
                .connect_timeout(std::time::Duration::from_secs(10))
                .read_timeout(std::time::Duration::from_secs(30))
                .build()?;
            let mut covers = covers::Covers::default();
            covers.1 =
                media_cache::MediaCache::open(&app.path().app_data_dir()?.join("media-cache"))
                    .map_err(|error| {
                        eprintln!("桌面媒体缓存不可用: {error}");
                    })
                    .ok();
            let port = tauri::async_runtime::block_on(transport::start_with_covers(
                transport::Transport {
                    sessions: sessions.clone(),
                    client: client.clone(),
                },
                covers.clone(),
            ))?;
            if let Some(cache) = covers.1.clone() {
                let handle = app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    loop {
                        cache.cover_changed().await;
                        let _ = handle.emit("desktop-cached-covers-changed", ());
                    }
                });
            }
            let cleanup = sessions.clone();
            tauri::async_runtime::spawn(async move {
                loop {
                    tokio::time::sleep(std::time::Duration::from_secs(10)).await;
                    cleanup.prune();
                }
            });
            app.manage(Desktop {
                sessions,
                client,
                port,
                fallbacks,
                covers: covers.clone(),
                library: std::sync::Arc::new(std::sync::Mutex::new(
                    local_library::Library::open(
                        app.path().app_config_dir()?.join("desktop-library.json"),
                    )
                    .map_err(std::io::Error::other)?,
                )),
                downloads: {
                    let mut downloads = downloads::Downloads::with_history(
                        app.path().app_config_dir()?.join("download-naming.json"),
                        app.path().audio_dir()?.join("拾音"),
                    )
                    .map_err(std::io::Error::other)?;
                    downloads.media_covers = covers.clone();
                    downloads.tools_dir = Some(app.path().resource_dir()?.join("tools"));
                    downloads
                },
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == "main" && matches!(event, tauri::WindowEvent::Destroyed) {
                if let Some(lyrics) = window.get_webview_window("desktop-lyrics") {
                    let _ = lyrics.destroy();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            desktop_request,
            desktop_lyrics::toggle_desktop_lyrics,
            desktop_lyrics::place_desktop_lyrics,
            desktop_lyrics::show_desktop_lyrics,
            desktop_lyrics::toggle_desktop_lyrics_settings,
            desktop_lyrics::desktop_lyrics_settings_window,
            desktop_lyrics::close_desktop_lyrics
        ])
        .build(tauri::generate_context!())
        .expect("桌面应用初始化失败")
        .run(|app, event| {
            if let tauri::RunEvent::ExitRequested { api, .. } = &event {
                let downloads = app.state::<Desktop>().downloads.clone();
                if downloads.active() {
                    api.prevent_exit();
                    let app = app.clone();
                    tauri::async_runtime::spawn(async move {
                        downloads.shutdown().await;
                        app.exit(0);
                    });
                }
            }
            if matches!(event, tauri::RunEvent::Exit) {
                app.state::<Desktop>().sessions.close_all();
            }
        });
}
