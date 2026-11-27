//! 下载独立解析，探查和写入前取链使用同一原生优先流程；没有播放会话。
use crate::{
    download_media, fallback,
    provider::{self, common, Media},
};
use serde_json::Value;
use std::time::Duration;

pub struct Resolved {
    pub media: Media,
    pub representation: Value,
    pub route: String,
}
pub async fn probe(client: &reqwest::Client, media: &Media) -> Result<Value, String> {
    let limit = download_media::PREFIX_BYTES;
    let mut response = client
        .get(&media.url)
        .headers(media.headers.clone())
        .header("Range", format!("bytes=0-{}", limit - 1))
        .header("Accept-Encoding", "identity")
        .send()
        .await
        .map_err(|_| "upstream_failure")?;
    if matches!(response.status().as_u16(), 401 | 403) {
        return Err("access_denied".into());
    }
    if !matches!(response.status().as_u16(), 200 | 206)
        || response
            .headers()
            .get("content-encoding")
            .is_some_and(|v| v != "identity")
    {
        return Err("upstream_invalid_response".into());
    }
    let size = if response.status() == 206 {
        let range = response
            .headers()
            .get("content-range")
            .and_then(|v| v.to_str().ok())
            .ok_or("upstream_invalid_response")?;
        if !range.starts_with("bytes 0-") {
            return Err("upstream_invalid_response".into());
        }
        range.split('/').nth(1).and_then(|s| s.parse().ok())
    } else {
        response.content_length()
    };
    let mut bytes = Vec::new();
    while bytes.len() < limit {
        let Some(chunk) = response.chunk().await.map_err(|_| "upstream_failure")? else {
            break;
        };
        bytes.extend_from_slice(&chunk[..chunk.len().min(limit - bytes.len())]);
    }
    download_media::prefix(bytes, size)
}
pub async fn resolve(
    client: &reqwest::Client,
    config: &fallback::Config,
    identity: &Value,
    quality: &str,
    title: &str,
    artist: &str,
) -> Result<Resolved, String> {
    let source = identity["providerId"].as_str().ok_or("invalid_input")?;
    let id = identity["platformId"].as_str().ok_or("invalid_input")?;
    let native = async {
        if source == "netease" {
            let url = provider::netease::resolve_quality(client, id, quality).await?;
            common::validate_media(source, &url)?;
            Ok((
                Media {
                    url,
                    headers: reqwest::header::HeaderMap::new(),
                },
                None,
            ))
        } else if source == "migu" {
            let (url, duration) = provider::migu::resolve_download(client, id, quality).await?;
            common::validate_media(source, &url)?;
            Ok((
                Media {
                    url,
                    headers: reqwest::header::HeaderMap::new(),
                },
                Some(duration),
            ))
        } else {
            provider::resolve(client, identity)
                .await
                .map(|media| (media, None))
        }
    };
    let checked_native = async {
        let (media, duration) = native.await?;
        let mut representation = probe(client, &media).await?;
        if let Some(duration) = duration {
            representation["expectedDurationSeconds"] = serde_json::json!(duration);
        }
        if !download_media::satisfies(&representation, quality) {
            return Err("media_unavailable".to_string());
        }
        Ok(Resolved {
            media,
            representation,
            route: "native".into(),
        })
    };
    select(
        checked_native,
        &config.routes(source, id),
        |route| async move {
            let media = backup(client, source, id, &route, quality, title, artist).await?;
            let representation = probe(client, &media).await?;
            if !download_media::satisfies(&representation, quality) {
                return Err("media_unavailable".to_string());
            }
            Ok(Resolved {
                media,
                representation,
                route,
            })
        },
    )
    .await
}
// 探查、正式保存和重试都通过这个原生优先策略；失败结果不会产生文件。
async fn select<T, N, B, F>(native: N, routes: &[String], mut backup: B) -> Result<T, String>
where
    N: std::future::Future<Output = Result<T, String>>,
    B: FnMut(String) -> F,
    F: std::future::Future<Output = Result<T, String>>,
{
    let mut last = match native.await {
        Ok(value) => return Ok(value),
        Err(e) if !fallback::may_try_another_route(&e) => return Err(e),
        Err(e) => e,
    };
    for route in routes {
        match tokio::time::timeout(Duration::from_secs(10), backup(route.clone())).await {
            Ok(Ok(value)) => return Ok(value),
            Ok(Err(e)) if !fallback::may_try_another_route(&e) => return Err(e),
            Ok(Err(e)) => last = e,
            Err(_) => last = "upstream_timeout".into(),
        }
    }
    Err(last)
}

