use serde_json::{json, Value};

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
        "album":raw["ALBUM"],"cover":raw.get("hts_MVPIC").or(raw.get("albumpic")).or(raw.get("pic")),
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
        return Err("此来源尚未迁移到桌面版".into());
    }
    let query = body["query"].as_str().unwrap_or("").trim();
    if query.is_empty() || query.chars().count() > 80 {
        return Err("请输入 1–80 字的关键词".into());
    }
    let limit = body["limit"].as_u64().unwrap_or(15);
    if !(1..=15).contains(&limit) {
        return Err("搜索数量无效".into());
    }
    let page = match body["cursor"].as_str() {
        None => 0,
        Some(cursor) => {
            let parts: Vec<_> = cursor.split(':').collect();
            if parts.len() != 2 || parts[1] != limit.to_string() {
                return Err("搜索游标无效".into());
            }
            let page = parts[0].parse::<u64>().map_err(|_| "搜索游标无效")?;
            if !(1..=9).contains(&page) {
                return Err("搜索游标无效".into());
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
        .map_err(|_| "酷我搜索网络失败")?
        .error_for_status()
        .map_err(|_| "酷我搜索暂不可用")?;
    let text = response.text().await.map_err(|_| "搜索响应读取失败")?;
    if text.len() > 2 * 1024 * 1024 {
        return Err("来源响应过大".into());
    }
    let data: Value = json5::from_str(&text).map_err(|_| "酷我返回格式异常")?;
    let rows = data["abslist"].as_array().ok_or("酷我搜索暂不可用")?;
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
        return Err("歌曲来源或身份无效".into());
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
        .map_err(|_| "歌曲解析网络失败")?
        .error_for_status()
        .map_err(|_| "歌曲暂不可用")?
        .text()
        .await
        .map_err(|_| "歌曲解析失败")?;
    let fields: std::collections::HashMap<_, _> = text
        .lines()
        .filter_map(|s| s.split_once('='))
        .map(|(k, v)| (k, v.trim()))
        .collect();
    if fields.get("rid") != Some(&id) {
        return Err("来源未返回匹配的歌曲".into());
    }
    let url = fields.get("url").ok_or("歌曲暂不可播放")?;
    let parsed = reqwest::Url::parse(url).map_err(|_| "媒体地址无效")?;
    let host = parsed.host_str().unwrap_or("");
    if !matches!(parsed.scheme(), "http" | "https")
        || !(host == "kuwo.cn" || host.ends_with(".kuwo.cn"))
        || !parsed.username().is_empty()
        || parsed.password().is_some()
    {
        return Err("来源返回了不受信任的媒体地址".into());
    }
    Ok(url.to_string())
}

#[cfg(test)]
mod tests {
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
