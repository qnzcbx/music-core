use tauri::{
    Emitter, Manager, PhysicalPosition, PhysicalSize, WebviewUrl, WebviewWindow, WindowEvent,
};

const LABEL: &str = "desktop-lyrics";
const VISIBILITY: &str = "desktop-lyrics-visible";

#[tauri::command]
pub async fn toggle_desktop_lyrics(window: WebviewWindow) -> Result<(), String> {
    if window.label() != "main" {
        return Err("invalid window".into());
    }
    let app = window.app_handle().clone();
    if let Some(lyrics) = app.get_webview_window(LABEL) {
        return lyrics.destroy().map_err(|e| e.to_string());
    }
    let lyrics = tauri::WebviewWindowBuilder::new(
        &app,
        LABEL,
        WebviewUrl::App("index.html?desktop-lyrics".into()),
    )
    .title("拾音 · 桌面歌词")
    .decorations(false)
    .shadow(false)
    .transparent(true)
    .always_on_top(true)
    .skip_taskbar(true)
    .resizable(false)
    .maximizable(false)
    .visible(false)
    .focused(false)
    .build()
    .map_err(|e| e.to_string())?;

    lyrics.on_window_event(move |event| match event {
        WindowEvent::Destroyed => {
            let _ = app.emit_to("main", VISIBILITY, false);
        }
        WindowEvent::Moved(position) => {
            let _ = app.emit_to(LABEL, "desktop-lyrics-moved", [position.x, position.y]);
        }
        _ => {}
    });
    Ok(())
}

#[tauri::command]
pub async fn place_desktop_lyrics(
    window: WebviewWindow,
    vertical: bool,
    double: bool,
    saved: Option<[i32; 2]>,
) -> Result<[i32; 2], String> {
    if window.label() != LABEL {
        return Err("invalid window".into());
    }
    let main = window
        .get_webview_window("main")
        .ok_or("main window missing")?;
    let monitors = window.available_monitors().map_err(|e| e.to_string())?;
    let saved_monitor = saved.and_then(|[x, y]| {
        monitors.iter().find(|monitor| {
            let area = monitor.work_area();
            let dx = i64::from(x) - i64::from(area.position.x);
            let dy = i64::from(y) - i64::from(area.position.y);
            (0..i64::from(area.size.width)).contains(&dx)
                && (0..i64::from(area.size.height)).contains(&dy)
        })
    });
    let fallback = window
        .current_monitor()
        .ok()
        .flatten()
        .filter(|_| window.is_visible().unwrap_or(false))
        .or_else(|| main.current_monitor().ok().flatten())
        .or_else(|| main.primary_monitor().ok().flatten());
    let monitor = saved_monitor
        .or(fallback.as_ref())
        .ok_or("monitor not found")?;
    let area = monitor.work_area();
    let scale = monitor.scale_factor();
    let (w, h) = if vertical {
        (166.0, 475.0)
    } else {
        (682.0, if double { 162.0 } else { 122.0 })
    };
    let width = ((w * scale) as u32).min(area.size.width);
    let height = ((h * scale) as u32).min(area.size.height);
    let left = area.position.x;
    let top = area.position.y;
    let right = left + (area.size.width - width) as i32;
    let bottom = top + (area.size.height - height) as i32;
    let inset = (16.0 * scale) as i32;
    let [x, y] = if saved_monitor.is_some() {
        saved.unwrap()
    } else if vertical {
        [right - inset, top + (bottom - top) / 2]
    } else {
        [left + (right - left) / 2, bottom - (86.0 * scale) as i32]
    };
    let (x, y) = (x.clamp(left, right), y.clamp(top, bottom));
    window
        .set_size(PhysicalSize::new(width, height))
        .map_err(|e| e.to_string())?;
    window
        .set_position(PhysicalPosition::new(x, y))
        .map_err(|e| e.to_string())?;
    Ok([x, y])
}

#[tauri::command]
pub async fn show_desktop_lyrics(window: WebviewWindow) -> Result<(), String> {
    if window.label() != LABEL {
        return Err("invalid window".into());
    }
    window.show().map_err(|e| e.to_string())?;
    window
        .emit_to("main", VISIBILITY, true)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn close_desktop_lyrics(window: WebviewWindow) -> Result<(), String> {
    if window.label() != LABEL {
        return Err("invalid window".into());
    }
    window.destroy().map_err(|e| e.to_string())
}