async fn backup(
    client: &reqwest::Client,
    source: &str,
    id: &str,
    route: &str,
    quality: &str,
    title: &str,
    artist: &str,
) -> Result<Media, String> {
    let request = match route {
        "vkeys" => client
            .get("https://api.vkeys.cn/music/tencent/song/link")
            .query(&[
                ("mid", id),
                (
                    "quality",
                    match quality {
                        "standard" => "4",
                        "high" => "8",
                        "lossless" => "10",
                        _ => "14",
                    },
                ),
            ]),
        "tang" => client
            .get("https://tang.api.s01s.cn/music_open_api.php")
            .query(&[("mid", id)]),
        "xunhuisi" => client
            .get("https://api.xunhuisi.store/API/QQMusic/Song.php")
            .query(&[("mid", id), ("type", "json")]),
        "gdstudio-preview" => client
            .get("https://music-api.gdstudio.xyz/api.php")
            .query(&[
                ("types", "url"),
                ("source", "netease"),
                ("id", id),
                (
                    "br",
                    match quality {
                        "standard" => "128",
                        "high" => "320",
                        _ => "999",
                    },
                ),
            ]),
        "jfjt" => client
            .post("https://dm.jfjt.cc/Song_V1")
            .header("Referer", "https://dm.jfjt.cc/")
            .form(&[
                ("url", id),
                (
                    "level",
                    match quality {
                        "high" => "exhigh",
                        "lossless" => "lossless",
                        _ => "standard",
                    },
                ),
                ("type", "json"),
            ]),
        _ => return Err("capability_unsupported".into()),
    };
    let response = request.send().await.map_err(|_| "upstream_failure")?;
    if response.status() == 403
        && response
            .headers()
            .get("cf-mitigated")
            .is_some_and(|v| v == "challenge")
    {
        return Err("upstream_failure".into());
    }
    if matches!(response.status().as_u16(), 401 | 403) {
        return Err("access_denied".into());
    }
    if response.status() != 200 {
        return Err("upstream_failure".into());
    }
    let data: Value = read_json(response).await?;
    let url = parse(source, route, id, &data, title, artist)?;
    Ok(Media {
        url,
        headers: reqwest::header::HeaderMap::new(),
    })
}
pub fn parse(
    source: &str,
    route: &str,
    id: &str,
    data: &Value,
    title: &str,
    artist: &str,
) -> Result<String, String> {
    fallback::permitted(data)?;
    let payload = if matches!(route, "vkeys" | "jfjt") {
        &data["data"]
    } else {
        data
    };
    fallback::permitted(payload)?;
    if route == "jfjt" && data["success"] != true {
        return Err("upstream_failure".into());
    }
    let echoed = if source == "qq" {
        payload.get("song_mid").or(payload.get("mid"))
    } else {
        payload.get("id")
    };
    if echoed.is_some_and(|v| common::id(v).as_deref() != Some(id)) {
        return Err("source_verification_failed".into());
    }
    // 与 Python 启动配置一致，允许精确 ID 请求绑定；有回显时必须匹配，另核对版本元数据和整文件时长。
    if matches!(route, "tang" | "xunhuisi" | "jfjt") {
        let (name, singer) = match route {
            "tang" => (&payload["song_name"], &payload["singer_name"]),
            "xunhuisi" => (&payload["title"], &payload["singer"]),
            _ => (&payload["name"], &payload["ar_name"]),
        };
        let names_match = name.as_str().is_some_and(|s| {
            s.split_whitespace().collect::<String>().to_lowercase()
                == title.split_whitespace().collect::<String>().to_lowercase()
        });
        let split_artists = |s: &str| {
            s.split(['/', ',', '、', '，', '&', ';'])
                .map(|p| p.trim().to_lowercase())
                .filter(|p| !p.is_empty())
                .collect::<std::collections::HashSet<_>>()
        };
        let actual = split_artists(singer.as_str().unwrap_or(""));
        let expected = split_artists(artist);
        if !names_match || actual.is_empty() || !actual.is_subset(&expected) {
            return Err("source_verification_failed".into());
        }
        if route == "xunhuisi" {
            if let Some(link) = payload.get("link").filter(|v| !v.is_null()) {
                let url = reqwest::Url::parse(link.as_str().ok_or("source_verification_failed")?)
                    .map_err(|_| "source_verification_failed")?;
                if url.host_str() != Some("y.qq.com")
                    || url.path() != format!("/n/ryqq/songDetail/{id}")
                {
                    return Err("source_verification_failed".into());
                }
            }
        }
        if route == "tang" && echoed.is_none() {
            return Err("source_verification_failed".into());
        }
    }
    let url = match route {
        "tang" => [
            "song_play_url_sq",
            "song_play_url_pq",
            "song_play_url_hq",
            "song_play_url",
            "song_play_url_standard",
            "song_play_url_fq",
        ]
        .iter()
        .find_map(|k| payload[*k].as_str().filter(|s| !s.is_empty())),
        "xunhuisi" => payload["music_url"].as_str(),
        _ => payload["url"].as_str(),
    }
    .filter(|s| !s.is_empty())
    .ok_or("media_unavailable")?;
    common::validate_media(source, url)?;
    Ok(url.into())
}

