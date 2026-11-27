use serde_json::{json, Value};

fn cover_url(raw: &Value) -> Option<String> {
    ["hts_MVPIC", "albumpic", "pic"]
        .iter()
        .filter_map(|key| raw[*key].as_str())
        .find(|url| crate::covers::valid_url("kuwo", url))
        .map(str::to_owned)
        .or_else(|| {
            let short = raw["web_albumpic_short"].as_str()?;
            static ALBUM_PATH: std::sync::LazyLock<regex::Regex> = std::sync::LazyLock::new(|| {
                regex::Regex::new(r"^[0-9]{1,4}/[A-Za-z0-9]{1,24}/[0-9]{1,8}/[0-9]{1,24}\.jpg$")
                    .unwrap()
            });
            ALBUM_PATH
                .is_match(short)
                .then(|| format!("https://img1.kuwo.cn/star/albumcover/{short}"))
        })
}

pub fn candidate(raw: &Value) -> Option<Value> {
    let id = raw.get("MUSICRID")?.as_str()?.trim_start_matches("MUSIC_");
    if !valid_id(id) {
        return None;
    }
    let title = raw.get("SONGNAME")?.as_str()?.trim();
    if title.is_empty() {
        return None;
    }
    let artists: Vec<String> = raw["ARTIST"]
        .as_str()
        .unwrap_or("")
        .split(['&', ';'])
        .map(|s| html_escape::decode_html_entities(s.trim()).into_owned())
        .filter(|s| !s.is_empty())
        .collect();
    Some(json!({"identity":{"providerId":"kuwo","platformId":id},
        "title":html_escape::decode_html_entities(title),"artists":artists,
        "album":raw["ALBUM"],"cover":cover_url(raw),"downloadAllowed":crate::downloads::eligibility(raw),
        "durationSeconds":raw["DURATION"].as_str().and_then(|s| s.parse::<f64>().ok()).filter(|n| n.is_finite() && *n >= 0.0)}))
}

pub fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 20
        && !id.starts_with('0')
        && id.bytes().all(|c| c.is_ascii_digit())
}

pub async fn search(client: &reqwest::Client, body: &Value) -> Result<Value, String> {
    if body["providerId"] != "kuwo" {
        return Err("capability_unsupported".into());
    }
    let query = body["query"].as_str().unwrap_or("").trim();
    if query.is_empty() || query.chars().count() > 80 {
        return Err("invalid_input".into());
    }
    let limit = body["limit"].as_u64().unwrap_or(15);
    if !(1..=15).contains(&limit) {
        return Err("invalid_input".into());
    }
    let page = match body["cursor"].as_str() {
        None => 0,
        Some(cursor) => {
            let parts: Vec<_> = cursor.split(':').collect();
            if parts.len() != 2 || parts[1] != limit.to_string() {
                return Err("invalid_input".into());
            }
            let page = parts[0].parse::<u64>().map_err(|_| "invalid_input")?;
            if !(1..=9).contains(&page) {
                return Err("invalid_input".into());
            }
            page
        }
    };
    let response = client
        .get("https://www.kuwo.cn/search/searchMusicBykeyWord")
        .query(&[
            ("all", query.to_owned()),
            ("ft", "music".into()),
            ("client", "kt".into()),
            ("vipver", "1".into()),
            ("pn", page.to_string()),
            ("rn", limit.to_string()),
            ("rformat", "json".into()),
            ("encoding", "utf8".into()),
            ("mobi", "1".into()),
        ])
        .send()
        .await
        .map_err(|_| "upstream_failure")?
        .error_for_status()
        .map_err(|_| "upstream_failure")?;
    let text = response.text().await.map_err(|_| "upstream_failure")?;
    if text.len() > 2 * 1024 * 1024 {
        return Err("upstream_invalid_response".into());
    }
    let data: Value = json5::from_str(&text).map_err(|_| "upstream_invalid_response")?;
    let rows = data["abslist"].as_array().ok_or("upstream_failure")?;
    let mut items = Vec::new();
    for item in rows.iter().take(limit as usize).filter_map(candidate) {
        if !items
            .iter()
            .any(|old: &Value| old["identity"] == item["identity"])
        {
            items.push(item);
        }
    }
    let total = data["TOTAL"]
        .as_str()
        .and_then(|s| s.parse::<u64>().ok())
        .or(data["TOTAL"].as_u64());
    let more = !rows.is_empty() && page < 9 && total.is_none_or(|n| (page + 1) * limit < n);
    Ok(json!({"items":items,"nextCursor":more.then(||format!("{}:{}",page+1,limit))}))
}

