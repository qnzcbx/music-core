use serde_json::{json, Value};

pub fn valid_id(source: &str, id: &str) -> bool {
    !id.is_empty()
        && if source == "qq" {
            id.len() <= 64 && id.bytes().all(|c| c.is_ascii_alphanumeric())
        } else {
            id.len() <= if source == "migu" { 32 } else { 20 }
                && !id.starts_with('0')
                && id.bytes().all(|c| c.is_ascii_digit())
        }
}
pub fn id(value: &Value) -> Option<String> {
    value
        .as_str()
        .map(str::to_owned)
        .or_else(|| value.as_u64().filter(|n| *n > 0).map(|n| n.to_string()))
}
pub fn page(body: &Value) -> Result<(String, u64, u64), String> {
    let query = body["query"].as_str().unwrap_or("").trim();
    let limit = body["limit"].as_u64().unwrap_or(15);
    if query.is_empty() || query.chars().count() > 80 || !(1..=15).contains(&limit) {
        return Err("搜索参数无效".into());
    }
    let page = if body["cursor"].is_null() {
        1
    } else {
        let cursor = body["cursor"].as_str().ok_or("搜索游标无效")?;
        let (p, l) = cursor.split_once(':').ok_or("搜索游标无效")?;
        let p = p.parse::<u64>().map_err(|_| "搜索游标无效")?;
        if !(2..=10).contains(&p) || l != limit.to_string() {
            return Err("搜索游标无效".into());
        }
        p
    };
    Ok((query.to_owned(), limit, page))
}
pub fn result(
    rows: &Value,
    total: &Value,
    limit: u64,
    page: u64,
    map: fn(&Value) -> Option<Value>,
) -> Result<Value, String> {
    let rows = rows.as_array().ok_or("来源搜索响应格式异常")?;
    let mut items = Vec::new();
    for row in rows.iter().take(limit as usize).filter_map(map) {
        if !items
            .iter()
            .any(|old: &Value| old["identity"] == row["identity"])
        {
            items.push(row);
        }
    }
    let total = total
        .as_u64()
        .or_else(|| total.as_str().and_then(|s| s.parse().ok()));
    let more = !rows.is_empty() && page < 10 && total.is_none_or(|n| page * limit < n);
    Ok(json!({"items":items,"nextCursor":more.then(||format!("{}:{limit}",page+1))}))
}
pub fn candidate(
    source: &str,
    id: String,
    title: &Value,
    artists: &Value,
    album: Value,
    duration: Option<f64>,
    cover: Value,
) -> Option<Value> {
    let title = title.as_str()?.trim();
    if !valid_id(source, &id) || title.is_empty() {
        return None;
    }
    let artists: Vec<_> = artists
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|a| a["name"].as_str())
        .filter(|s| !s.is_empty())
        .collect();
    Some(
        json!({"identity":{"providerId":source,"platformId":id},"title":title,"artists":artists,
        "album":album,"durationSeconds":duration.filter(|n|n.is_finite()&&*n>=0.0),"cover":cover}),
    )
}
pub async fn bytes(request: reqwest::RequestBuilder) -> Result<Vec<u8>, String> {
    let mut response = request.send().await.map_err(|e| {
        if e.is_timeout() {
            "来源请求超时"
        } else {
            "来源网络请求失败"
        }
    })?;
    match response.status().as_u16() {
        200 => {}
        401 | 403 => return Err("来源拒绝匿名访问或当前访问权限不足".into()),
        429 => return Err("来源请求过于频繁，请稍后再试".into()),
        _ => return Err("来源服务暂不可用".into()),
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| "来源响应读取失败")? {
        if bytes.len() + chunk.len() > 2 * 1024 * 1024 {
            return Err("来源响应过大".into());
        }
        bytes.extend_from_slice(&chunk);
    }
    Ok(bytes)
}
pub async fn json(request: reqwest::RequestBuilder) -> Result<Value, String> {
    serde_json::from_slice(&bytes(request).await?).map_err(|_| "来源返回格式异常".into())
}
pub fn validate_media(source: &str, url: &str) -> Result<(), String> {
    let url = reqwest::Url::parse(url).map_err(|_| "媒体地址无效")?;
    let domains: &[&str] = match source {
        "kuwo" => &["kuwo.cn"],
        "netease" => &["music.126.net"],
        "qq" => &["stream.qqmusic.qq.com", "aqqmusic.tc.qq.com"],
        "migu" => &["freetyst.nf.migu.cn"],
        _ => &[],
    };
    let host = url.host_str().unwrap_or("");
    if !matches!(url.scheme(), "http" | "https")
        || !url.username().is_empty()
        || url.password().is_some()
        || url.port().is_some_and(|p| p != 80 && p != 443)
        || !domains
            .iter()
            .any(|d| host == *d || host.ends_with(&format!(".{d}")))
    {
        return Err("来源返回了不受信任的媒体地址".into());
    }
    if [".m3u8", ".mpd", ".mgg", ".mflac"]
        .iter()
        .any(|s| url.path().to_lowercase().ends_with(s))
    {
        return Err("该媒体格式暂不支持桌面播放".into());
    }
    Ok(())
}
