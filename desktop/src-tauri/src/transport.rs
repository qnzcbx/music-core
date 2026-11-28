use crate::sessions::Sessions;
use axum::{
    body::Body,
    extract::{Path, State},
    http::{HeaderMap, Method, StatusCode},
    response::{IntoResponse, Response},
    routing::get,
    Router,
};
use futures_util::StreamExt;

#[derive(Clone)]
pub struct Transport {
    pub sessions: Sessions,
    pub client: reqwest::Client,
}

fn decimal(value: &str) -> Option<u64> {
    if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    value.parse().ok()
}

pub fn valid_range(value: &str) -> bool {
    let Some((start, end)) = value
        .strip_prefix("bytes=")
        .and_then(|value| value.split_once('-'))
    else {
        return false;
    };
    if start.is_empty() {
        return decimal(end).is_some_and(|length| length > 0);
    }
    decimal(start)
        .is_some_and(|start| end.is_empty() || decimal(end).is_some_and(|end| end >= start))
}

fn expected_media_length(
    status: StatusCode,
    headers: &HeaderMap,
    range: Option<&str>,
) -> Result<Option<u64>, ()> {
    fn header<'a>(headers: &'a HeaderMap, key: &str) -> Result<Option<&'a str>, ()> {
        let mut values = headers.get_all(key).iter();
        let first = values
            .next()
            .map(|value| value.to_str().map_err(|_| ()))
            .transpose()?;
        if values.next().is_some() {
            return Err(());
        }
        Ok(first)
    }
    if header(headers, "content-encoding")?
        .is_some_and(|value| !value.eq_ignore_ascii_case("identity"))
    {
        return Err(());
    }
    if status != StatusCode::RANGE_NOT_SATISFIABLE
        && header(headers, "content-type")?.is_some_and(|value| {
            let mime = value.to_ascii_lowercase();
            mime.contains("html") || mime.contains("json")
        })
    {
        return Err(());
    }
    let length = header(headers, "content-length")?
        .map(|value| decimal(value).ok_or(()))
        .transpose()?;
    if status == StatusCode::OK {
        return Ok(length);
    }
    let supplied = header(headers, "content-range")?;
    if status == StatusCode::RANGE_NOT_SATISFIABLE {
        if let Some(value) = supplied {
            value.strip_prefix("bytes */").and_then(decimal).ok_or(())?;
        }
        return Ok(length);
    }
    let (bounds, total) = supplied
        .and_then(|value| value.strip_prefix("bytes "))
        .and_then(|value| value.split_once('/'))
        .ok_or(())?;
    let (first, last) = bounds.split_once('-').ok_or(())?;
    let (first, last) = (decimal(first).ok_or(())?, decimal(last).ok_or(())?);
    let total = if total == "*" {
        None
    } else {
        Some(decimal(total).ok_or(())?)
    };
    let span = last
        .checked_sub(first)
        .and_then(|span| span.checked_add(1))
        .ok_or(())?;
    if length.is_some_and(|length| length != span) || total.is_some_and(|total| last >= total) {
        return Err(());
    }
    if let Some((start, end)) = range
        .and_then(|value| value.strip_prefix("bytes="))
        .and_then(|value| value.split_once('-'))
    {
        if let Some(start) = decimal(start) {
            if start != first || decimal(end).is_some_and(|end| last > end) {
                return Err(());
            }
        } else if total.zip(decimal(end)).is_some_and(|(total, suffix)| {
            first != total.saturating_sub(suffix) || last != total - 1
        }) {
            return Err(());
        }
    }
    Ok(Some(span))
}

fn local_range(range: &str, size: u64) -> Option<(u64, u64)> {
    if size == 0 || !valid_range(range) {
        return None;
    }
    let (start, end) = range.strip_prefix("bytes=")?.split_once('-')?;
    if start.is_empty() {
        return Some((size.saturating_sub(end.parse().ok()?), size - 1));
    }
    let start = start.parse::<u64>().ok()?;
    let end = end.parse::<u64>().unwrap_or(size - 1).min(size - 1);
    (start <= end).then_some((start, end))
}

