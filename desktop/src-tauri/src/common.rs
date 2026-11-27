use serde_json::{json, Value};

pub fn valid_id(source: &str, id: &str) -> bool {
    matches!(source, "qq" | "kuwo" | "netease" | "migu")
        && !id.is_empty()
        && if source == "qq" {
            id.len() <= 64 && id.bytes().all(|c| c.is_ascii_alphanumeric())
        } else {
            id.len() <= if source == "migu" { 32 } else { 20 }
                && !id.starts_with('0')
                && id.bytes().all(|c| c.is_ascii_digit())
        }
}
pub(crate) fn identity(value: &Value) -> Option<(&str, &str)> {
    let source = value["providerId"].as_str()?;
    let id = value["platformId"].as_str()?;
    valid_id(source, id).then_some((source, id))
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
        return Err("invalid_input".into());
    }
    let page = if body["cursor"].is_null() {
        1
    } else {
        let cursor = body["cursor"].as_str().ok_or("invalid_input")?;
        let (p, l) = cursor.split_once(':').ok_or("invalid_input")?;
        let p = p.parse::<u64>().map_err(|_| "invalid_input")?;
        if !(2..=10).contains(&p) || l != limit.to_string() {
            return Err("invalid_input".into());
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
    let rows = rows.as_array().ok_or("upstream_invalid_response")?;
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
            "upstream_timeout"
        } else {
            "upstream_failure"
        }
    })?;
    match response.status().as_u16() {
        200 => {}
        401 | 403 => return Err("access_denied".into()),
        429 => return Err("upstream_rate_limited".into()),
        _ => return Err("upstream_failure".into()),
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| "upstream_failure")? {
        if bytes.len() + chunk.len() > 2 * 1024 * 1024 {
            return Err("upstream_invalid_response".into());
        }
        bytes.extend_from_slice(&chunk);
    }
    Ok(bytes)
}
pub async fn json(request: reqwest::RequestBuilder) -> Result<Value, String> {
    serde_json::from_slice(&bytes(request).await?).map_err(|_| "upstream_invalid_response".into())
}
pub fn validate_media(source: &str, url: &str) -> Result<(), String> {
    let url = reqwest::Url::parse(url).map_err(|_| "untrusted_media")?;
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
        return Err("untrusted_media".into());
    }
    if [".m3u8", ".mpd", ".mgg", ".mflac"]
        .iter()
        .any(|s| url.path().to_lowercase().ends_with(s))
    {
        return Err("capability_unsupported".into());
    }
    Ok(())
}
