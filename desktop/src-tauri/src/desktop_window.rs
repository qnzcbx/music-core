use serde::{Deserialize, Serialize};
use std::{
    path::{Path, PathBuf},
    sync::Mutex,
};
use tauri::{AppHandle, Emitter, Manager, WebviewWindow, Window, WindowEvent};

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

pub fn setup(app: &AppHandle) -> tauri::Result<()> {
    let path = app.path().app_config_dir()?.join("window.json");
    app.manage(Settings {
        action: Mutex::new(read_close_action(&path)),
        path,
    });

    Ok(())
}

pub fn hidden(window: &WebviewWindow) -> bool {
    !window.is_visible().unwrap_or(true) || window.is_minimized().unwrap_or(false)
}

pub fn report_visibility(window: &Window) {
    if let Some(main) = window.get_webview_window("main") {
        let _ = main.emit("desktop-main-hidden", hidden(&main));
    }
}

pub fn restore(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let result = window
            .show()
            .and_then(|_| window.unminimize())
            .and_then(|_| {
                let _ = window.emit("desktop-main-hidden", hidden(&window));
                window.set_focus()
            });
        if let Err(error) = result {
            eprintln!("恢复主窗口失败: {error}");
        }
    }
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
    } else if crate::desktop_tray::available(window.app_handle()) {
        match window.hide() {
            Ok(()) => {
                api.prevent_close();
                let _ = window.emit("desktop-main-hidden", true);
            }
            Err(error) => eprintln!("隐藏主窗口失败: {error}"),
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
        write_snapshot(&settings.path, &action).map_err(|_| "无法保存关闭窗口设置")?;
        *current = action;
    }
    Ok(*current)
}

fn write_snapshot(path: &std::path::Path, value: &impl Serialize) -> Result<(), String> {
    use std::io::Write;
    let parent = path.parent().ok_or("file_io_error")?;
    std::fs::create_dir_all(parent).map_err(|_| "file_io_error")?;
    // 同目录临时文件同步后原子替换；失败不修改内存快照，也不覆盖成品。
    let mut temporary = tempfile::NamedTempFile::new_in(parent).map_err(|_| "file_io_error")?;
    serde_json::to_writer_pretty(&mut temporary, value).map_err(|_| "file_io_error")?;
    temporary.flush().map_err(|_| "file_io_error")?;
    temporary
        .as_file()
        .sync_all()
        .map_err(|_| "file_io_error")?;
    temporary.persist(path).map_err(|_| "file_io_error")?;
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