async fn local_stream(
    path: &std::path::Path,
    mime: &str,
    method: Method,
    headers: HeaderMap,
    cancel: tokio_util::sync::CancellationToken,
) -> Response {
    use tokio::io::{AsyncReadExt, AsyncSeekExt};
    let Ok(mut file) = tokio::fs::File::open(path).await else {
        return StatusCode::GONE.into_response();
    };
    let Ok(metadata) = file.metadata().await else {
        return StatusCode::GONE.into_response();
    };
    if !metadata.is_file() || metadata.len() == 0 || cancel.is_cancelled() {
        return StatusCode::GONE.into_response();
    }
    let size = metadata.len();
    let mut response = Response::builder()
        .header("Accept-Ranges", "bytes")
        .header("Cache-Control", "no-store")
        .header("Content-Type", mime);
    let (start, length) = if let Some(range) = headers.get("range") {
        let Some((start, end)) = range
            .to_str()
            .ok()
            .and_then(|value| local_range(value, size))
        else {
            return response
                .status(StatusCode::RANGE_NOT_SATISFIABLE)
                .header("Content-Range", format!("bytes */{size}"))
                .body(Body::empty())
                .unwrap();
        };
        response = response
            .status(StatusCode::PARTIAL_CONTENT)
            .header("Content-Range", format!("bytes {start}-{end}/{size}"));
        (start, end - start + 1)
    } else {
        (0, size)
    };
    response = response.header("Content-Length", length);
    if method == Method::HEAD {
        return response.body(Body::empty()).unwrap();
    }
    if file.seek(std::io::SeekFrom::Start(start)).await.is_err() {
        return StatusCode::GONE.into_response();
    }
    let chunks = futures_util::stream::try_unfold(
        (file.take(length), cancel),
        |(mut file, cancel)| async move {
            let mut buffer = vec![0; 65536];
            let count = tokio::select! {
                _ = cancel.cancelled() => return Ok::<_,std::io::Error>(None),
                count = file.read(&mut buffer) => count?,
            };
            if count == 0 {
                return Ok(None);
            }
            buffer.truncate(count);
            Ok(Some((buffer, (file, cancel))))
        },
    );
    response.body(Body::from_stream(chunks)).unwrap()
}

async fn stream(
    State(state): State<Transport>,
    Path(id): Path<String>,
    method: Method,
    headers: HeaderMap,
) -> Response {
    let Some(session) = state.sessions.get(&id) else {
        return StatusCode::GONE.into_response();
    };
    if let Some((path, mime)) = session.local {
        return local_stream(&path, mime, method, headers, session.cancel).await;
    }
    let mut request = state
        .client
        .request(method.clone(), &session.url)
        .headers(session.headers.clone())
        .header("Accept-Encoding", "identity");
    let range = if let Some(range) = headers.get("range") {
        let Some(range) = range.to_str().ok().filter(|range| valid_range(range)) else {
            return StatusCode::RANGE_NOT_SATISFIABLE.into_response();
        };
        if headers.get_all("range").iter().count() != 1 {
            return StatusCode::RANGE_NOT_SATISFIABLE.into_response();
        }
        request = request.header("Range", range);
        if let Some(condition) = headers
            .get("if-range")
            .and_then(|value| value.to_str().ok())
            .filter(|value| value.len() <= 200 && !value.starts_with("W/"))
        {
            request = request.header("If-Range", condition);
        }
        Some(range)
    } else {
        None
    };
    let upstream = tokio::select! {
        _ = session.cancel.cancelled() => return StatusCode::GONE.into_response(),
        result = request.send() => match result {
            Ok(response) => response,
            Err(_) => return StatusCode::BAD_GATEWAY.into_response(),
        }
    };
    let status = upstream.status();
    match status.as_u16() {
        401 | 403 => return StatusCode::FORBIDDEN.into_response(),
        404 | 410 => return StatusCode::GONE.into_response(),
        200 | 206 | 416 => {}
        _ => return StatusCode::BAD_GATEWAY.into_response(),
    }
    let Ok(expected) = expected_media_length(status, upstream.headers(), range) else {
        return StatusCode::BAD_GATEWAY.into_response();
    };
    let mut response = Response::builder()
        .status(status)
        .header("Cache-Control", "no-store")
        .header("Access-Control-Allow-Origin", "*");
    for name in [
        "content-type",
        "content-length",
        "content-range",
        "accept-ranges",
        "etag",
        "last-modified",
    ] {
        if name == "content-range" && status == StatusCode::OK {
            continue;
        }
        if let Some(value) = upstream.headers().get(name) {
            response = response.header(name, value);
        }
    }
    if method == Method::HEAD {
        return response.body(Body::empty()).unwrap();
    }
    // 取消会打断等待中的上游读取；Body 被 WebView 丢弃时也立即释放连接。
    let bytes = upstream.bytes_stream();
    let body = futures_util::stream::try_unfold(
        (Box::pin(bytes), session.cancel, expected),
        |(mut bytes, cancel, remaining)| async move {
            let next = tokio::select! {
                _ = cancel.cancelled() => return Ok(None),
                chunk = bytes.next() => chunk,
            };
            match next {
                Some(Ok(chunk)) => {
                    let remaining = remaining
                        .map(|length| {
                            length
                                .checked_sub(chunk.len() as u64)
                                .ok_or_else(|| std::io::Error::other("上游媒体长度超出声明"))
                        })
                        .transpose()?;
                    Ok(Some((chunk, (bytes, cancel, remaining))))
                }
                Some(Err(_)) => Err(std::io::Error::other("上游媒体传输中断")),
                None if remaining.is_some_and(|length| length != 0) => {
                    Err(std::io::Error::other("上游媒体传输不完整"))
                }
                None => Ok(None),
            }
        },
    );
    response.body(Body::from_stream(body)).unwrap()
}

