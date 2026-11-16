#[path = "common.rs"]
pub(crate) mod common;
#[path = "providers/kuwo.rs"]
mod kuwo;
#[path = "providers/migu.rs"]
mod migu;
#[path = "providers/netease.rs"]
mod netease;
#[path = "providers/qq.rs"]
mod qq;
use serde_json::{json, Value};

pub struct Media {
    pub url: String,
    pub headers: reqwest::header::HeaderMap,
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn maps_sources_without_colliding_numeric_ids() {
        let a = netease::candidate(
            &json!({"id":123,"name":"歌","dt":120000,"ar":[{"name":"甲"}],"al":{"name":"专辑"}}),
        )
        .unwrap();
        let b = migu::candidate(
            &json!({"contentId":"123","name":"歌","duration":120,"singers":[{"name":"甲"}]}),
        )
        .unwrap();
        let c = qq::candidate(
            &json!({"mid":"123","title":"歌","interval":120,"singer":[{"name":"甲"}]}),
        )
        .unwrap();
        assert_ne!(a["identity"], b["identity"]);
        assert_ne!(b["identity"], c["identity"]);
        for row in [a, b, c] {
            assert_eq!(row["durationSeconds"], 120.0);
            assert_eq!(row["artists"], json!(["甲"]));
        }
        assert!(netease::candidate(&json!({"id":true,"name":"歌"})).is_none());
        assert!(qq::candidate(&json!({"mid":"../123","title":"歌"})).is_none());
    }
    #[test]
    fn cursors_and_media_permissions() {
        for source in ["netease", "qq", "migu"] {
            assert_eq!(
                common::page(&json!({"providerId":source,"query":"歌","limit":15,"cursor":"2:15"}))
                    .unwrap()
                    .2,
                2
            );
            assert!(common::page(&json!({"query":"歌","limit":15,"cursor":"2:10"})).is_err());
        }
        assert!(netease::media(json!({"code":301}), "123")
            .unwrap_err()
            .contains("登录"));
        assert!(netease::media(json!({"code":200,"data":[{"id":123,"code":200,"url":"https://m701.music.126.net/a.mp3","freeTrialInfo":{}}]}),"123").is_err());
        assert!(qq::media(json!({"code":0,"req_0":{"code":0,"data":{"midurlinfo":[{"songmid":"456","purl":"a"}]}}}),"123").is_err());
        assert!(migu::media(json!({"data":{"song":{"contentId":"123","copyrightId":"A"},"url":"x","freeListenType":1}}),"123","A").is_err());
        assert!(common::validate_media("qq", "https://evil.invalid/a.mp3").is_err());
        assert!(common::validate_media("netease", "https://m701.music.126.net/a.mp3").is_ok());
        let page = common::result(
            &json!([{"mid":"123","title":"歌"},{"mid":"123","title":"歌"}]),
            &json!(3),
            2,
            1,
            qq::candidate,
        )
        .unwrap();
        assert_eq!(page["items"].as_array().unwrap().len(), 1);
        assert_eq!(page["nextCursor"], "2:2");
    }
    #[test]
    fn migu_response_and_dual_identity() {
        assert!(migu::decode(vec![0xab, 0xcd, 1]).is_err());
        let detail = json!({"resource":[{"contentId":"123","copyrightId":"A","rateFormats":[{"formatType":"PQ","resourceType":"2"}]}]});
        assert_eq!(
            migu::context(&detail, "123").unwrap(),
            ("A".into(), "PQ".into(), "2".into())
        );
        assert!(migu::context(&detail, "124").is_err());
    }
    #[tokio::test]
    #[ignore = "真实来源网络验收，不把外部失败视为 fixture 通过"]
    async fn online_sources() {
        let client = reqwest::Client::builder()
            .user_agent("Mozilla/5.0")
            .redirect(reqwest::redirect::Policy::none())
            .read_timeout(std::time::Duration::from_secs(20))
            .build()
            .unwrap();
        for source in ["netease", "qq", "migu"] {
            let page = match search(
                &client,
                &json!({"providerId":source,"query":"晴天","limit":3}),
            )
            .await
            {
                Ok(page) => page,
                Err(error) => {
                    println!("{source}: 搜索失败：{error}");
                    continue;
                }
            };
            println!(
                "{source}: 搜索 {} 首",
                page["items"].as_array().unwrap().len()
            );
            for item in page["items"].as_array().unwrap().iter().take(3) {
                let identity = &item["identity"];
                let media = match resolve(&client, identity).await {
                    Ok(media) => media,
                    Err(error) => {
                        println!("{identity}: 解析失败：{error}");
                        continue;
                    }
                };
                let sessions = crate::sessions::Sessions::new();
                let id = sessions.insert_media(media);
                let port = crate::transport::start(crate::transport::Transport {
                    sessions: sessions.clone(),
                    client: client.clone(),
                })
                .await
                .unwrap();
                let url = format!("http://127.0.0.1:{port}/api/playback/{id}/stream");
                for range in ["bytes=0-1023", "bytes=300000-301023"] {
                    match client.get(&url).header("Range", range).send().await {
                        Ok(response) => {
                            println!(
                                "{identity}: {range} status={} content-range={:?}",
                                response.status(),
                                response.headers().get("content-range")
                            );
                            let _ = response.bytes().await;
                        }
                        Err(_) => println!("{identity}: 媒体请求失败"),
                    }
                }
                sessions.close(&id);
            }
        }
    }
}

