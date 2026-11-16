use super::common;
use serde_json::{json, Value};
pub fn candidate(row: &Value) -> Option<Value> {
    let album_mid = row["album"]["mid"].as_str().or(row["albummid"].as_str());
    let cover = album_mid
        .filter(|s| !s.is_empty() && s.len() <= 64 && s.bytes().all(|c| c.is_ascii_alphanumeric()))
        .map(|mid| format!("https://y.gtimg.cn/music/photo_new/T002R500x500M000{mid}.jpg"));
    let id = row["mid"].as_str().or(row["songmid"].as_str())?;
    let title = row
        .get("title")
        .or(row.get("songname"))
        .or(row.get("name"))?;
    common::candidate(
        "qq",
        id.into(),
        title,
        &row["singer"],
        row["album"]
            .get("title")
            .or(row["album"].get("name"))
            .or(row.get("albumname"))
            .cloned()
            .unwrap_or(Value::Null),
        row["interval"].as_f64(),
        json!(cover),
    )
}
pub async fn search(client: &reqwest::Client, body: &Value) -> Result<Value, String> {
    let (query, limit, page) = common::page(body)?;
    let data = common::json(
        client
            .get("https://c.y.qq.com/soso/fcgi-bin/client_search_cp")
            .header("Referer", "https://y.qq.com/")
            .query(&[
                ("w", query),
                ("p", page.to_string()),
                ("n", limit.to_string()),
                ("format", "json".into()),
                ("t", "0".into()),
                ("platform", "yqq.json".into()),
                ("new_json", "1".into()),
            ]),
    )
    .await?;
    if data["code"].as_i64().is_some_and(|n| n != 0) {
        return Err("QQ 搜索被来源拒绝，请稍后重试".into());
    }
    common::result(
        &data["data"]["song"]["list"],
        &data["data"]["song"]["totalnum"],
        limit,
        page,
        candidate,
    )
}
pub fn media(data: Value, id: &str) -> Result<String, String> {
    let result = &data["req_0"];
    if data["code"].as_i64().is_some_and(|n| n != 0) || result["code"] != 0 {
        return Err("QQ 官方接口拒绝当前匿名上下文".into());
    }
    let rows = result["data"]["midurlinfo"]
        .as_array()
        .ok_or("QQ 媒体响应格式异常")?;
    if rows.len() != 1 || rows[0]["songmid"] != id {
        return Err("QQ 返回歌曲身份不匹配".into());
    }
    let row = &rows[0];
    if matches!(row["result"].as_i64(), Some(301 | 401 | 403)) {
        return Err("QQ 歌曲访问权限不足".into());
    }
    let purl = row["purl"]
        .as_str()
        .filter(|s| !s.is_empty())
        .or(row["wifiurl"].as_str().filter(|s| !s.is_empty()))
        .ok_or("QQ 未提供匿名可播放媒体，请选择其他曲目")?;
    let base = result["data"]["sip"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .find(|s| s.starts_with("http"));
    if purl.starts_with("http://") || purl.starts_with("https://") {
        return Ok(purl.into());
    }
    reqwest::Url::parse(base.ok_or("QQ 媒体地址缺失")?)
        .and_then(|u| u.join(purl))
        .map(|u| u.to_string())
        .map_err(|_| "QQ 媒体地址无效".into())
}
pub async fn resolve(client: &reqwest::Client, id: &str) -> Result<String, String> {
    let guid = uuid::Uuid::new_v4().as_u128() % 9_000_000_000 + 1_000_000_000;
    let payload = json!({"comm":{"ct":24,"cv":0,"format":"json","uin":"0"},"req_0":{"module":"music.vkey.GetVkey","method":"UrlGetVkey","param":{"songmid":[id],"songtype":[0],"guid":guid.to_string(),"uin":"0","loginflag":0,"platform":"20"}}});
    media(
        common::json(
            client
                .get("https://u.y.qq.com/cgi-bin/musicu.fcg")
                .header("Referer", "https://y.qq.com/")
                .query(&[("data", payload.to_string())]),
        )
        .await?,
        id,
    )
}
