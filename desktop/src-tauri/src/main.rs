#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod provider;
mod sessions;
mod transport;
use serde_json::{json, Value};
use tauri::Manager;

struct Desktop {
    sessions: sessions::Sessions,
    client: reqwest::Client,
    port: u16,
}

#[tauri::command]
async fn desktop_request(
    path: String,
    body: Value,
    state: tauri::State<'_, Desktop>,
) -> Result<Value, String> {
    match path.as_str() {
        "/api/providers" => Ok(provider::catalog()),
        "/api/search" => provider::search(&state.client, &body).await,
        "/api/playback/open" => {
            let identity = &body["identity"];
            let media = provider::resolve(&state.client, identity).await?;
            let id = state.sessions.insert_media(media);
            let now = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_millis() as u64;
            Ok(
                json!({"playbackId":id,"streamUrl":format!("http://127.0.0.1:{}/api/playback/{}/stream",state.port,id),
                "expiresInSeconds":120,"media":{"id":id,"identity":identity,"protocol":"progressive",
                "representation":{},"resolvedAt":now,"validUntil":null}}),
            )
        }
        _ => {
            let parts: Vec<_> = path.split('/').collect();
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
            Err("此功能尚未迁移到桌面版（歌词、下载、本机音乐库及目录管理暂不可用）".into())
        }
    }
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let sessions = sessions::Sessions::new();
            let client = reqwest::Client::builder()
                .user_agent("Mozilla/5.0")
                .referer(false)
                .redirect(reqwest::redirect::Policy::none())
                .connect_timeout(std::time::Duration::from_secs(10))
                .read_timeout(std::time::Duration::from_secs(30))
                .build()?;
            let port = tauri::async_runtime::block_on(transport::start(transport::Transport {
                sessions: sessions.clone(),
                client: client.clone(),
            }))?;
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
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![desktop_request])
        .build(tauri::generate_context!())
        .expect("桌面应用初始化失败")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::Exit) {
                app.state::<Desktop>().sessions.close_all();
            }
        });
}
