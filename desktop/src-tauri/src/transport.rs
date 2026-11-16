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

pub fn valid_range(value: &str) -> bool {
    let Some(value) = value.strip_prefix("bytes=") else {
        return false;
    };
    let Some((start, end)) = value.split_once('-') else {
        return false;
    };
    if start.is_empty() {
        return end.parse::<u64>().is_ok_and(|n| n > 0);
    }
    let Ok(start) = start.parse::<u64>() else {
        return false;
    };
    end.is_empty() || end.parse::<u64>().is_ok_and(|n| n >= start)
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
    let mut request = state
        .client
        .request(method.clone(), &session.url)
        .headers(session.headers.clone())
        .header("Accept-Encoding", "identity");
    if let Some(range) = headers.get("range") {
        if !range.to_str().is_ok_and(valid_range) {
            return StatusCode::RANGE_NOT_SATISFIABLE.into_response();
        }
        request = request.header("Range", range);
    }
    if let Some(condition) = headers.get("if-range") {
        request = request.header("If-Range", condition);
    }
    let upstream = tokio::select! {
        _ = session.cancel.cancelled() => return StatusCode::GONE.into_response(),
        result = request.send() => match result {
            Ok(response) => response,
            Err(_) => return StatusCode::BAD_GATEWAY.into_response(),
        }
    };
    let status = upstream.status();
    if !matches!(status.as_u16(), 200 | 206 | 416) {
        return StatusCode::BAD_GATEWAY.into_response();
    }
    if status == StatusCode::PARTIAL_CONTENT && !upstream.headers().contains_key("content-range") {
        return StatusCode::BAD_GATEWAY.into_response();
    }
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
        if let Some(value) = upstream.headers().get(name) {
            response = response.header(name, value);
        }
    }
    if method == Method::HEAD {
        return response.body(Body::empty()).unwrap();
    }
    // 取消会打断等待中的上游读取；Body 被 WebView 丢弃时也立即释放连接。
    let bytes = upstream.bytes_stream();
    let body = futures_util::stream::unfold(
        (Box::pin(bytes), session.cancel),
        |(mut bytes, cancel)| async move {
            tokio::select! {
                _ = cancel.cancelled() => None,
                chunk = bytes.next() => chunk.map(|chunk|(chunk,(bytes,cancel))),
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
        assert!(
            crate::provider::common::bytes(client.get(format!("http://{address}/limited")))
                .await
                .unwrap_err()
                .contains("频繁")
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
