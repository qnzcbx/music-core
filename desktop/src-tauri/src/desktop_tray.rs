use serde::{Deserialize, Serialize};
use std::{
    path::{Path, PathBuf},
    sync::Mutex,
};
use tauri::{
    menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, WebviewWindow, Window, WindowEvent,
};

#[derive(Clone, Copy, Debug, Default, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum CloseAction {
    #[default]
    Tray,
    Exit,
}

fn read_close_action(path: &Path) -> CloseAction {
    std::fs::read(path)
        .ok()
        .and_then(|bytes| serde_json::from_slice(&bytes).ok())
        .unwrap_or_default()
}

struct Settings {
    path: PathBuf,
    action: Mutex<CloseAction>,
}

struct Controls {
    previous: MenuItem<tauri::Wry>,
    toggle: MenuItem<tauri::Wry>,
    next: MenuItem<tauri::Wry>,
    lyrics: CheckMenuItem<tauri::Wry>,
}

pub fn restore(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let result = window
            .show()
            .and_then(|_| window.unminimize())
            .and_then(|_| {
                let _ = app.emit_to("main", "desktop-main-hidden", false);
                window.set_focus()
            });
        if let Err(error) = result {
            eprintln!("恢复主窗口失败: {error}");
        }
    }
}

pub fn setup(app: &AppHandle) -> tauri::Result<()> {
    let path = app.path().app_config_dir()?.join("window.json");
    app.manage(Settings {
        action: Mutex::new(read_close_action(&path)),
        path,
    });

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

pub fn on_close(window: &Window, event: &WindowEvent) {
    let WindowEvent::CloseRequested { api, .. } = event else {
        return;
    };
    if window.label() != "main" {
        return;
    }
    let Some(settings) = window.try_state::<Settings>() else {
        return;
    };
    if *settings.action.lock().unwrap() == CloseAction::Exit {
        api.prevent_close();
        window.app_handle().exit(0);
    } else if window.try_state::<Controls>().is_some() {
        match window.hide() {
            Ok(()) => {
                api.prevent_close();
                let _ = window.emit("desktop-main-hidden", true);
            }
            Err(error) => eprintln!("隐藏主窗口失败: {error}"),
        }
    }
}

pub fn set_lyrics_visible(app: &AppHandle, visible: bool) {
    if let Some(controls) = app.try_state::<Controls>() {
        if let Err(error) = controls.lyrics.set_checked(visible) {
            eprintln!("更新托盘歌词状态失败: {error}");
        }
    }
}

#[tauri::command]
pub fn desktop_close_action(
    window: WebviewWindow,
    action: Option<CloseAction>,
) -> Result<CloseAction, String> {
    if window.label() != "main" {
        return Err("invalid window".into());
    }
    let settings = window.try_state::<Settings>().ok_or("窗口设置不可用")?;
    let mut current = settings.action.lock().unwrap();
    if let Some(action) = action {
        write_snapshot(&settings.path, &action)
            .map_err(|_| "无法保存关闭窗口设置")?;
        *current = action;
    }
    Ok(*current)
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
fn write_snapshot(path: &std::path::Path, value: &impl Serialize) -> Result<(), String> {
    use std::io::Write;
    let parent = path.parent().ok_or("file_io_error")?;
    std::fs::create_dir_all(parent).map_err(|_| "file_io_error")?;
    // 同目录临时文件同步后原子替换；失败不修改内存快照，也不覆盖成品。
    let mut temporary =
        tempfile::NamedTempFile::new_in(parent).map_err(|_| "file_io_error")?;
    serde_json::to_writer_pretty(&mut temporary, value)
        .map_err(|_| "file_io_error")?;
    temporary
        .flush()
        .map_err(|_| "file_io_error")?;
    temporary
        .as_file()
        .sync_all()
        .map_err(|_| "file_io_error")?;
    temporary
        .persist(path)
        .map_err(|_| "file_io_error")?;
    Ok(())
}


#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn close_action_defaults_to_tray_and_round_trips_exit() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("window.json");
        assert_eq!(read_close_action(&path), CloseAction::Tray);
        write_snapshot(&path, &CloseAction::Exit).unwrap();
        assert_eq!(read_close_action(&path), CloseAction::Exit);
        std::fs::write(&path, b"invalid").unwrap();
        assert_eq!(read_close_action(&path), CloseAction::Tray);
    }
}
