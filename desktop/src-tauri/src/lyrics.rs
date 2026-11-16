use crate::provider::common;
use base64::Engine;
use serde_json::{json, Value};
use std::collections::BTreeMap;

pub fn parse(raw: &str) -> Result<(Vec<Value>, Option<String>), String> {
    if raw.len() > 1024 * 1024 {
        return Err("歌词响应过大".into());
    }
    let stamp = regex::Regex::new(r"\[(\d{1,4}):([0-5]\d)(?:\.(\d{1,6}))?\]").unwrap();
    let metadata = regex::Regex::new(r"\[[^\]]*\]").unwrap();
    let offsets = regex::Regex::new(r"(?i)\[offset:([+-]?\d{1,9})\]").unwrap();
    let offset = offsets
        .captures_iter(raw)
        .last()
        .and_then(|c| c[1].parse::<i64>().ok())
        .unwrap_or(0);
    let mut grouped: BTreeMap<i64, Vec<String>> = BTreeMap::new();
    let mut plain = Vec::new();
    let mut count = 0;
    for row in raw.trim_start_matches('\u{feff}').lines() {
        let text = metadata.replace_all(row, "").trim().to_owned();
        let mut timed = false;
        for c in stamp.captures_iter(row) {
            timed = true;
            count += 1;
            if count > 10000 {
                return Err("歌词行数过多".into());
            }
            let fraction = c
                .get(3)
                .map(|m| {
                    format!("{:0<3}", m.as_str())
                        .chars()
                        .take(3)
                        .collect::<String>()
                })
                .unwrap_or("0".into());
            let time = (c[1].parse::<i64>().unwrap() * 60000
                + c[2].parse::<i64>().unwrap() * 1000
                + fraction.parse::<i64>().unwrap()
                + offset)
                .max(0);
            let texts = grouped.entry(time).or_default();
            if !texts.contains(&text) {
                texts.push(text.clone());
            }
        }
        if !timed && !text.is_empty() {
            plain.push(text);
            if plain.len() > 10000 {
                return Err("歌词行数过多".into());
            }
        }
    }
    let entries: Vec<_> = grouped.into_iter().collect();
    let lines=entries.iter().enumerate().map(|(i,(time,text))|json!({"startMs":time,"endMs":entries.get(i+1).map(|e|e.0),"text":text.join("\n")})).collect();
    Ok((lines, (!plain.is_empty()).then(|| plain.join("\n"))))
}
pub fn document(
    identity: &Value,
    raw: &str,
    translation: &str,
    instrumental: bool,
) -> Result<Value, String> {
    let (mut lines, plain) = parse(raw)?;
    let (translated, _) = parse(translation)?;
    let mut used = std::collections::HashSet::new();
    for line in &mut lines {
        let mut near: Vec<_> = translated
            .iter()
            .enumerate()
            .filter(|(i, t)| {
                !used.contains(i)
                    && (t["startMs"].as_i64().unwrap() - line["startMs"].as_i64().unwrap()).abs()
                        <= 20
            })
            .collect();
        near.sort_by_key(|(_, t)| {
            (t["startMs"].as_i64().unwrap() - line["startMs"].as_i64().unwrap()).abs()
        });
        if !near.is_empty()
            && (near.len() == 1
                || (near[0].1["startMs"].as_i64().unwrap() - line["startMs"].as_i64().unwrap())
                    .abs()
                    < (near[1].1["startMs"].as_i64().unwrap() - line["startMs"].as_i64().unwrap())
                        .abs())
        {
            used.insert(near[0].0);
            line["translation"] = near[0].1["text"].clone();
        }
    }
    let status = if !lines.is_empty() {
        "synced"
    } else if plain.is_some() {
        "plain"
    } else if instrumental {
        "instrumental"
    } else {
        "unavailable"
    };
    Ok(
        json!({"identity":identity,"status":status,"lines":lines,"plainText":plain,"sourceFormat":if status=="synced"{Some("lrc")}else if status=="plain"{Some("text")}else{None},
        "unalignedTranslation":if !translation.is_empty()&&(translated.is_empty()||used.len()!=translated.len()){Some(translation)}else{None}}),
    )
}
pub async fn get(client: &reqwest::Client, identity: &Value) -> Result<Value, String> {
    let source = identity["providerId"].as_str().ok_or("歌词来源无效")?;
    let id = identity["platformId"].as_str().ok_or("歌词身份无效")?;
    if !["qq", "netease", "kuwo", "migu"].contains(&source) || !common::valid_id(source, id) {
        return Err("歌词身份无效".into());
    }
    tokio::time::timeout(std::time::Duration::from_secs(12), async {
        match source {
            "qq" => {
                let data = common::json(
                    client
                        .get("https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg")
                        .header("Referer", "https://y.qq.com/portal/player.html")
                        .query(&[
                            ("songmid", id),
                            ("g_tk", "5381"),
                            ("loginUin", "0"),
                            ("hostUin", "0"),
                            ("format", "json"),
                            ("inCharset", "utf8"),
                            ("outCharset", "utf-8"),
                            ("platform", "yqq"),
                        ]),
                )
                .await?;
                if data["code"].as_i64().is_some_and(|c| c != 0) || !data["lyric"].is_string() {
                    return Err("QQ 歌词响应无效".into());
                }
                let decode = |v: &Value| -> Result<String, String> {
                    String::from_utf8(
                        base64::engine::general_purpose::STANDARD
                            .decode(v.as_str().unwrap_or(""))
                            .map_err(|_| "歌词编码无效")?,
                    )
                    .map_err(|_| "歌词文本无效".into())
                };
                document(
                    identity,
                    &decode(&data["lyric"])?,
                    &decode(&data["trans"])?,
                    false,
                )
            }
            "netease" => {
                let data = common::json(
                    client
                        .post("https://interface3.music.163.com/api/song/lyric")
                        .form(&[
                            ("id", id),
                            ("lv", "0"),
                            ("tv", "0"),
                            ("rv", "0"),
                            ("cp", "false"),
                            ("kv", "0"),
                            ("yv", "0"),
                            ("ytv", "0"),
                            ("yrv", "0"),
                        ]),
                )
                .await?;
                if data["code"] != 200
                    || !data.get("lrc").is_some()
                        && !data.get("nolyric").is_some()
                        && !data.get("uncollected").is_some()
                {
                    return Err("网易云歌词响应无效".into());
                }
                document(
                    identity,
                    data["lrc"]["lyric"].as_str().unwrap_or(""),
                    data["tlyric"]["lyric"].as_str().unwrap_or(""),
                    data["nolyric"] == true,
                )
            }
            "kuwo" => {
                let data = common::json(
                    client
                        .get("https://m.kuwo.cn/newh5/singles/songinfoandlrc")
                        .header("Referer", "https://m.kuwo.cn/")
                        .query(&[
                            ("musicId", id),
                            ("reqId", ""),
                            ("plat", "web"),
                            ("from", ""),
                        ]),
                )
                .await?;
                let rows = data["data"]["lrclist"]
                    .as_array()
                    .ok_or("酷我歌词响应无效")?;
                let mut raw = String::new();
                for row in rows {
                    let seconds = row["time"]
                        .as_f64()
                        .or_else(|| row["time"].as_str().and_then(|s| s.parse::<f64>().ok()))
                        .ok_or("歌词时间无效")?;
                    if !seconds.is_finite() || !(0.0..600000.0).contains(&seconds) {
                        return Err("歌词时间无效".into());
                    }
                    let ms = (seconds * 1000.0) as u64;
                    raw.push_str(&format!(
                        "[{:02}:{:02}.{:03}]{}\n",
                        ms / 60000,
                        ms / 1000 % 60,
                        ms % 1000,
                        row["lineLyric"].as_str().ok_or("歌词文本无效")?
                    ));
                }
                document(identity, &raw, "", false)
            }
            _ => {
                let data = crate::provider::migu::decode(
                    common::bytes(
                        crate::provider::migu::request(client, "/v1.0/content/resourceinfo.do")
                            .query(&[("resourceId", id), ("resourceType", "2")]),
                    )
                    .await?,
                )?;
                let rows = data["resource"].as_array().ok_or("咪咕歌词详情无效")?;
                if rows.len() != 1 || common::id(&rows[0]["contentId"]).as_deref() != Some(id) {
                    return Err("咪咕歌词身份不匹配".into());
                }
                let Some(url) = rows[0]["lrcUrl"].as_str().filter(|s| !s.is_empty()) else {
                    return document(identity, "", "", false);
                };
                let parsed = reqwest::Url::parse(url).map_err(|_| "歌词地址无效")?;
                if !matches!(parsed.scheme(), "https" | "http")
                    || parsed.host_str() != Some("d.musicapp.migu.cn")
                    || !parsed.username().is_empty()
                    || parsed.password().is_some()
                    || parsed.port().is_some_and(|p| p != 80 && p != 443)
                {
                    return Err("歌词地址不受支持".into());
                }
                let raw =
                    common::bytes(client.get(url).header("Referer", "https://y.migu.cn/")).await?;
                document(
                    identity,
                    std::str::from_utf8(&raw).map_err(|_| "歌词编码无效")?,
                    "",
                    false,
                )
            }
        }
    })
    .await
    .map_err(|_| "歌词获取超时，请重试")?
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn lrc_offsets_duplicates_and_translation() {
        let identity = json!({"providerId":"qq","platformId":"123"});
        let d = document(
            &identity,
            "[offset:-100]\n[00:01.12][00:02]甲\n[00:01.120]乙",
            "[00:01.020]译文",
            false,
        )
        .unwrap();
        assert_eq!(d["lines"][0]["startMs"], 1020);
        assert_eq!(d["lines"][0]["endMs"], 1900);
        assert_eq!(d["lines"][0]["text"], "甲\n乙");
        assert_eq!(d["lines"][0]["translation"], "译文");
        assert_eq!(
            document(&identity, "", "", false).unwrap()["status"],
            "unavailable"
        );
        assert_eq!(
            document(&identity, "纯文本", "", false).unwrap()["status"],
            "plain"
        );
        assert_eq!(
            document(&identity, "", "", true).unwrap()["status"],
            "instrumental"
        );
    }
    #[tokio::test]
    #[ignore = "真实四来源歌词和封面探测，失败单独记录"]
    async fn online_metadata() {
        let client = reqwest::Client::builder()
            .user_agent("Mozilla/5.0")
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .unwrap();
        for (source, id, query) in [
            ("qq", "0027oMO61wWi55", "发如雪 周杰伦"),
            ("qq", "0037WF7I0yUPLu", "发如雪 周杰伦"),
            ("kuwo", "228908", "晴天"),
            ("netease", "2668397359", "晴天"),
            ("migu", "600919000007741344", "晴天"),
        ] {
            let identity = json!({"providerId":source,"platformId":id});
            match get(&client, &identity).await {
                Ok(d) => println!(
                    "{source}/{id} lyrics={} lines={}",
                    d["status"],
                    d["lines"].as_array().unwrap().len()
                ),
                Err(e) => println!("{source}/{id} lyrics_error={e}"),
            }
            match crate::provider::search(
                &client,
                &json!({"providerId":source,"query":query,"limit":15}),
            )
            .await
            {
                Ok(page) => {
                    let row = page["items"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .find(|r| r["identity"] == identity);
                    println!(
                        "{source}/{id} cover_mapped={} trusted={}",
                        row.is_some_and(|r| r["cover"].as_str().is_some_and(|s| !s.is_empty())),
                        row.is_some_and(|r| r["cover"]
                            .as_str()
                            .is_some_and(|s| crate::covers::valid_url(source, s)))
                    );
                }
                Err(e) => println!("{source}/{id} search_error={e}"),
            }
        }
    }
}
