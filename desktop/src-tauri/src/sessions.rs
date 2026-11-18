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
    pub local: Option<(std::path::PathBuf, &'static str)>,
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
                local: None,
                headers: media.headers,
                expires: Instant::now() + Duration::from_secs(120),
                cancel: CancellationToken::new(),
            },
        );
        id
    }
    pub fn insert_local(&self, path: std::path::PathBuf, mime: &'static str) -> String {
        let id = uuid::Uuid::new_v4().simple().to_string();
        let mut sessions = self.0.lock().unwrap();
        let local = sessions
            .iter()
            .filter(|(_, session)| session.local.is_some());
        if local.clone().count() >= 16 {
            if let Some(oldest) = local
                .min_by_key(|(_, session)| session.expires)
                .map(|(id, _)| id.clone())
            {
                if let Some(session) = sessions.remove(&oldest) {
                    session.cancel.cancel();
                }
            }
        }
        sessions.insert(
            id.clone(),
            Session {
                url: String::new(),
                headers: Default::default(),
                local: Some((path, mime)),
                expires: Instant::now(),
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
            if session.local.is_some() || session.expires > Instant::now() {
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
