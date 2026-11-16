use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
use tokio_util::sync::CancellationToken;

#[derive(Clone)]
pub struct Session {
    pub url: String,
    pub headers: reqwest::header::HeaderMap,
    pub expires: Instant,
    pub cancel: CancellationToken,
}

#[derive(Clone)]
pub struct Sessions(pub Arc<Mutex<HashMap<String, Session>>>);

impl Sessions {
    pub fn new() -> Self {
        Self(Arc::new(Mutex::new(HashMap::new())))
    }
    #[cfg(test)]
    pub fn insert(&self, url: String) -> String {
        self.insert_media(crate::provider::Media {
            url,
            headers: reqwest::header::HeaderMap::new(),
        })
    }
    pub fn insert_media(&self, media: crate::provider::Media) -> String {
        let id = uuid::Uuid::new_v4().simple().to_string();
        self.0.lock().unwrap().insert(
            id.clone(),
            Session {
                url: media.url,
                headers: media.headers,
                expires: Instant::now() + Duration::from_secs(120),
                cancel: CancellationToken::new(),
            },
        );
        id
    }
    pub fn get(&self, id: &str) -> Option<Session> {
        self.prune();
        self.0.lock().unwrap().get(id).cloned()
    }
    pub fn renew(&self, id: &str) -> bool {
        self.prune();
        if let Some(session) = self.0.lock().unwrap().get_mut(id) {
            session.expires = Instant::now() + Duration::from_secs(120);
            true
        } else {
            false
        }
    }
    pub fn close(&self, id: &str) {
        if let Some(session) = self.0.lock().unwrap().remove(id) {
            session.cancel.cancel();
        }
    }
    pub fn close_all(&self) {
        for (_, session) in self.0.lock().unwrap().drain() {
            session.cancel.cancel();
        }
    }
    pub fn prune(&self) {
        self.0.lock().unwrap().retain(|_, session| {
            if session.expires > Instant::now() {
                true
            } else {
                session.cancel.cancel();
                false
            }
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn released_and_invalid_sessions_are_unavailable() {
        let sessions = Sessions::new();
        assert!(sessions.get("invalid").is_none());
        let id = sessions.insert("https://example.invalid".into());
        let active = sessions.get(&id).unwrap();
        sessions.close(&id);
        assert!(active.cancel.is_cancelled());
        assert!(sessions.get(&id).is_none());
        assert!(!sessions.renew(&id));
    }
}
