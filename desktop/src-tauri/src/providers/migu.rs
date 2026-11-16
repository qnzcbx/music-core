use super::common;
use serde_json::{json, Value};
const ROOT: &str = "https://c.musicapp.migu.cn";
fn request(client: &reqwest::Client, path: &str) -> reqwest::RequestBuilder {
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
            return Err("咪咕响应格式异常".into());
        }
        let key = b"Jk8qzuePiJ1qE3mDYhLQ3T73DtDoAhLP";
        let seed = bytes[3];
        bytes = bytes[4..]
            .iter()
            .enumerate()
            .map(|(i, b)| b.wrapping_add(seed).wrapping_sub(key[i % key.len()]))
            .collect();
    }
    let data: Value = serde_json::from_slice(&bytes).map_err(|_| "咪咕响应格式异常")?;
    if data
        .get("code")
        .or(data.get("returnCode"))
        .is_some_and(|c| {
            !matches!(c.as_str(), Some("0" | "000000" | "200"))
                && !matches!(c.as_i64(), Some(0 | 200))
        })
    {
        return Err("咪咕拒绝当前访问或服务暂不可用".into());
    }
    Ok(data)
}
pub fn candidate(row: &Value) -> Option<Value> {
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
        Value::Null,
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
pub fn context(data: &Value, id: &str) -> Result<(String, String, String), String> {
    let rows = data["resource"].as_array().ok_or("咪咕歌曲详情格式异常")?;
    if rows.len() != 1 || common::id(&rows[0]["contentId"]).as_deref() != Some(id) {
        return Err("咪咕歌曲身份不匹配".into());
    }
    let row = &rows[0];
    if !row["needEncrypt"].is_null()
        && !matches!(row["needEncrypt"], Value::Bool(false))
        && row["needEncrypt"] != 0
        && row["needEncrypt"] != "0"
    {
        return Err("咪咕加密媒体暂不支持".into());
    }
    let copyright = common::id(&row["copyrightId"])
        .filter(|s| !s.is_empty() && s.len() <= 64 && s.bytes().all(|c| c.is_ascii_alphanumeric()))
        .ok_or("咪咕版权身份缺失")?;
    for tone in ["PQ", "LQ", "HQ"] {
        for field in ["rateFormats", "newRateFormats", "audioFormats"] {
            for f in row[field].as_array().into_iter().flatten() {
                if f["formatType"] == tone {
                    if let Some(resource) =
                        common::id(&f["resourceType"]).filter(|s| common::valid_id("migu", s))
                    {
                        return Ok((copyright, tone.into(), resource));
                    }
                }
            }
        }
    }
    Err("咪咕未提供普通可播放格式".into())
}
pub fn media(data: Value, id: &str, copyright: &str) -> Result<String, String> {
    let body = &data["data"];
    if common::id(&body["song"]["contentId"]).as_deref() != Some(id)
        || common::id(&body["song"]["copyrightId"]).as_deref() != Some(copyright)
    {
        return Err("咪咕媒体身份不匹配".into());
    }
    if body["audioFormatType"]
        .as_str()
        .is_some_and(|s| !matches!(s, "PQ" | "LQ" | "HQ"))
    {
        return Err("咪咕媒体格式暂不支持".into());
    }
    if !body["freeListenType"].is_null()
        && body["freeListenType"] != 0
        && body["freeListenType"] != "0"
        && body["freeListenType"] != false
    {
        return Err("咪咕仅提供试听，不能作为完整曲目播放".into());
    }
    body["url"]
        .as_str()
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .ok_or("咪咕未提供匿名可播放媒体".into())
}
pub async fn resolve(client: &reqwest::Client, id: &str) -> Result<String, String> {
    let detail = decode(
        common::bytes(
            request(client, "/v1.0/content/resourceinfo.do")
                .query(&[("resourceId", id), ("resourceType", "2")]),
        )
        .await?,
    )?;
    let (copyright, tone, resource) = context(&detail, id)?;
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
    media(data, id, &copyright)
}