#[cfg(test)]
pub async fn start(state: Transport) -> std::io::Result<u16> {
    start_with_covers(state, crate::covers::Covers::default()).await
}
pub async fn start_with_covers(
    state: Transport,
    covers: crate::covers::Covers,
) -> std::io::Result<u16> {
    let listener = tokio::net::TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, 0)).await?;
    let port = listener.local_addr()?.port();
    let app = Router::new()
        .route("/api/playback/{id}/stream", get(stream))
        .with_state(state)
        .merge(covers.router());
    tokio::spawn(async move {
        let _ = axum::serve(listener, app).await;
    });
    Ok(port)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn local_session_serves_file_ranges_and_expires_on_close() {
        let root = tempfile::tempdir().unwrap();
        let file = root.path().join("registered.flac");
        std::fs::write(&file, b"0123456789").unwrap();
        let sessions = Sessions::new();
        let id = sessions.insert_local(file, "audio/flac");
        let client = reqwest::Client::new();
        let port = start(Transport {
            sessions: sessions.clone(),
            client: client.clone(),
        })
        .await
        .unwrap();
        let url = format!("http://127.0.0.1:{port}/api/playback/{id}/stream");
        let head = client.head(&url).send().await.unwrap();
        assert_eq!(head.headers()["content-length"], "10");
        let partial = client
            .get(&url)
            .header("range", "bytes=4-6")
            .send()
            .await
            .unwrap();
        assert_eq!(partial.status(), 206);
        assert_eq!(partial.headers()["content-range"], "bytes 4-6/10");
        assert_eq!(partial.text().await.unwrap(), "456");
        let invalid = client
            .get(&url)
            .header("range", "bytes=10-")
            .send()
            .await
            .unwrap();
        assert_eq!(invalid.status(), 416);
        sessions.close(&id);
        assert_eq!(client.get(&url).send().await.unwrap().status(), 410);
    }

    #[tokio::test]
    async fn preserves_non_range_response_and_maps_rate_limit() {
        let upstream = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = upstream.local_addr().unwrap();
        tokio::spawn(async move {
            axum::serve(
                upstream,
                Router::new()
                    .route("/whole", get(|| async { "whole" }))
                    .route("/limited", get(|| async { StatusCode::TOO_MANY_REQUESTS })),
            )
            .await
            .unwrap();
        });
        let client = reqwest::Client::new();
        assert_eq!(
            crate::provider::common::bytes(client.get(format!("http://{address}/limited")))
                .await
                .unwrap_err(),
            "upstream_rate_limited"
        );
        let sessions = Sessions::new();
        let id = sessions.insert(format!("http://{address}/whole"));
        let port = start(Transport {
            sessions,
            client: client.clone(),
        })
        .await
        .unwrap();
        let response = client
            .get(format!("http://127.0.0.1:{port}/api/playback/{id}/stream"))
            .header("Range", "bytes=1-2")
            .send()
            .await
            .unwrap();
        assert_eq!(response.status(), 200);
        assert!(!response.headers().contains_key("content-range"));
        assert_eq!(response.text().await.unwrap(), "whole");
    }
    #[tokio::test]
    async fn shared_stream_contract_exercises_head_and_get() {
        use serde::Deserialize;
        use std::collections::BTreeMap;

        #[derive(Clone, Deserialize)]
        struct Case {
            range: Option<String>,
            upstream: u16,
            headers: BTreeMap<String, String>,
            body: String,
            status: u16,
        }
        let cases: Vec<Case> = serde_json::from_str(include_str!(
            "../../../tests/fixtures/contracts/playback-stream.json"
        ))
        .unwrap();
        let upstream = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = upstream.local_addr().unwrap();
        let fixtures = cases.clone();
        let server = tokio::spawn(async move {
            axum::serve(
                upstream,
                Router::new().route(
                    "/{index}",
                    get(move |Path(index): Path<usize>| {
                        let case = fixtures[index].clone();
                        async move {
                            let mut response = Response::builder().status(case.upstream);
                            for (name, value) in case.headers {
                                response = response.header(name, value);
                            }
                            response.body(Body::from(case.body)).unwrap()
                        }
                    }),
                ),
            )
            .await
            .unwrap();
        });
        let client = reqwest::Client::new();
        let sessions = Sessions::new();
        let port = start(Transport {
            sessions: sessions.clone(),
            client: client.clone(),
        })
        .await
        .unwrap();
        for (index, case) in cases.iter().enumerate() {
            let id = sessions.insert(format!("http://{address}/{index}"));
            let url = format!("http://127.0.0.1:{port}/api/playback/{id}/stream");
            for method in [Method::HEAD, Method::GET] {
                let mut request = client.request(method.clone(), &url);
                if let Some(range) = &case.range {
                    request = request.header("range", range);
                }
                let response = request.send().await.unwrap();
                assert_eq!(
                    response.status().as_u16(),
                    case.status,
                    "fixture {index} {method}"
                );
                if case.status == 200 {
                    assert!(!response.headers().contains_key("content-range"));
                }
                if method == Method::HEAD {
                    assert!(response.bytes().await.unwrap().is_empty());
                } else if case.status < 400 || case.status == 416 {
                    assert_eq!(response.text().await.unwrap(), case.body);
                }
            }
            sessions.close(&id);
        }
        server.abort();
    }

    #[test]
    fn validates_single_ranges() {
        for range in ["bytes=0-1", "bytes=1024-", "bytes=-256"] {
            assert!(valid_range(range));
        }
        for range in [
            "bytes=-0",
            "bytes=2-1",
            "bytes=0-1,4-5",
            "bytes=-",
            "garbage",
        ] {
            assert!(!valid_range(range));
        }
    }
    #[tokio::test]
    async fn forwards_real_partial_response_and_releases_session() {
        let upstream = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = upstream.local_addr().unwrap();
        tokio::spawn(async move {
            axum::serve(
                upstream,
                Router::new().route(
                    "/",
                    get(|headers: HeaderMap| async move {
                        assert_eq!(headers["range"], "bytes=2-4");
                        (
                            StatusCode::PARTIAL_CONTENT,
                            [
                                ("content-range", "bytes 2-4/10"),
                                ("accept-ranges", "bytes"),
                            ],
                            "234",
                        )
                    }),
                ),
            )
            .await
            .unwrap();
        });
        let sessions = Sessions::new();
        let id = sessions.insert(format!("http://{address}/"));
        let client = reqwest::Client::new();
        let port = start(Transport {
            sessions: sessions.clone(),
            client: client.clone(),
        })
        .await
        .unwrap();
        let url = format!("http://127.0.0.1:{port}/api/playback/{id}/stream");
        let response = client
            .get(&url)
            .header("Range", "bytes=2-4")
            .send()
            .await
            .unwrap();
        assert_eq!(response.status(), 206);
        assert_eq!(response.headers()["content-range"], "bytes 2-4/10");
        assert_eq!(response.text().await.unwrap(), "234");
        sessions.close(&id);
        assert_eq!(client.get(&url).send().await.unwrap().status(), 410);
    }
}
