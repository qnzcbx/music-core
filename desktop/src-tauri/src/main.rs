#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod covers;
mod delete_plan;
mod desktop_lyrics;
#[cfg(windows)]
mod desktop_tray;
mod download_history;
mod download_media;
mod download_resolver;
mod downloads;
mod fallback;
mod file_recycle;
mod local_library;
mod lyrics;
mod media_cache;
mod provider;
mod sessions;
mod storage;
mod transcode;
mod transport;
use serde_json::{json, Value};
use tauri::{Emitter, Manager};

struct Desktop {
    sessions: sessions::Sessions,
    delete_plans: std::sync::Mutex<delete_plan::Plans>,
    protected_paths: Vec<std::path::PathBuf>,
    client: reqwest::Client,
    port: u16,
    fallbacks: fallback::Config,
    covers: covers::Covers,
    downloads: downloads::Downloads,
    library: std::sync::Arc<std::sync::Mutex<local_library::Library>>,
}

#[tauri::command]
async fn desktop_request(
    window: tauri::WebviewWindow,
    path: String,
    body: Value,
    state: tauri::State<'_, Desktop>,
) -> Result<Value, String> {
    if path.starts_with("/api/local-library/recycle/") && window.label() != "main" {
        return Err("invalid_input".into());
    }
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
                .filter(|items| items.len() <= 200)
                .ok_or("invalid_input")?
                .clone();
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
            let downloads = state.downloads.clone();
            tauri::async_runtime::spawn_blocking(move || downloads.clear_media_cache(scope))
                .await
                .map_err(|_| "媒体缓存清理失败")??;
            Ok(Value::Null)
        }
        "/api/downloads/options" => Ok(state.downloads.options(&state.client, &body).await),
        "/api/downloads" => {
            if body.is_null() {
                let downloads = state.downloads.clone();
                tauri::async_runtime::spawn_blocking(move || downloads.poll())
                    .await
                    .map_err(|_| "download_history_unavailable")?
            } else {
                state.downloads.create(&state.client, &body).await
            }
        }
        "/api/downloads/settings" => {
            let downloads = state.downloads.clone();
            tauri::async_runtime::spawn_blocking(move || downloads.settings(&body))
                .await
                .map_err(|_| "download_history_unavailable")?
        }
        "/api/downloads/settings/directory" => state.downloads.directory(&body).await,
        "/api/local-library" => {
            if !body.is_null() {
                local_library::change(&state.downloads, &body).await?;
            }
            let downloads = state.downloads.clone();
            let library = state.library.clone();
            let (cache, port) = (state.covers.1.clone(), state.port);
            tauri::async_runtime::spawn_blocking(move || {
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
                Ok(view)
            })
            .await
            .map_err(|_| "local_library_unavailable")?
        }
        "/api/local-library/recycle/prepare" => {
            let id = body["id"].as_str().ok_or("invalid_input")?.to_owned();
            let path_hint = body["pathHint"].as_str().map(std::path::PathBuf::from);
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
        "/api/local-library/recycle/cancel" => {
            let token = body["token"].as_str().ok_or("invalid_input")?;
            state.delete_plans.lock().unwrap().cancel(token);
            Ok(Value::Null)
        }
        "/api/local-library/recycle/execute" => {
            let token = body["token"].as_str().ok_or("invalid_input")?;
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
        "/api/local-library/open" | "/api/local-library/reveal" | "/api/local-library/remove" => {
            let id = body["id"].as_str().ok_or("invalid_input")?.to_owned();
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
                    if path == "/api/local-library/remove" {
                        let delete_file = body["deleteFile"].as_bool().ok_or("invalid_input")?;
                        history.remove_song(&song.path, &id, delete_file)?;
                        return Ok(None);
                    }
                    Ok(Some(song))
                })?;
                let Some(song) = song else {
                    return Ok(Value::Null);
                };
                let file = song.playback_path()?;
                if path == "/api/local-library/reveal" {
                    downloads::reveal_file(&file)?;
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
    let builder = tauri::Builder::default();
    #[cfg(windows)]
    let builder = builder.plugin(tauri_plugin_single_instance::init(|app, _, _| {
        desktop_tray::restore(app);
    }));
    let exit_ready = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    builder
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
            let data_dir = app.path().app_data_dir()?;
            let db = storage::Database::open(&data_dir.join("music-core.sqlite3"))?;
            let mut covers = covers::Covers::default();
            covers.1 = media_cache::MediaCache::open(&data_dir.join("media-cache"), db.clone())
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
            let mut protected_paths = vec![
                app.path().app_data_dir()?,
                app.path().app_config_dir()?,
                app.path().app_local_data_dir()?,
                app.path().resource_dir()?,
            ];
            protected_paths.extend(
                [
                    "SystemRoot",
                    "ProgramFiles",
                    "ProgramFiles(x86)",
                    "ProgramData",
                ]
                .into_iter()
                .filter_map(std::env::var_os)
                .map(std::path::PathBuf::from),
            );
            app.manage(Desktop {
                sessions,
                delete_plans: Default::default(),
                protected_paths,
                client,
                port,
                fallbacks,
                covers: covers.clone(),
                library: std::sync::Arc::new(std::sync::Mutex::new(local_library::Library::new())),
                downloads: {
                    let mut downloads = downloads::Downloads::with_database(
                        db,
                        app.path().audio_dir()?.join("拾音"),
                    );
                    downloads.media_covers = covers.clone();
                    downloads.tools_dir = Some(app.path().resource_dir()?.join("tools"));
                    downloads
                },
            });
            #[cfg(windows)]
            if let Err(error) = desktop_tray::setup(app.handle()) {
                eprintln!("系统托盘初始化失败: {error}");
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            #[cfg(windows)]
            desktop_tray::on_close(window, event);
            if window.label() == "main" && matches!(event, tauri::WindowEvent::Destroyed) {
                if let Some(lyrics) = window.get_webview_window("desktop-lyrics") {
                    let _ = lyrics.destroy();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            desktop_request,
            #[cfg(windows)]
            desktop_tray::desktop_close_action,
            #[cfg(windows)]
            desktop_tray::desktop_tray_playback,
            desktop_lyrics::toggle_desktop_lyrics,
            desktop_lyrics::place_desktop_lyrics,
            desktop_lyrics::show_desktop_lyrics,
            desktop_lyrics::toggle_desktop_lyrics_settings,
            desktop_lyrics::desktop_lyrics_settings_window,
            desktop_lyrics::close_desktop_lyrics
        ])
        .build(tauri::generate_context!())
        .expect("桌面应用初始化失败")
        .run(move |app, event| {
            if let tauri::RunEvent::ExitRequested { api, .. } = &event {
                use std::sync::atomic::Ordering;
                if !exit_ready.load(Ordering::Acquire) {
                    api.prevent_exit();
                    let downloads = app.state::<Desktop>().downloads.clone();
                    if downloads.begin_shutdown() {
                        let app = app.clone();
                        let exit_ready = exit_ready.clone();
                        tauri::async_runtime::spawn(async move {
                            if !downloads
                                .wait_for_shutdown(std::time::Duration::from_secs(8))
                                .await
                            {
                                eprintln!("退出等待超过 8 秒，部分下载资源可能尚未清理");
                            }
                            exit_ready.store(true, Ordering::Release);
                            app.exit(0);
                        });
                    }
                }
            }
            if matches!(event, tauri::RunEvent::Exit) {
                app.state::<Desktop>().sessions.close_all();
            }
        });
}