async fn read_json(mut response: reqwest::Response) -> Result<Value, String> {
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| "upstream_failure")? {
        if bytes.len() + chunk.len() > 2 * 1024 * 1024 {
            return Err("upstream_invalid_response".into());
        }
        bytes.extend_from_slice(&chunk);
    }
    serde_json::from_slice(&bytes).map_err(|_| "upstream_invalid_response".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[tokio::test]
    async fn native_success_and_denial_never_call_backup() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        let calls = AtomicUsize::new(0);
        for native in [Ok(1), Err("access_denied".into())] {
            let result = select(async { native }, &["backup".into()], |_| {
                calls.fetch_add(1, Ordering::SeqCst);
                async { Ok(2) }
            })
            .await;
            assert_eq!(calls.load(Ordering::SeqCst), 0);
            if let Ok(value) = result {
                assert_eq!(value, 1);
            }
        }
        let failed = select(
            async { Err::<u8, _>("media_unavailable".into()) },
            &["backup".into()],
            |_| async { Err("source_verification_failed".into()) },
        )
        .await;
        assert!(failed.is_err());
    }
    #[test]
    fn identities_permissions_and_versions() {
        let url = "https://isure.stream.qqmusic.qq.com/test.mp3";
        assert!(parse(
            "qq",
            "vkeys",
            "abc",
            &json!({"data":{"mid":"wrong","url":url}}),
            "歌",
            "人"
        )
        .is_err());
        assert!(parse(
            "qq",
            "vkeys",
            "abc",
            &json!({"data":{"url":url}}),
            "歌",
            "人"
        )
        .is_ok());
        assert!(parse(
            "qq",
            "vkeys",
            "abc",
            &json!({"data":{"url":url,"freeTrialInfo":{}}}),
            "歌",
            "人"
        )
        .is_err());
        assert!(parse("qq","tang","abc",&json!({"song_mid":"abc","song_name":"另一个版本","singer_name":"人","song_play_url":url}),"歌","人").is_err());
    }
    #[tokio::test]
    #[ignore = "Tang整文件诊断；不发布成品"]
    async fn live_tang_full_check() {
        use tokio::io::AsyncWriteExt;
        let client = reqwest::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .read_timeout(Duration::from_secs(20))
            .build()
            .unwrap();
        let media = backup(
            &client,
            "qq",
            "0027oMO61wWi55",
            "tang",
            "lossless",
            "发如雪",
            "周杰伦",
        )
        .await
        .unwrap();
        let mut response = client.get(media.url).send().await.unwrap();
        assert_eq!(response.status(), 200);
        let dir = std::env::current_dir().unwrap().join(".runtime");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join(format!("tang-diagnostic-{}.part", uuid::Uuid::new_v4()));
        let mut file = tokio::fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&path)
            .await
            .unwrap();
        while let Some(chunk) = response.chunk().await.unwrap() {
            file.write_all(&chunk).await.unwrap();
        }
        drop(file);
        let result = crate::download_media::inspect(&path, 299.0, "lossless");
        println!("tang full validation: {result:?}");
        std::fs::remove_file(path).unwrap();
    }
    #[tokio::test]
    #[ignore = "单独路线探查，不作为整文件保存成功"]
    async fn live_individual_routes() {
        let client = reqwest::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .read_timeout(Duration::from_secs(10))
            .build()
            .unwrap();
        for (source, id, title, artist, route, quality) in [
            ("qq", "0027oMO61wWi55", "发如雪", "周杰伦", "vkeys", "high"),
            (
                "qq",
                "0027oMO61wWi55",
                "发如雪",
                "周杰伦",
                "tang",
                "lossless",
            ),
            (
                "qq",
                "0027oMO61wWi55",
                "发如雪",
                "周杰伦",
                "xunhuisi",
                "standard",
            ),
            (
                "netease",
                "2668397359",
                "晴天 (原唱 周杰伦)",
                "RyaVocal",
                "gdstudio-preview",
                "lossless",
            ),
            (
                "netease",
                "2668397359",
                "晴天 (原唱 周杰伦)",
                "RyaVocal",
                "jfjt",
                "lossless",
            ),
        ] {
            let result = tokio::time::timeout(Duration::from_secs(15), async {
                let media = backup(&client, source, id, route, quality, title, artist).await?;
                probe(&client, &media).await
            })
            .await;
            println!("{source}/{id} {route} {quality}: {result:?}");
        }
    }
    #[tokio::test]
    #[ignore = "真实下载探查，诊断只包含来源身份、品质和路线"]
    async fn live_probes() {
        let client = reqwest::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .connect_timeout(Duration::from_secs(6))
            .read_timeout(Duration::from_secs(12))
            .build()
            .unwrap();
        for (source, id, title, artist) in [
            ("qq", "0027oMO61wWi55", "发如雪", "周杰伦"),
            ("netease", "2668397359", "晴天", "周杰伦"),
            ("migu", "600913000007163534", "晴天", "周杰伦"),
        ] {
            for quality in ["standard", "high", "lossless"] {
                for (label, config) in [
                    ("native", fallback::Config { routes: vec![] }),
                    ("default", fallback::Config::default()),
                ] {
                    let result = tokio::time::timeout(
                        Duration::from_secs(48),
                        resolve(
                            &client,
                            &config,
                            &json!({"providerId":source,"platformId":id}),
                            quality,
                            title,
                            artist,
                        ),
                    )
                    .await;
                    match result {
                        Ok(Ok(r)) => println!(
                            "{source}/{id} {quality} {label}: {} {}",
                            r.route, r.representation
                        ),
                        Ok(Err(e)) => println!("{source}/{id} {quality} {label}: {e}"),
                        Err(_) => println!("{source}/{id} {quality} {label}: timeout"),
                    }
                }
            }
        }
    }
}
