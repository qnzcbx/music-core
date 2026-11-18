use super::common;
use serde_json::{json, Value};
fn check(data: Value) -> Result<Value, String> {
    match data["code"].as_i64() {
        Some(200) => Ok(data),
        Some(301 | 401 | 403) => Err("网易云当前接口需要登录或访问权限".into()),
        _ => Err("网易云服务暂不可用".into()),
    }
}
pub fn candidate(row: &Value) -> Option<Value> {
    common::candidate(
        "netease",
        common::id(&row["id"])?,
        &row["name"],
        &row["ar"],
        row["al"]["name"].clone(),
        row["dt"].as_f64().map(|n| n / 1000.0),
        row["al"]["picUrl"].clone(),
    )
}
pub async fn search(client: &reqwest::Client, body: &Value) -> Result<Value, String> {
    let (query, limit, page) = common::page(body)?;
    let data = check(
        common::json(
            client
                .post("https://music.163.com/api/cloudsearch/pc")
                .header("Referer", "https://music.163.com/")
                .form(&[
                    ("s", query),
                    ("type", "1".into()),
                    ("limit", limit.to_string()),
                    ("offset", ((page - 1) * limit).to_string()),
                ]),
        )
        .await?,
    )?;
    let rows = if data["result"]["songCount"] == 0 {
        json!([])
    } else {
        data["result"]["songs"].clone()
    };
    common::result(&rows, &data["result"]["songCount"], limit, page, candidate)
}
pub fn media(data: Value, id: &str) -> Result<String, String> {
    let data = check(data)?;
    let rows = data["data"].as_array().ok_or("网易云媒体响应格式异常")?;
    if rows.len() != 1 || common::id(&rows[0]["id"]).as_deref() != Some(id) {
        return Err("网易云返回歌曲身份不匹配".into());
    }
    let row = &rows[0];
    if matches!(row["code"].as_i64(), Some(301 | 401 | 403)) {
        return Err("网易云歌曲访问权限不足".into());
    }
    let url = row["url"].as_str().filter(|url| !url.is_empty());
    if !row["freeTrialInfo"].is_null() {
        return Err("该歌曲仅提供试听，桌面版不作为完整曲目播放".into());
    }
    // -110 + 空链接是已观察到的原生取链失败。和 Python 一样，允许既有备用路线继续验证。
    if row["code"] == -110 && url.is_none() {
        return Err("该歌曲未提供匿名可播放媒体".into());
    }
    if row["code"] != 200 {
        return Err("网易云未返回成功的媒体解析结果".into());
    }
    url.map(str::to_owned)
        .ok_or_else(|| "该歌曲未提供匿名可播放媒体".into())
}
pub async fn resolve(client: &reqwest::Client, id: &str) -> Result<String, String> {
    resolve_quality(client, id, "standard").await
}
pub async fn resolve_quality(
    client: &reqwest::Client,
    id: &str,
    quality: &str,
) -> Result<String, String> {
    media(
        common::json(
            client
                .post("https://music.163.com/api/song/enhance/player/url")
                .header("Referer", "https://music.163.com/")
                .form(&[
                    ("ids", format!("[{id}]")),
                    (
                        "br",
                        match quality {
                            "high" => "320000",
                            "lossless" => "999000",
                            _ => "128000",
                        }
                        .into(),
                    ),
                ]),
        )
        .await?,
        id,
    )
}
