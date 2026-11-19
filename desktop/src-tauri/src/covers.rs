use axum::{
    body::Body,
    extract::{Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::get,
    Router,
};
use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
use tokio::sync::OnceCell;
type ImageResult = Result<(Vec<u8>, String), String>;
struct Entry {
    url: String,
    created: Instant,
    image: OnceCell<ImageResult>,
}
#[derive(Clone, Default)]
pub struct Covers(Arc<Mutex<HashMap<String, Arc<Entry>>>>);

pub fn valid_url(source: &str, value: &str) -> bool {
    let Ok(url) = reqwest::Url::parse(value) else {
        return false;
    };
    if !matches!(url.scheme(), "http" | "https")
        || !url.username().is_empty()
        || url.password().is_some()
        || url.port().is_some()
        || url.fragment().is_some()
    {
        return false;
    }
    let host = url.host_str().unwrap_or("");
    let path = url.path();
    let image = [".jpg", ".jpeg", ".png", ".webp"]
        .iter()
        .any(|ext| path.to_lowercase().ends_with(ext));
    match source {
        "qq" => {
            image
                && host == "y.gtimg.cn"
                && url.scheme() == "https"
                && regex::Regex::new(r"^/music/photo_new/T002R500x500M000[A-Za-z0-9]{1,64}\.jpg$")
                    .unwrap()
                    .is_match(path)
                && url.query().is_none()
        }
        "netease" => {
            image
                && regex::Regex::new(r"^p[0-9]+\.music\.126\.net$")
                    .unwrap()
                    .is_match(host)
        }
        "kuwo" => image && host.ends_with(".kuwo.cn"),
        "migu" => {
            host == "d.musicapp.migu.cn"
                && ((image && path.starts_with("/data/oss/resource/"))
                    || regex::Regex::new(
                        r"^/data/resource-service/file-down/[A-Za-z0-9/_-]{1,256}$",
                    )
                    .unwrap()
                    .is_match(path))
        }
        _ => false,
    }
}
fn display_url(source: &str, url: &str) -> Option<reqwest::Url> {
    if !valid_url(source, url) {
        return None;
    }
    // 老搜索响应中的 HTTP 封面统一通过同一已确认 CDN 的 HTTPS 请求。
    let mut parsed = reqwest::Url::parse(url).ok()?;
    parsed.set_scheme("https").ok()?;
    // 网易云原图可能超过代理的 2 MiB 限制。搜索和播放器共用 500px 缩略图。
    if source == "netease" {
        let query: Vec<_> = parsed
            .query_pairs()
            .filter(|(key, _)| key != "param")
            .into_iter()
            .map(|(k, v)| (k.into_owned(), v.into_owned()))
            .collect();
        parsed.set_query(None);
        parsed
            .query_pairs_mut()
            .extend_pairs(query)
            .append_pair("param", "500y500");
    }
    Some(parsed)
}
impl Covers {
    pub fn register(&self, source: &str, url: &str, port: u16) -> Option<String> {
        let parsed = display_url(source, url)?;
        let url = parsed.as_str();
        let mut entries = self.0.lock().unwrap();
        entries.retain(|_, entry| entry.created.elapsed() < Duration::from_secs(3600));
        if let Some((id, _)) = entries.iter().find(|(_, entry)| entry.url == url) {
            return Some(format!("http://127.0.0.1:{port}/covers/{id}"));
        }
        if entries.len() >= 128 {
            if let Some(id) = entries
                .iter()
                .min_by_key(|(_, e)| e.created)
                .map(|(id, _)| id.clone())
            {
                entries.remove(&id);
            }
        }
        let id = uuid::Uuid::new_v4().simple().to_string();
        entries.insert(
            id.clone(),
            Arc::new(Entry {
                url: url.into(),
                created: Instant::now(),
                image: OnceCell::new(),
            }),
        );
        Some(format!("http://127.0.0.1:{port}/covers/{id}"))
    }
    pub fn register_palette(&self, url: &str, port: u16) -> Option<String> {
        if url.len() > 2048 || !url.starts_with("https://") {
            return None;
        }
        ["qq", "netease", "kuwo", "migu"]
            .iter()
            .find_map(|source| self.register(source, url, port))
    }
    pub fn map_page(page: &mut serde_json::Value) {
        if let Some(items) = page["items"].as_array_mut() {
            for item in items {
                let cover = item["cover"].as_str().and_then(|url| {
                    display_url(item["identity"]["providerId"].as_str().unwrap_or(""), url)
                });
                item["cover"] = serde_json::json!(cover.map(|url| url.to_string()));
            }
        }
    }
    pub fn router(self) -> Router {
        Router::new()
            .route("/covers/{id}", get(serve))
            .with_state(self)
    }
}
pub fn image_type(bytes: &[u8]) -> Option<&'static str> {
    if bytes.starts_with(&[255, 216, 255]) {
        Some("image/jpeg")
    } else if bytes.starts_with(b"\x89PNG\r\n\x1a\n") {
        Some("image/png")
    } else if bytes.starts_with(b"RIFF") && bytes.get(8..12) == Some(b"WEBP") {
        Some("image/webp")
    } else {
        None
    }
}
async fn read(url: &str) -> ImageResult {
    let client = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(8))
        .build()
        .map_err(|_| "封面请求失败")?;
    let mut response = client
        .get(url)
        .header("Accept-Encoding", "identity")
        .send()
        .await
        .map_err(|_| "封面请求失败")?;
    if response.status() != 200
        || response
            .content_length()
            .is_some_and(|n| n > 2 * 1024 * 1024)
    {
        return Err("封面响应无效或过大".into());
    }
    let mime = response
        .headers()
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .split(';')
        .next()
        .unwrap_or("")
        .to_owned();
    // 咪咕已确认的 file-down 图片端点用通用 MIME；仍须通过下方图片文件头检查。
    let migu_binary = reqwest::Url::parse(url).is_ok_and(|u| {
        u.host_str() == Some("d.musicapp.migu.cn")
            && u.path().starts_with("/data/resource-service/file-down/")
    }) && mime == "application/octet-stream";
    if !["image/jpeg", "image/jpg", "image/png", "image/webp"].contains(&mime.as_str())
        && !migu_binary
    {
        return Err("封面格式不支持".into());
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| "封面读取失败")? {
        if bytes.len() + chunk.len() > 2 * 1024 * 1024 {
            return Err("封面过大".into());
        }
        bytes.extend_from_slice(&chunk);
    }
    let kind = image_type(&bytes).ok_or("封面格式无效")?.to_owned();
    Ok((bytes, kind))
}
async fn serve(State(covers): State<Covers>, Path(id): Path<String>) -> Response {
    let entry = covers.0.lock().unwrap().get(&id).cloned();
    let Some(entry) = entry else {
        return StatusCode::NOT_FOUND.into_response();
    };
    if entry.created.elapsed() > Duration::from_secs(3600) {
        return StatusCode::GONE.into_response();
    }
    match entry.image.get_or_init(|| read(&entry.url)).await {
        Ok((bytes, kind)) => Response::builder()
            .header("Content-Type", kind)
            .header("Access-Control-Allow-Origin", "*")
            .header("Cache-Control", "private, max-age=3600")
            .header("X-Content-Type-Options", "nosniff")
            .body(Body::from(bytes.clone()))
            .unwrap(),
        Err(_) => StatusCode::BAD_GATEWAY.into_response(),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bounded_registered_images_and_dedup() {
        let covers = Covers::default();
        let url = "https://y.gtimg.cn/music/photo_new/T002R500x500M0000024bjiL2aocxT.jpg";
        assert_eq!(
            covers.register("qq", url, 1234),
            covers.register("qq", url, 1234)
        );
        assert!(covers
            .register("qq", "https://127.0.0.1/private.jpg", 1234)
            .is_none());
        assert!(covers
            .register("qq", "https://y.gtimg.cn/other.jpg", 1234)
            .is_none());
        assert_eq!(image_type(b"<html>"), None);
        assert_eq!(image_type(b"\xff\xd8\xffimage"), Some("image/jpeg"));
    }
    #[test]
    fn netease_registers_bounded_thumbnail() {
        let covers = Covers::default();
        let url = "http://p2.music.126.net/KTo5oSxH3CPA5PBTeFKDyA==/109951164581432409.jpg";
        assert!(covers.register("netease", url, 1234).is_some());
        let entries = covers.0.lock().unwrap();
        assert_eq!(
            entries.values().next().unwrap().url,
            format!("{}?param=500y500", url.replacen("http:", "https:", 1))
        );
    }
    #[test]
    fn search_keeps_cdn_addresses_without_registering_them() {
        let covers = Covers::default();
        let qq = "https://y.gtimg.cn/music/photo_new/T002R500x500M000000lqMaM0HR7AF.jpg";
        let mut page = serde_json::json!({"items":[
            {"identity":{"providerId":"qq"},"cover":qq},
            {"identity":{"providerId":"netease"},"cover":"http://p2.music.126.net/a.jpg?param=100y100"},
            {"identity":{"providerId":"qq"},"cover":null},
            {"identity":{"providerId":"qq"},"cover":"https://evil.example/a.jpg"}
        ]});
        Covers::map_page(&mut page);
        assert_eq!(page["items"][0]["cover"], qq);
        assert_eq!(
            page["items"][1]["cover"],
            "https://p2.music.126.net/a.jpg?param=500y500"
        );
        assert!(page["items"][2]["cover"].is_null());
        assert!(page["items"][3]["cover"].is_null());
        assert!(covers.0.lock().unwrap().is_empty());
        assert!(covers
            .register_palette("https://evil.example/a.jpg", 1234)
            .is_none());
        assert!(covers
            .register_palette(qq, 1234)
            .unwrap()
            .starts_with("http://127.0.0.1:1234/covers/"));
    }
    #[tokio::test]
    async fn cached_image_reads_share_one_upstream_request() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        let count = Arc::new(AtomicUsize::new(0));
        let calls = count.clone();
        let upstream = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = upstream.local_addr().unwrap();
        tokio::spawn(async move {
            axum::serve(
                upstream,
                Router::new().route(
                    "/image",
                    get(move || {
                        let calls = calls.clone();
                        async move {
                            calls.fetch_add(1, Ordering::SeqCst);
                            ([("content-type", "image/jpeg")], vec![255u8, 216, 255, 0])
                        }
                    }),
                ),
            )
            .await
            .unwrap();
        });
        let covers = Covers::default();
        // 仅测试模块直接注入本地夹具，生产入口仍必须经过 register 的域名校验。
        covers.0.lock().unwrap().insert(
            "fixture".into(),
            Arc::new(Entry {
                url: format!("http://{addr}/image"),
                created: Instant::now(),
                image: OnceCell::new(),
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            axum::serve(listener, covers.router()).await.unwrap();
        });
        let client = reqwest::Client::new();
        let url = format!("http://{addr}/covers/fixture");
        let (a, b) = tokio::join!(client.get(&url).send(), client.get(&url).send());
        assert_eq!(a.unwrap().status(), 200);
        assert_eq!(b.unwrap().headers()["access-control-allow-origin"], "*");
        assert_eq!(count.load(Ordering::SeqCst), 1);
        assert_eq!(
            client
                .get(format!("http://{addr}/covers/unknown"))
                .send()
                .await
                .unwrap()
                .status(),
            404
        );
    }
}
