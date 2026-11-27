#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod covers;
mod core_ipc;
mod delete_plan;
mod desktop_lyrics;
#[cfg(windows)]
mod desktop_tray;
#[cfg(windows)]
mod desktop_window;
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
fn desktop_platform(window: tauri::WebviewWindow, state: tauri::State<'_, Desktop>) -> Value {
    #[cfg(windows)]
    let tray = desktop_tray::available(window.app_handle());
    #[cfg(not(windows))]
    let tray = false;
    #[cfg(windows)]
    let hidden = desktop_window::hidden(&window);
    #[cfg(not(windows))]
    let hidden = !window.is_visible().unwrap_or(true);
    let lyrics_visible = window
        .get_webview_window("desktop-lyrics")
        .is_some_and(|lyrics| lyrics.is_visible().unwrap_or(false));
    json!({
        "window": window.label(),
        "mediaPort": state.port,
        "tray": tray,
        "desktopLyrics": cfg!(windows),
        "recycle": cfg!(windows),
        "mediaCache": state.covers.1.is_some(),
        "hidden": hidden,
        "lyricsVisible": lyrics_visible
    })
}

fn main() {
    let builder = tauri::Builder::default();
    #[cfg(windows)]
    let builder = builder.plugin(tauri_plugin_single_instance::init(|app, _, _| {
        desktop_window::restore(app);
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
            if let Err(error) = desktop_window::setup(app.handle()).and_then(|_| desktop_tray::setup(app.handle())) {
                eprintln!("系统托盘初始化失败: {error}");
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            #[cfg(windows)]
            {
                desktop_window::on_close(window, event);
                if window.label() == "main" && matches!(event, tauri::WindowEvent::Resized(_) | tauri::WindowEvent::Focused(_)) {
                    desktop_window::report_visibility(window);
                }
            }
            if window.label() == "main" && matches!(event, tauri::WindowEvent::Destroyed) {
                if let Some(lyrics) = window.get_webview_window("desktop-lyrics") {
                    let _ = lyrics.destroy();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            core_ipc::core_request,
            desktop_platform,
            #[cfg(windows)]
            desktop_window::desktop_close_action,
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