pub fn catalog() -> Value {
    json!([
        ("kuwo", "酷我"),
        ("qq", "QQ 音乐"),
        ("netease", "网易云音乐"),
        ("migu", "咪咕音乐")
    ]
    .iter()
    .enumerate()
    .map(
        |(order, (id, name))| json!({"id":id,"name":name,"order":order,
        "defaultSelected":*id=="kuwo","implementationStatus":"native-anonymous",
        "reason":"官方匿名接口；曲目权限及网络条件决定能否播放",
        "capabilities":{"search":true,"resolve":true,"lyrics":false,"download":false}})
    )
    .collect::<Vec<_>>())
}

pub async fn search(client: &reqwest::Client, body: &Value) -> Result<Value, String> {
    tokio::time::timeout(std::time::Duration::from_secs(18), async {
        match body["providerId"].as_str() {
            Some("kuwo") => kuwo::search(client, body).await,
            Some("netease") => netease::search(client, body).await,
            Some("qq") => qq::search(client, body).await,
            Some("migu") => migu::search(client, body).await,
            _ => Err("来源无效".into()),
        }
    })
    .await
    .map_err(|_| "来源搜索超时，请稍后重试")?
}

pub async fn resolve(client: &reqwest::Client, identity: &Value) -> Result<Media, String> {
    tokio::time::timeout(std::time::Duration::from_secs(20), async {
        let source = identity["providerId"].as_str().ok_or("歌曲来源无效")?;
        let id = identity["platformId"].as_str().ok_or("歌曲身份无效")?;
        if !common::valid_id(source, id) {
            return Err("歌曲身份无效".into());
        }
        let url = match source {
            "kuwo" => kuwo::resolve(client, identity).await?,
            "netease" => netease::resolve(client, id).await?,
            "qq" => qq::resolve(client, id).await?,
            "migu" => migu::resolve(client, id).await?,
            _ => return Err("来源无效".into()),
        };
        common::validate_media(source, &url)?;
        let mut headers = reqwest::header::HeaderMap::new();
        let (agent, referer) = match source {
            "kuwo" => ("okhttp/3.10.0", "https://www.kuwo.cn/"),
            "netease" => ("Mozilla/5.0", "https://music.163.com/"),
            "qq" => ("Mozilla/5.0", "https://y.qq.com/"),
            _ => ("Mozilla/5.0", "https://h5.nf.migu.cn/"),
        };
        headers.insert("user-agent", agent.parse().unwrap());
        headers.insert("referer", referer.parse().unwrap());
        Ok(Media { url, headers })
    })
    .await
    .map_err(|_| "歌曲解析超时，请稍后重试")?
}
