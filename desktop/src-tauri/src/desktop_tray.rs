use crate::desktop_window::restore;
use serde::Deserialize;
use tauri::{
    menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, WebviewWindow,
};

struct Controls {
    previous: MenuItem<tauri::Wry>,
    toggle: MenuItem<tauri::Wry>,
    next: MenuItem<tauri::Wry>,
    lyrics: CheckMenuItem<tauri::Wry>,
}

pub fn setup(app: &AppHandle) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "打开拾音", true, None::<&str>)?;
    let previous = MenuItem::with_id(app, "previous", "上一首", false, None::<&str>)?;
    let toggle = MenuItem::with_id(app, "toggle", "播放", false, None::<&str>)?;
    let next = MenuItem::with_id(app, "next", "下一首", false, None::<&str>)?;
    let lyrics = CheckMenuItem::with_id(app, "lyrics", "桌面歌词", false, false, None::<&str>)?;
    let exit = MenuItem::with_id(app, "exit", "退出拾音", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[
            &open,
            &PredefinedMenuItem::separator(app)?,
            &previous,
            &toggle,
            &next,
            &PredefinedMenuItem::separator(app)?,
            &lyrics,
            &PredefinedMenuItem::separator(app)?,
            &exit,
        ],
    )?;
    let icon = app
        .default_window_icon()
        .ok_or(tauri::Error::AssetNotFound("icons/icon.ico".into()))?;
    TrayIconBuilder::with_id("shiyin")
        .icon(icon.clone())
        .tooltip("拾音")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_tray_icon_event(|tray, event| {
            if matches!(
                event,
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                }
            ) {
                restore(tray.app_handle());
            }
        })
        .on_menu_event(|app, event| match event.id().as_ref() {
            "open" => restore(app),
            "exit" => app.exit(0),
            "previous" | "toggle" | "next" | "lyrics" => {
                if event.id().as_ref() == "lyrics" {
                    // 原生菜单会自动翻转勾选，先恢复实际窗口状态。
                    let visible = app
                        .get_webview_window("desktop-lyrics")
                        .is_some_and(|window| window.is_visible().unwrap_or(false));
                    set_lyrics_visible(app, visible);
                }
                let _ = app.emit_to("main", "desktop-tray-action", event.id().as_ref());
            }
            _ => {}
        })
        .build(app)?;
    app.manage(Controls {
        previous,
        toggle,
        next,
        lyrics,
    });
    Ok(())
}

pub fn available(app: &AppHandle) -> bool {
    app.try_state::<Controls>().is_some()
}

pub fn set_lyrics_visible(app: &AppHandle, visible: bool) {
    if let Some(controls) = app.try_state::<Controls>() {
        if let Err(error) = controls.lyrics.set_checked(visible) {
            eprintln!("更新托盘歌词状态失败: {error}");
        }
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Playback {
    can_previous: bool,
    can_toggle: bool,
    can_next: bool,
    playing: bool,
}

#[tauri::command]
pub fn desktop_tray_playback(window: WebviewWindow, playback: Playback) -> Result<(), String> {
    if window.label() != "main" {
        return Err("invalid window".into());
    }
    let Some(controls) = window.try_state::<Controls>() else {
        return Ok(());
    };
    controls
        .previous
        .set_enabled(playback.can_previous)
        .and_then(|_| controls.toggle.set_enabled(playback.can_toggle))
        .and_then(|_| controls.next.set_enabled(playback.can_next))
        .and_then(|_| controls.lyrics.set_enabled(true))
        .and_then(|_| {
            controls
                .toggle
                .set_text(if playback.playing { "暂停" } else { "播放" })
        })
        .map_err(|error| error.to_string())
}
