use crate::provider::{common, Media};
use serde::Deserialize;
use serde_json::Value;
use std::{collections::HashSet, future::Future, time::Duration};

// 原生始终由 choose 先执行；此处只集中维护备用顺序和支持的路线名。
const DEFAULT_ROUTES: &[(&str, &[&str])] = &[
    ("qq", &["vkeys", "tang", "xunhuisi"]),
    ("netease", &["gdstudio-preview", "jfjt"]),
];

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    #[serde(default)]
    pub routes: Vec<Grant>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Grant {
    pub provider: String,
    pub route: String,
    #[serde(default)]
    pub tracks: Option<Vec<String>>,
    #[serde(default)]
    allow_request_bound: bool,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            routes: DEFAULT_ROUTES
                .iter()
                .flat_map(|(source, routes)| {
                    routes.iter().map(|route| Grant {
                        provider: (*source).into(),
                        route: (*route).into(),
                        tracks: None,
                        allow_request_bound: false,
                    })
                })
                .collect(),
        }
    }
}

impl Config {
    pub fn from_env() -> Result<Self, String> {
        match std::env::var("MUSIC_CORE_DESKTOP_FALLBACKS") {
            Ok(raw) => Self::parse(&raw),
            Err(std::env::VarError::NotPresent) => Ok(Self::default()),
            Err(_) => Err("桌面备用路线配置编码无效".into()),
        }
    }
    pub fn parse(raw: &str) -> Result<Self, String> {
        if raw.len() > 65536 {
            return Err("备用路线配置过大".into());
        }
        let config: Self = serde_json::from_str(raw).map_err(|_| "备用路线配置格式无效")?;
        let mut seen = HashSet::new();
        for grant in &config.routes {
            let allowed = DEFAULT_ROUTES
                .iter()
                .find(|(source, _)| *source == grant.provider)
                .map(|(_, routes)| *routes)
                .unwrap_or(&[]);
            if !allowed.contains(&grant.route.as_str())
                || (grant.allow_request_bound
                    && (grant.provider != "qq" || grant.route != "xunhuisi"))
                || !seen.insert((&grant.provider, &grant.route))
                || grant.tracks.as_ref().is_some_and(|tracks| {
                    tracks
                        .iter()
                        .any(|id| !common::valid_id(&grant.provider, id))
                })
            {
                return Err("备用路线名称、重复项或曲目范围无效".into());
            }
        }
        Ok(config)
    }
    pub(crate) fn routes(&self, source: &str, id: &str) -> Vec<String> {
        self.routes
            .iter()
            .filter(|g| {
                g.provider == source
                    && g.tracks
                        .as_ref()
                        .is_none_or(|tracks| tracks.iter().any(|t| t == id))
            })
            .map(|g| g.route.clone())
            .collect()
    }
}

// 只有可判定的临时失败才有机会换路线，未知故障按终止处理。
pub(crate) fn may_try_another_route(error: &str) -> bool {
    matches!(error,
        "anonymous_media_unavailable" | "media_unavailable" | "upstream_failure"
        | "upstream_timeout" | "upstream_invalid_response" | "upstream_rate_limited"
        | "source_verification_failed" | "untrusted_media" | "provider_context_rejected"
    )
}

pub async fn choose<T, N, NF, B, BF>(
    native: N,
    routes: &[String],
    mut backup: B,
) -> Result<(T, String), String>
where
    N: FnOnce() -> NF,
    NF: Future<Output = Result<T, String>>,
    B: FnMut(String) -> BF,
    BF: Future<Output = Result<T, String>>,
{
    let mut last = match native().await {
        Ok(media) => return Ok((media, "native".into())),
        Err(error) if error == "anonymous_media_unavailable" => error,
        Err(error) => return Err(error),
    };
    for route in routes {
        match tokio::time::timeout(Duration::from_secs(7), backup(route.clone())).await {
            Ok(Ok(media)) => return Ok((media, route.clone())),
            Ok(Err(error)) => {
                // 无法校验的结果只淘汰当前路线；明确限制不能换服务继续。
                if !may_try_another_route(&error) {
                    return Err(error);
                }
                last = error;
            }
            Err(_) => last = "upstream_timeout".into(),
        }
    }
    Err(last)
}

