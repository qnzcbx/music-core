use super::common;
use serde_json::{json, Value};
const ROOT: &str = "https://c.musicapp.migu.cn";
pub(crate) fn request(client: &reqwest::Client, path: &str) -> reqwest::RequestBuilder {
    client
        .get(format!("{ROOT}{path}"))
        .header("Origin", "https://h5.nf.migu.cn")
        .header("Referer", "https://h5.nf.migu.cn/")
        .header("ua", "Android_migu")
        .header("version", "6.8.8")
        .header("channel", "014021I")
        .header("subchannel", "014021I")
}
pub fn decode(mut bytes: Vec<u8>) -> Result<Value, String> {
    // 与现有后端相同的公开响应字节混淆格式，不是媒体解密。
    if bytes.starts_with(&[0xab, 0xcd, 1]) {
        if bytes.len() < 5 {
            return Err("upstream_invalid_response".into());
        }
        let key = b"Jk8qzuePiJ1qE3mDYhLQ3T73DtDoAhLP";
        let seed = bytes[3];
        bytes = bytes[4..]
            .iter()
            .enumerate()
            .map(|(i, b)| b.wrapping_add(seed).wrapping_sub(key[i % key.len()]))
            .collect();
    }
    let data: Value = serde_json::from_slice(&bytes).map_err(|_| "upstream_invalid_response")?;
    if data
        .get("code")
        .or(data.get("returnCode"))
        .is_some_and(|c| {
            !matches!(c.as_str(), Some("0" | "000000" | "200"))
                && !matches!(c.as_i64(), Some(0 | 200))
        })
    {
        return Err("upstream_failure".into());
    }
    Ok(data)
}
pub fn candidate(row: &Value) -> Option<Value> {
    let cover = row["imgItems"]
        .as_array()
        .into_iter()
        .flatten()
        .rev()
        .find_map(|v| v["img"].as_str())
        .or(row["img3"].as_str())
        .or(row["img2"].as_str())
        .or(row["img1"].as_str())
        .and_then(|s| {
            reqwest::Url::parse("https://d.musicapp.migu.cn")
                .unwrap()
                .join(s)
                .ok()
        })
        .map(|u| u.to_string());
    let title = row.get("name").or(row.get("songName"))?;
    let singers = row
        .get("singers")
        .or(row.get("singerList"))
        .unwrap_or(&Value::Null);
    let album = row["album"].as_str().map(str::to_owned).or_else(|| {
        row["albums"].as_array().map(|a| {
            a.iter()
                .filter_map(|a| a["name"].as_str())
                .collect::<Vec<_>>()
                .join(", ")
        })
    });
    common::candidate(
        "migu",
        common::id(&row["contentId"])?,
        title,
        singers,
        json!(album),
        row["duration"].as_f64(),
        json!(cover),
    )
}
pub async fn search(client: &reqwest::Client, body: &Value) -> Result<Value, String> {
    let (query, limit, page) = common::page(body)?;
    let data = decode(
        common::bytes(request(client, "/v1.0/content/search_all.do").query(&[
            ("text", query),
            ("pageNo", page.to_string()),
            ("pageSize", limit.to_string()),
            ("isCopyright", "1".into()),
            ("sort", "1".into()),
            (
                "searchSwitch",
                "{'song':1,'album':0,'singer':0,'tagSong':1,'mvSong':0,'bestShow':1}".into(),
            ),
        ]))
        .await?,
    )?;
    common::result(
        &data["songResultData"]["result"],
        &data["songResultData"]["totalCount"],
        limit,
        page,
        candidate,
    )
}
#[cfg(test)]
pub fn context(data: &Value, id: &str) -> Result<(String, String, String), String> {
    context_quality(data, id, "auto")
}
pub fn context_quality(
    data: &Value,
    id: &str,
    quality: &str,
) -> Result<(String, String, String), String> {
    let rows = data["resource"].as_array().ok_or("upstream_invalid_response")?;
    if rows.len() != 1 || common::id(&rows[0]["contentId"]).as_deref() != Some(id) {
        return Err("source_verification_failed".into());
    }
    let row = &rows[0];
    if !row["needEncrypt"].is_null()
        && !matches!(row["needEncrypt"], Value::Bool(false))
        && row["needEncrypt"] != 0
        && row["needEncrypt"] != "0"
    {
        return Err("encrypted_media".into());
    }
    let copyright = common::id(&row["copyrightId"])
        .filter(|s| !s.is_empty() && s.len() <= 64 && s.bytes().all(|c| c.is_ascii_alphanumeric()))
        .ok_or("source_verification_failed")?;
    let tones: &[&str] = match quality {
        "standard" => &["PQ"],
        "high" => &["HQ"],
        "lossless" => return Err("capability_unsupported".into()),
        _ => &["PQ", "LQ", "HQ"],
    };
    for tone in tones {
        for field in ["rateFormats", "newRateFormats", "audioFormats"] {
            for f in row[field].as_array().into_iter().flatten() {
                if f["formatType"] == *tone {
                    if let Some(resource) =
                        common::id(&f["resourceType"]).filter(|s| common::valid_id("migu", s))
                    {
                        return Ok((copyright, (*tone).into(), resource));
                    }
                }
            }
        }
    }
    Err("media_unavailable".into())
}
pub fn media(data: Value, id: &str, copyright: &str) -> Result<String, String> {
    let body = &data["data"];
    if common::id(&body["song"]["contentId"]).as_deref() != Some(id)
        || common::id(&body["song"]["copyrightId"]).as_deref() != Some(copyright)
    {
        return Err("source_verification_failed".into());
    }
    if body["audioFormatType"]
        .as_str()
        .is_some_and(|s| !matches!(s, "PQ" | "LQ" | "HQ"))
    {
        return Err("capability_unsupported".into());
    }
    if !body["freeListenType"].is_null()
        && body["freeListenType"] != 0
        && body["freeListenType"] != "0"
        && body["freeListenType"] != false
    {
        return Err("preview_only".into());
    }
    body["url"]
        .as_str()
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .ok_or("media_unavailable".into())
}
pub async fn resolve(client: &reqwest::Client, id: &str) -> Result<String, String> {
    resolve_quality(client, id, "auto").await
}
pub async fn resolve_quality(
    client: &reqwest::Client,
    id: &str,
    quality: &str,
) -> Result<String, String> {
    Ok(resolve_download(client, id, quality).await?.0)
}
pub async fn resolve_download(
    client: &reqwest::Client,
    id: &str,
    quality: &str,
) -> Result<(String, f64), String> {
    let detail = decode(
        common::bytes(
            request(client, "/v1.0/content/resourceinfo.do")
                .query(&[("resourceId", id), ("resourceType", "2")]),
        )
        .await?,
    )?;
    let (copyright, tone, resource) = context_quality(&detail, id, quality)?;
    let duration = detail["resource"][0]["length"]
        .as_str()
        .and_then(parse_duration)
        .unwrap_or(0.0);
    let data = decode(
        common::bytes(
            request(client, "/strategy/listen-url/h5/v2.4")
                .header("birth", "h5page")
                .header("signature", "1")
                .header("Content-Type", "application/json;charset=UTF-8")
                .query(&[
                    ("contentId", id),
                    ("copyrightId", &copyright),
                    ("resourceType", &resource),
                    ("netType", "01"),
                    ("toneFlag", &tone),
                    ("scene", ""),
                    ("lowerQualityContentId", id),
                ]),
        )
        .await?,
    )?;
    Ok((media(data, id, &copyright)?, duration))
}

// 原生详情 length 是时:分:秒，不将缺失值或畸形字段作为可信时长。
fn parse_duration(value: &str) -> Option<f64> {
    let parts = value
        .split(':')
        .map(str::parse::<u64>)
        .collect::<Result<Vec<_>, _>>()
        .ok()?;
    if parts.len() != 3 || parts[1] >= 60 || parts[2] >= 60 {
        return None;
    }
    let seconds = parts[0]
        .checked_mul(3600)?
        .checked_add(parts[1] * 60)?
        .checked_add(parts[2])?;
    (seconds > 0 && seconds <= 86400).then_some(seconds as f64)
}

#[cfg(test)]
mod duration_tests {
    use super::*;
    #[test]
    fn duration_from_detail_is_bounded_hms() {
        assert_eq!(parse_duration("00:04:09"), Some(249.0));
        for value in [
            "",
            "249",
            "00:99:00",
            "00:00:00",
            "99999999999999999999:00:00",
        ] {
            assert!(parse_duration(value).is_none());
        }
    }
}