pub async fn resolve(client: &reqwest::Client, identity: &Value) -> Result<String, String> {
    let id = identity["platformId"].as_str().unwrap_or("");
    if identity["providerId"] != "kuwo" || !valid_id(id) {
        return Err("invalid_input".into());
    }
    // 复用现有同平台 mobi 取链，不需要账户 Cookie。
    let text = client
        .get("https://mobi.kuwo.cn/mobi.s")
        .header("User-Agent", "okhttp/3.10.0")
        .query(&[
            ("user", "0"),
            ("corp", "kuwo"),
            ("source", "kwplayer_ar_5.1.0.0_B_jiakong_vh.apk"),
            ("p2p", "1"),
            ("type", "convert_url2"),
            ("sig", "0"),
            ("format", "mp3"),
            ("rid", id),
        ])
        .send()
        .await
        .map_err(|_| "upstream_failure")?
        .error_for_status()
        .map_err(|_| "upstream_failure")?
        .text()
        .await
        .map_err(|_| "upstream_failure")?;
    let fields: std::collections::HashMap<_, _> = text
        .lines()
        .filter_map(|s| s.split_once('='))
        .map(|(k, v)| (k, v.trim()))
        .collect();
    if fields.get("rid") != Some(&id) {
        return Err("source_verification_failed".into());
    }
    let url = fields.get("url").ok_or("media_unavailable")?;
    let parsed = reqwest::Url::parse(url).map_err(|_| "untrusted_media")?;
    let host = parsed.host_str().unwrap_or("");
    if !matches!(parsed.scheme(), "http" | "https")
        || !(host == "kuwo.cn" || host.ends_with(".kuwo.cn"))
        || !parsed.username().is_empty()
        || parsed.password().is_some()
    {
        return Err("untrusted_media".into());
    }
    Ok(url.to_string())
}

#[cfg(test)]
mod tests {
    #[test]
    fn uses_album_short_path_when_cover_is_missing() {
        let mut row = serde_json::json!({"MUSICRID":"MUSIC_409123142","SONGNAME":"test",
            "hts_MVPIC":"","albumpic":"invalid","web_albumpic_short":"120/s4s50/91/3189617145.jpg"});
        assert_eq!(
            super::candidate(&row).unwrap()["cover"],
            "https://img1.kuwo.cn/star/albumcover/120/s4s50/91/3189617145.jpg"
        );
        row["pic"] = serde_json::json!("https://img1.kuwo.cn/test.jpg");
        assert_eq!(super::candidate(&row).unwrap()["cover"], row["pic"]);
        row["pic"] = serde_json::Value::Null;
        row["web_albumpic_short"] = serde_json::json!("../test.jpg");
        assert!(super::candidate(&row).unwrap()["cover"].is_null());
    }

    use super::*;
    #[tokio::test]
    #[ignore = "需要连接真实酷我服务"]
    async fn online_search_and_range() {
        let client = reqwest::Client::builder()
            .user_agent("Mozilla/5.0")
            .timeout(std::time::Duration::from_secs(25))
            .build()
            .unwrap();
        let page = search(
            &client,
            &json!({"providerId":"kuwo","query":"test","limit":1}),
        )
        .await
        .unwrap();
        let identity = &page["items"][0]["identity"];
        let url = resolve(&client, identity).await.unwrap();
        let sessions = crate::sessions::Sessions::new();
        let id = sessions.insert(url);
        let port = crate::transport::start(crate::transport::Transport {
            sessions: sessions.clone(),
            client: client.clone(),
        })
        .await
        .unwrap();
        let local = format!("http://127.0.0.1:{port}/api/playback/{id}/stream");
        for range in ["bytes=0-1023", "bytes=300000-301023"] {
            let response = client
                .get(&local)
                .header("Range", range)
                .send()
                .await
                .unwrap();
            assert_eq!(response.status(), 206);
            assert!(response.headers().contains_key("content-range"));
            assert_eq!(response.bytes().await.unwrap().len(), 1024);
        }
        sessions.close(&id);
        assert_eq!(client.get(&local).send().await.unwrap().status(), 410);
        println!("真实酷我搜索、取链、起始及中段 Range、释放会话通过；identity={identity}");
    }
    #[test]
    fn maps_identity_and_entities() {
        let row = candidate(&json!({"MUSICRID":"MUSIC_123","SONGNAME":"A &amp; B","ARTIST":"甲&乙","DURATION":"90"})).unwrap();
        assert_eq!(row["identity"]["platformId"], "123");
        assert_eq!(row["title"], "A & B");
        assert_eq!(row["artists"], json!(["甲", "乙"]));
        assert!(candidate(&json!({"MUSICRID":"bad","SONGNAME":"x"})).is_none());
    }
}