pub async fn resolve(
    client: &reqwest::Client,
    config: &Config,
    identity: &Value,
) -> Result<(Media, String, IdentityEvidence), String> {
    let source = identity["providerId"].as_str().ok_or("invalid_input")?;
    let id = identity["platformId"].as_str().ok_or("invalid_input")?;
    let routes = config.routes(source, id);
    let ((media, evidence), route) = tokio::time::timeout(
        Duration::from_secs(28),
        choose(
            || async {
                crate::provider::resolve(client, identity)
                    .await
                    .map(|media| (media, IdentityEvidence::Native))
            },
            &routes,
            |route| async move {
                // 只有实际进入备用路线才创建无凭据客户端。
                let external = reqwest::Client::builder()
                    .user_agent("Mozilla/5.0")
                    .redirect(reqwest::redirect::Policy::none())
                    .connect_timeout(Duration::from_secs(4))
                    .build()
                    .map_err(|_| "upstream_failure")?;
                let allow_request_bound = config.routes.iter().any(|grant| {
                    grant.provider == source && grant.route == route && grant.allow_request_bound
                });
                backup(&external, source, id, &route, allow_request_bound).await
            },
        ),
    )
    .await
    .map_err(|_| "upstream_timeout")??;
    Ok((media, route, evidence))
}

pub(crate) fn permitted(data: &Value) -> Result<(), String> {
    for field in ["code", "status"] {
        if matches!(data[field].as_i64(), Some(301 | 401 | 403))
            || matches!(data[field].as_str(), Some("301" | "401" | "403"))
        {
            return Err("access_denied".into());
        }
    }
    if data.get("code").is_some_and(|code| {
        !code.is_null()
            && !matches!(code.as_i64(), Some(0 | 200))
            && !matches!(code.as_str(), Some("0" | "200"))
    }) {
        return Err("upstream_failure".into());
    }
    for field in [
        "freeTrialInfo",
        "freeListenType",
        "drm",
        "encrypted",
        "requiresLogin",
        "requiresPayment",
        "regionBlocked",
    ] {
        if data
            .get(field)
            .is_some_and(|v| !v.is_null() && v != false && v != 0 && v != "0")
        {
            return Err("access_denied".into());
        }
    }
    Ok(())
}

// vkeys 使用区分大小写的 songMID。多个身份字段必须相互一致。
pub(crate) fn response_identity_matches(
    source: &str,
    route: &str,
    payload: &Value,
    id: &str,
) -> Result<bool, String> {
    let fields: &[&str] = match (source, route) {
        ("qq", "vkeys") => &["songMID", "song_mid", "mid"],
        ("qq", _) => &["song_mid", "mid"],
        _ => &["id"],
    };
    let mut present = false;
    for value in fields.iter().filter_map(|field| payload.get(*field)) {
        if common::id(value).as_deref() != Some(id) {
            return Err("source_verification_failed".into());
        }
        present = true;
    }
    Ok(present)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum IdentityEvidence {
    Native,
    Confirmed,
    RequestBound,
}

fn xunhuisi_evidence(
    payload: &Value,
    id: &str,
    allow_request_bound: bool,
) -> Result<IdentityEvidence, String> {
    let mut confirmed = false;
    for value in ["songMID", "song_mid", "mid"]
        .iter()
        .filter_map(|field| payload.get(*field))
    {
        if value.as_str() != Some(id) {
            return Err("source_verification_failed".into());
        }
        confirmed = true;
    }
    let invalid = "source_verification_failed";
    if let Some(link) = payload.get("link").filter(|v| !v.is_null()) {
        let url = reqwest::Url::parse(link.as_str().ok_or(invalid)?).map_err(|_| invalid)?;
        if url.scheme() != "https"
            || url.host_str() != Some("y.qq.com")
            || !url.username().is_empty()
            || url.password().is_some()
            || url.port().is_some()
            || url.path() != format!("/n/ryqq/songDetail/{id}")
        {
            return Err(invalid.into());
        }
    } else if !confirmed {
        return Err(invalid.into());
    }
    if confirmed {
        return Ok(IdentityEvidence::Confirmed);
    }
    if !allow_request_bound
        || ["title", "singer"].iter().any(|field| {
            !payload[*field]
                .as_str()
                .is_some_and(|value| !value.trim().is_empty())
        })
    {
        return Err(invalid.into());
    }
    Ok(IdentityEvidence::RequestBound)
}

fn parse(
    source: &str,
    route: &str,
    id: &str,
    data: &Value,
    allow_request_bound: bool,
) -> Result<(String, IdentityEvidence), String> {
    permitted(data)?;
    let payload = match route {
        "vkeys" | "jfjt" => &data["data"],
        _ => data,
    };
    permitted(payload)?;
    if route == "jfjt" && data["success"] != true {
        return Err("upstream_failure".into());
    }
    let is_xunhuisi = source == "qq" && route == "xunhuisi";
    let evidence = if is_xunhuisi {
        xunhuisi_evidence(payload, id, allow_request_bound)?
    } else if response_identity_matches(source, route, payload, id)? {
        IdentityEvidence::Confirmed
    } else {
        return Err("source_verification_failed".into());
    };
    let title = if is_xunhuisi {
        payload.get("title")
    } else {
        payload
            .get("song_name")
            .or(payload.get("title"))
            .or(payload.get("name"))
    };
    if let Some(title) = title.and_then(Value::as_str) {
        if ["伴奏", "伴唱", "翻唱", "live", "现场"]
            .iter()
            .any(|word| title.to_lowercase().contains(word))
        {
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
    Ok((url.into(), evidence))
}

async fn backup(
    client: &reqwest::Client,
    source: &str,
    id: &str,
    route: &str,
    allow_request_bound: bool,
) -> Result<(Media, IdentityEvidence), String> {
    let request = match route {
        "vkeys" => client
            .get("https://api.vkeys.cn/music/tencent/song/link")
            .query(&[("mid", id), ("quality", "14")]),
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
                ("id", id),
                ("source", "netease"),
                ("br", "999"),
            ]),
        "jfjt" => client
            .post("https://dm.jfjt.cc/Song_V1")
            .header("Referer", "https://dm.jfjt.cc/")
            .form(&[("url", id), ("level", "standard"), ("type", "json")]),
        _ => return Err("invalid_input".into()),
    };
    let data = common::json(request).await?;
    let (url, evidence) = parse(source, route, id, &data, allow_request_bound)?;
    probe(client, &url).await?;
    Ok((
        Media {
            url,
            headers: reqwest::header::HeaderMap::new(),
        },
        evidence,
    ))
}

async fn probe(client: &reqwest::Client, url: &str) -> Result<(), String> {
    let mut response = client
        .get(url)
        .header("Range", "bytes=0-4095")
        .header("Accept-Encoding", "identity")
        .send()
        .await
        .map_err(|_| "upstream_failure")?;
    if matches!(response.status().as_u16(), 401 | 403) {
        return Err("access_denied".into());
    }
    if !matches!(response.status().as_u16(), 200 | 206) {
        return Err("media_unavailable".into());
    }
    if response.status().as_u16() == 206
        && !response
            .headers()
            .get("content-range")
            .and_then(|v| v.to_str().ok())
            .is_some_and(|range| range.starts_with("bytes 0-") && range.contains('/'))
    {
        return Err("upstream_invalid_response".into());
    }
    let mime = response
        .headers()
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    if mime.contains("html") || mime.contains("json") {
        return Err("upstream_invalid_response".into());
    }
    let mut bytes = Vec::new();
    while bytes.len() < 4096 {
        let Some(chunk) = response.chunk().await.map_err(|_| "upstream_failure")? else {
            break;
        };
        bytes.extend_from_slice(&chunk[..chunk.len().min(4096 - bytes.len())]);
    }
    if bytes.starts_with(b"ID3")
        || bytes.starts_with(b"fLaC")
        || bytes.starts_with(b"OggS")
        || bytes.get(4..8) == Some(b"ftyp")
        || (bytes.len() > 1 && bytes[0] == 255 && bytes[1] & 224 == 224)
    {
        Ok(())
    } else {
        Err("upstream_invalid_response".into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };
    fn parse(source: &str, route: &str, id: &str, data: &Value) -> Result<String, String> {
        super::parse(source, route, id, data, false).map(|(url, _)| url)
    }
    #[test]
    fn xunhuisi_requires_scoped_permission_and_valid_metadata() {
        let id = "0039MnYb0qxYhV";
        let data = json!({"title":"晴天", "singer":"周杰伦",
            "link":format!("https://y.qq.com/n/ryqq/songDetail/{id}"),
            "music_url":"https://aqqmusic.tc.qq.com/fixture.m4a"});
        assert!(super::parse("qq", "xunhuisi", id, &data, false).is_err());
        assert_eq!(
            super::parse("qq", "xunhuisi", id, &data, true).unwrap().1,
            IdentityEvidence::RequestBound
        );
        let mut confirmed = data.clone();
        confirmed["song_mid"] = json!(id);
        assert_eq!(
            super::parse("qq", "xunhuisi", id, &confirmed, false)
                .unwrap()
                .1,
            IdentityEvidence::Confirmed
        );
        confirmed["songMID"] = json!("conflict");
        assert!(super::parse("qq", "xunhuisi", id, &confirmed, true).is_err());
        for (field, value) in [
            ("mid", json!("other")),
            ("mid", json!(null)),
            ("mid", json!(123)),
            ("title", json!("晴天 Live")),
            ("title", json!(false)),
            ("singer", json!("  ")),
            ("link", json!(null)),
            ("link", json!("https://y.qq.com/n/ryqq/songDetail/other")),
            ("music_url", json!("https://example.invalid/fixture.m4a")),
        ] {
            let mut invalid = data.clone();
            invalid[field] = value;
            assert!(
                super::parse("qq", "xunhuisi", id, &invalid, true).is_err(),
                "{field}"
            );
        }
        for field in ["freeTrialInfo", "requiresLogin", "requiresPayment"] {
            let mut restricted = data.clone();
            restricted[field] = json!(true);
            assert_eq!(
                super::parse("qq", "xunhuisi", id, &restricted, true)
                    .err()
                    .as_deref(),
                Some("access_denied")
            );
        }
        assert!(super::parse(
            "qq",
            "tang",
            id,
            &json!({"song_play_url":data["music_url"]}),
            true
        )
        .is_err());
        assert!(super::parse(
            "qq",
            "vkeys",
            id,
            &json!({"data":{"url":data["music_url"]}}),
            true
        )
        .is_err());
        assert!(Config::parse(
            r#"{"routes":[{"provider":"qq","route":"vkeys","allow_request_bound":true}]}"#
        )
        .is_err());
        assert!(Config::parse(
            r#"{"routes":[{"provider":"qq","route":"xunhuisi","allow_request_bound":true}]}"#
        )
        .is_ok());
    }
    #[tokio::test]
    #[ignore = "真实 xunhuisi 诊断与回环播放验收"]
    async fn xunhuisi_real_playback() {
        let id = "0039MnYb0qxYhV";
        let client = reqwest::Client::builder()
            .user_agent("Mozilla/5.0")
            .redirect(reqwest::redirect::Policy::none())
            .timeout(Duration::from_secs(10))
            .build()
            .unwrap();
        let data = common::json(
            client
                .get("https://api.xunhuisi.store/API/QQMusic/Song.php")
                .query(&[("mid", id), ("type", "json")]),
        )
        .await
        .unwrap();
        println!("code={:?} fields={:?} title_matches={} singer_matches={} link_matches={} media_present={}",
            data["code"].as_i64(), data.as_object().unwrap().keys().collect::<Vec<_>>(),
            data["title"] == "晴天", data["singer"] == "周杰伦",
            data["link"] == format!("https://y.qq.com/n/ryqq/songDetail/{id}"), data["music_url"].is_string());
        assert_eq!(
            parse("qq", "xunhuisi", id, &data).err().as_deref(),
            Some("source_verification_failed")
        );
        println!("strict route rejected before media probe");
        let (media, evidence) = backup(&client, "qq", id, "xunhuisi", true)
            .await
            .unwrap_or_else(|error| panic!("xunhuisi playback probe: {error}"));
        assert_eq!(evidence, IdentityEvidence::RequestBound);
        println!("evidence={evidence:?}, trusted target and audio prefix verified");
        let sessions = crate::sessions::Sessions::new();
        let sid = sessions.insert_media(media);
        let port = crate::transport::start(crate::transport::Transport {
            sessions: sessions.clone(),
            client: client.clone(),
        })
        .await
        .unwrap();
        for (start, end) in [(0, 1023), (300000, 301023)] {
            let response = client
                .get(format!("http://127.0.0.1:{port}/api/playback/{sid}/stream"))
                .header("Range", format!("bytes={start}-{end}"))
                .send()
                .await
                .unwrap();
            assert_eq!(response.status(), 206);
            assert!(response.headers()["content-range"]
                .to_str()
                .unwrap()
                .starts_with(&format!("bytes {start}-{end}/")));
            assert_eq!(response.bytes().await.unwrap().len(), 1024);
            println!("start={start} end={end} status=206 length=1024");
        }
        sessions.close(&sid);
    }
    #[test]
    fn vkeys_uses_returned_song_mid_and_rejects_conflicting_evidence() {
        let id = "0039MnYb0qxYhV";
        // 复现上游 data 的字段形状，媒体地址使用测试占位。
        for (quality, ext) in [("auto", "flac"), ("standard", "m4a")] {
            let fixture = serde_json::json!({
                "code": 0,
                "data": {
                    "songID": 123,
                    "songMID": id,
                    "kbps": null,
                    "link": null,
                    "url": format!("https://stream.qqmusic.qq.com/fixture.{ext}"),
                },
            });
            assert!(parse("qq", "vkeys", id, &fixture).is_ok(), "{quality}");
            assert!(
                crate::download_resolver::parse("qq", "vkeys", id, &fixture, "晴天", "周杰伦")
                    .is_ok(),
                "{quality}"
            );

            let mut missing = fixture.clone();
            missing["data"].as_object_mut().unwrap().remove("songMID");
            assert_eq!(
                parse("qq", "vkeys", id, &missing).unwrap_err(),
                "source_verification_failed"
            );

            let mut wrong = fixture.clone();
            wrong["data"]["songMID"] = serde_json::json!("wrongMID");
            for response in [wrong.clone(), {
                wrong["data"]["song_mid"] = serde_json::json!(id);
                wrong
            }] {
                assert_eq!(
                    parse("qq", "vkeys", id, &response).unwrap_err(),
                    "source_verification_failed"
                );
                assert_eq!(
                    crate::download_resolver::parse("qq", "vkeys", id, &response, "晴天", "周杰伦")
                        .unwrap_err(),
                    "source_verification_failed",
                );
            }

            let mut restricted = fixture;
            restricted["data"]["freeTrialInfo"] = serde_json::json!({"limited": true});
            assert_eq!(
                parse("qq", "vkeys", id, &restricted).unwrap_err(),
                "access_denied"
            );
        }

        let only_vkeys_field = serde_json::json!({
            "songMID": id,
            "song_play_url": "https://stream.qqmusic.qq.com/fixture.mp3",
        });
        assert_eq!(
            parse("qq", "tang", id, &only_vkeys_field).unwrap_err(),
            "source_verification_failed",
        );
    }

    #[test]
    fn shared_route_policy_stops_on_authorization_and_invalid_input() {
        let rows: Vec<Value> = serde_json::from_str(include_str!(
            "../../../tests/fixtures/contracts/resolution.json"
        )).unwrap();
        for row in rows {
            assert_eq!(
                may_try_another_route(row["desktop"].as_str().unwrap()),
                row["continues"].as_bool().unwrap(),
                "{}", row["code"],
            );
        }
    }

    #[tokio::test]
    async fn native_first_and_denials_never_call_backup() {
        for result in [
            Ok(123),
            Err("access_denied".into()),
            Err("upstream_failure".into()),
        ] {
            let calls = Arc::new(AtomicUsize::new(0));
            let count = calls.clone();
            let value = choose(
                || async { result },
                &["tang".into()],
                move |_| {
                    count.fetch_add(1, Ordering::SeqCst);
                    async { Ok(456) }
                },
            )
            .await;
            assert_eq!(calls.load(Ordering::SeqCst), 0);
            if let Ok((value, route)) = value {
                assert_eq!(value, 123);
                assert_eq!(route, "native");
            }
        }
    }
    #[tokio::test]
    async fn netease_empty_minus_110_can_reach_verified_backup() {
        for (id, code, trial, expected) in [
            ("30612793", -110, Value::Null, true),
            ("2083785152", -110, Value::Null, true),
            ("30612793", 403, Value::Null, false),
            ("30612793", 200, json!({"start":0,"end":30}), false),
        ] {
            let native =
                json!({"code":200,"data":[{"id":id,"code":code,"url":null,"freeTrialInfo":trial}]});
            let backup = json!({"success":true,"data":{"id":id,"url":"https://m701.music.126.net/audio.mp3"}});
            let result = choose(
                || async { crate::provider::netease::media(native, id) },
                &["jfjt".into()],
                |route| {
                    let result = parse("netease", &route, id, &backup);
                    async { result }
                },
            )
            .await;
            assert_eq!(result.is_ok(), expected, "{id}: {result:?}");
        }
    }
    #[tokio::test]
    async fn timeout_has_a_bounded_end() {
        let value = choose(
            || async {
                Err::<u8, _>("anonymous_media_unavailable".into())
            },
            &["tang".into()],
            |_| async { std::future::pending().await },
        )
        .await;
        assert_eq!(value.unwrap_err(), "upstream_timeout");
    }
    #[test]
    fn builtin_defaults_and_explicit_overrides() {
        let config = Config::default();
        assert_eq!(
            config.routes("qq", "0027oMO61wWi55"),
            vec!["vkeys", "tang", "xunhuisi"]
        );
        assert_eq!(
            config.routes("netease", "123"),
            vec!["gdstudio-preview", "jfjt"]
        );
        assert!(config.routes("kuwo", "123").is_empty());
        assert!(Config::parse(r#"{"routes":[]}"#)
            .unwrap()
            .routes("qq", "123")
            .is_empty());
        let override_config=Config::parse(r#"{"routes":[{"provider":"qq","route":"tang"},{"provider":"qq","route":"vkeys","tracks":["123"]}]}"#).unwrap();
        assert_eq!(override_config.routes("qq", "123"), vec!["tang", "vkeys"]);
        assert_eq!(override_config.routes("qq", "456"), vec!["tang"]);
        assert!(override_config.routes("netease", "123").is_empty());
    }
    #[tokio::test]
    async fn invalid_vkeys_result_does_not_block_tang_but_restrictions_do() {
        for error in [
            "source_verification_failed",
            "source_verification_failed",
            "access_denied",
            "access_denied",
        ] {
            let calls = Arc::new(AtomicUsize::new(0));
            let count = calls.clone();
            let value = choose(
                || async {
                    Err::<u8, _>("anonymous_media_unavailable".into())
                },
                &["vkeys".into(), "tang".into()],
                move |route| {
                    count.fetch_add(1, Ordering::SeqCst);
                    async move {
                        if route == "vkeys" {
                            Err(error.into())
                        } else {
                            Ok(1)
                        }
                    }
                },
            )
            .await;
            if error == "access_denied" {
                assert!(value.is_err());
                assert_eq!(calls.load(Ordering::SeqCst), 1);
            } else {
                assert_eq!(value.unwrap(), (1, "tang".into()));
                assert_eq!(calls.load(Ordering::SeqCst), 2);
            }
        }
    }
    #[test]
    fn independent_grants_and_strict_identity() {
        let config =
            Config::parse(r#"{"routes":[{"provider":"qq","route":"tang","tracks":["123"]}]}"#)
                .unwrap();
        assert_eq!(config.routes("qq", "123"), vec!["tang"]);
        assert!(config.routes("netease", "123").is_empty());
        assert!(config.routes("qq", "456").is_empty());
        assert!(Config::parse(
            r#"{"routes":[{"provider":"qq","route":"unknown","tracks":["123"]}]}"#
        )
        .is_err());
        let url = "https://isure.stream.qqmusic.qq.com/audio.m4a";
        assert!(parse("qq", "vkeys", "123", &json!({"data":{"url":url}})).is_err());
        assert!(parse(
            "qq",
            "tang",
            "123",
            &json!({"song_mid":"456","song_play_url":url})
        )
        .is_err());
        assert!(parse(
            "qq",
            "tang",
            "123",
            &json!({"song_mid":"123","song_name":"原曲 Live","song_play_url":url})
        )
        .is_err());
        assert!(parse(
            "qq",
            "tang",
            "123",
            &json!({"code":403,"song_mid":"123","song_play_url":url})
        )
        .is_err());
        assert_eq!(
            parse(
                "qq",
                "tang",
                "123",
                &json!({"song_mid":"123","song_name":"原曲","song_play_url":url})
            )
            .unwrap(),
            url
        );
        assert_eq!(
            parse(
                "qq",
                "xunhuisi",
                "123",
                &json!({"mid":"123","title":"原曲","music_url":url})
            )
            .unwrap(),
            url
        );
        assert!(parse(
            "qq",
            "xunhuisi",
            "123",
            &json!({"link":"https://y.qq.com/n/ryqq/songDetail/123","title":"原曲","music_url":url})
        )
        .is_err());
        let net = "https://m701.music.126.net/audio.mp3";
        assert_eq!(
            parse(
                "netease",
                "gdstudio-preview",
                "123",
                &json!({"id":123,"url":net})
            )
            .unwrap(),
            net
        );
        assert_eq!(
            parse(
                "netease",
                "jfjt",
                "123",
                &json!({"success":true,"data":{"id":123,"name":"原曲","url":net}})
            )
            .unwrap(),
            net
        );
        assert!(parse(
            "netease",
            "jfjt",
            "123",
            &json!({"success":true,"data":{"id":123,"url":net,"freeTrialInfo":{}}})
        )
        .is_err());
    }
    #[tokio::test]
    #[ignore = "需要访问网易云及已配置的备用服务"]
    async fn netease_online_regression() {
        let client = reqwest::Client::builder()
            .user_agent("Mozilla/5.0")
            .redirect(reqwest::redirect::Policy::none())
            .timeout(Duration::from_secs(12))
            .build()
            .unwrap();
        let config = Config::default();
        let sessions = crate::sessions::Sessions::new();
        let covers = crate::covers::Covers::default();
        let port = crate::transport::start_with_covers(
            crate::transport::Transport {
                sessions: sessions.clone(),
                client: client.clone(),
            },
            covers.clone(),
        )
        .await
        .unwrap();
        let ((), ()) = tokio::join!(
            async {
                for (title, id) in [("句号", "1405283464"), ("回忆的沙漏", "234023")] {
                    let mut page = crate::provider::netease::search(
                        &client,
                        &json!({"query":format!("邓紫棋 {title}")}),
                    )
                    .await
                    .unwrap();
                    crate::covers::Covers::map_page(&mut page);
                    let cover = page["items"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .find(|row| row["identity"]["platformId"] == id)
                        .unwrap()["cover"]
                        .as_str()
                        .unwrap();
                    assert!(cover.starts_with("https://"));
                    assert!(cover.contains("param=500y500"));
                    let response = client.get(cover).send().await.unwrap();
                    assert_eq!(response.status(), 200, "{title}");
                    let bytes = response.bytes().await.unwrap();
                    assert!(crate::covers::image_type(&bytes).is_some(), "{title}");
                    println!("{title}: cover {} bytes", bytes.len());
                }
            },
            async {
                for (title, id) in [("多远都要在一起", "30612793"), ("唯一", "2083785152")]
                {
                    let (media, route, _) = resolve(
                        &client,
                        &config,
                        &json!({"providerId":"netease","platformId":id}),
                    )
                    .await
                    .unwrap_or_else(|err| panic!("{title}: {err}"));
                    let sid = sessions.insert_media(media);
                    for range in ["bytes=0-1023", "bytes=300000-301023"] {
                        let response = client
                            .get(format!("http://127.0.0.1:{port}/api/playback/{sid}/stream"))
                            .header("Range", range)
                            .send()
                            .await
                            .unwrap();
                        assert_eq!(response.status(), 206, "{title} route={route} {range}");
                        assert_eq!(response.bytes().await.unwrap().len(), 1024);
                    }
                    println!("{title}: {route} returned both ranges");
                }
            }
        );
    }
    #[tokio::test]
    #[ignore = "固定真实样本；需要网络及已获授权的服务使用范围"]
    async fn online_fixed_samples() {
        let config = Config::from_env().unwrap();
        println!(
            "fallback_config_present={}",
            std::env::var_os("MUSIC_CORE_DESKTOP_FALLBACKS").is_some()
        );
        let client = reqwest::Client::builder()
            .user_agent("Mozilla/5.0")
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .unwrap();
        for (source, id) in [
            ("qq", "0027oMO61wWi55"),
            ("qq", "0037WF7I0yUPLu"),
            ("qq", "0039MnYb0qxYhV"),
            ("netease", "2668397359"),
            ("netease", "186016"),
        ] {
            let identity = json!({"providerId":source,"platformId":id});
            let before = crate::provider::resolve(&client, &identity).await;
            println!(
                "{id} native={}",
                if before.is_ok() {
                    "media_resolved"
                } else {
                    before.as_ref().err().unwrap()
                }
            );
            match resolve(&client, &config, &identity).await {
                Ok((media, route, _)) => {
                    let sessions = crate::sessions::Sessions::new();
                    let sid = sessions.insert_media(media);
                    let port = crate::transport::start(crate::transport::Transport {
                        sessions: sessions.clone(),
                        client: client.clone(),
                    })
                    .await
                    .unwrap();
                    for range in ["bytes=0-1023", "bytes=300000-301023"] {
                        let response = client
                            .get(format!("http://127.0.0.1:{port}/api/playback/{sid}/stream"))
                            .header("Range", range)
                            .send()
                            .await
                            .unwrap();
                        println!(
                            "{id} route={route} range={range} status={} content-range={:?}",
                            response.status(),
                            response.headers().get("content-range")
                        );
                        assert_eq!(response.status(), 206);
                        assert_eq!(response.bytes().await.unwrap().len(), 1024);
                    }
                    sessions.close(&sid);
                }
                Err(error) => println!("{id} final_error={error}"),
            }
        }
    }
}
