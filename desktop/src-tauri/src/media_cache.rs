use axum::{
    extract::{Path as RoutePath, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::get,
    Router,
};
use rusqlite::{params, Connection};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    io::Write,
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
};

#[derive(Clone)]
pub struct MediaCache(Arc<Inner>);
struct Inner {
    db: Mutex<Connection>,
    root: PathBuf,
    gates: [tokio::sync::Mutex<()>; 32],
}
fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn identity(value: &Value) -> Option<(&str, &str)> {
    let source = value["providerId"].as_str()?;
    let id = value["platformId"].as_str()?;
    (matches!(source, "qq" | "netease" | "kuwo" | "migu")
        && crate::provider::common::valid_id(source, id))
    .then_some((source, id))
}
fn cover_key(source: &str, url: &str) -> String {
    let stable = if source == "qq" {
        url.strip_prefix("https://y.gtimg.cn/music/photo_new/T002R500x500M000")
            .and_then(|s| s.strip_suffix(".jpg"))
            .map(|mid| format!("album:{mid}:500"))
    } else {
        None
    };
    digest(format!("{source}:{}", stable.as_deref().unwrap_or(url)).as_bytes())
}

impl MediaCache {
    pub fn open(root: &Path) -> Result<Self, Box<dyn std::error::Error>> {
        std::fs::create_dir_all(root.join("covers"))?;
        let db = Connection::open(root.join("resources.sqlite3"))?;
        db.execute_batch("PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS covers(key TEXT PRIMARY KEY, path TEXT NOT NULL, sha256 TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tracks(source TEXT NOT NULL, track TEXT NOT NULL, cover_key TEXT, origin TEXT, lyrics TEXT, PRIMARY KEY(source,track));
            CREATE TABLE IF NOT EXISTS download_refs(id TEXT PRIMARY KEY, source TEXT NOT NULL, track TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS refs_track ON download_refs(source,track);
            PRAGMA user_version=1;")?;
        Ok(Self(Arc::new(Inner {
            db: Mutex::new(db),
            root: root.to_owned(),
            gates: std::array::from_fn(|_| tokio::sync::Mutex::new(())),
        })))
    }
    fn gate(&self, key: &str) -> &tokio::sync::Mutex<()> {
        let hash = Sha256::digest(key.as_bytes());
        &self.0.gates[usize::from(hash[0]) % self.0.gates.len()]
    }
    fn read_image(&self, key: &str) -> Option<(Vec<u8>, &'static str)> {
        if key.len() != 64 || !key.bytes().all(|c| c.is_ascii_hexdigit()) {
            return None;
        }
        let db = self.0.db.lock().ok()?;
        let (path, checksum): (String, String) = db
            .query_row("SELECT path,sha256 FROM covers WHERE key=?1", [key], |r| {
                Ok((r.get(0)?, r.get(1)?))
            })
            .ok()?;
        if path != format!("covers/{key}.img") {
            return None;
        }
        let file = self.0.root.join(path);
        if file.metadata().ok()?.len() > 2 * 1024 * 1024 {
            return None;
        }
        let data = std::fs::read(file).ok()?;
        let mime = crate::covers::image_type(&data)?;
        (digest(&data) == checksum).then_some((data, mime))
    }
    fn put_image(&self, key: &str, bytes: &[u8]) -> Option<()> {
        let db = self.0.db.lock().ok()?;
        let path = format!("covers/{key}.img");
        let mut tmp = tempfile::NamedTempFile::new_in(self.0.root.join("covers")).ok()?;
        tmp.write_all(bytes).ok()?;
        tmp.persist(self.0.root.join(&path)).ok()?;
        db.execute(
            "INSERT OR REPLACE INTO covers VALUES (?1,?2,?3)",
            params![key, path, digest(bytes)],
        )
        .ok()?;
        Some(())
    }
    pub async fn cover(
        &self,
        covers: &crate::covers::Covers,
        track: &Value,
        supplied: Option<&str>,
        port: u16,
    ) -> Option<String> {
        let (source, id) = identity(track)?;
        let previous = self
            .0
            .db
            .lock()
            .ok()?
            .query_row(
                "SELECT origin FROM tracks WHERE source=?1 AND track=?2",
                params![source, id],
                |r| r.get::<_, Option<String>>(0),
            )
            .ok()
            .flatten();
        let url = supplied
            .filter(|url| url.len() <= 2048 && crate::covers::valid_url(source, url))
            .or(previous.as_deref())?;
        let key = cover_key(source, url);
        let _guard = self.gate(&format!("cover:{key}")).lock().await;
        {
            let db = self.0.db.lock().ok()?;
            db.execute("INSERT INTO tracks(source,track,cover_key,origin) VALUES (?1,?2,?3,?4)
                ON CONFLICT(source,track) DO UPDATE SET cover_key=excluded.cover_key,origin=excluded.origin",params![source,id,key,url]).ok()?;
        }
        if self.read_image(&key).is_none() {
            let (bytes, _) = covers.load(source, url).await.ok()?;
            self.put_image(&key, &bytes)?;
        }
        Some(format!("http://127.0.0.1:{port}/cached-covers/{key}"))
    }
    pub fn cached_for_track(&self, track: &Value, port: u16) -> Option<String> {
        let (source, id) = identity(track)?;
        let key = self
            .0
            .db
            .lock()
            .ok()?
            .query_row(
                "SELECT cover_key FROM tracks WHERE source=?1 AND track=?2",
                params![source, id],
                |r| r.get::<_, String>(0),
            )
            .ok()?;
        self.read_image(&key)?;
        Some(format!("http://127.0.0.1:{port}/cached-covers/{key}"))
    }
    pub fn cached_lyrics(&self, track: &Value) -> Option<Value> {
        let (source, id) = identity(track)?;
        let db = self.0.db.lock().ok()?;
        let raw: String = db
            .query_row(
                "SELECT lyrics FROM tracks WHERE source=?1 AND track=?2",
                params![source, id],
                |r| r.get(0),
            )
            .ok()?;
        let doc: Value = serde_json::from_str(&raw).ok()?;
        (identity(&doc["identity"]) == Some((source, id))
            && matches!(
                doc["status"].as_str(),
                Some("synced" | "plain" | "instrumental")
            ))
        .then_some(doc)
    }
    pub async fn lyrics(&self, client: &reqwest::Client, track: &Value) -> Result<Value, String> {
        let (source, id) = identity(track).ok_or("歌词曲目无效")?;
        if let Some(doc) = self.cached_lyrics(track) {
            return Ok(doc);
        }
        let _guard = self.gate(&format!("lyrics:{source}:{id}")).lock().await;
        if let Some(doc) = self.cached_lyrics(track) {
            return Ok(doc);
        }
        let doc = crate::lyrics::get(client, track).await?;
        if matches!(
            doc["status"].as_str(),
            Some("synced" | "plain" | "instrumental")
        ) {
            if let Ok(db) = self.0.db.lock() {
                let _ = db.execute(
                    "INSERT INTO tracks(source,track,lyrics) VALUES(?1,?2,?3)
                    ON CONFLICT(source,track) DO UPDATE SET lyrics=excluded.lyrics",
                    params![source, id, doc.to_string()],
                );
            }
        }
        Ok(doc)
    }
    pub fn pin(&self, id: &str, track: &Value) {
        if let (Some((source, track)), Ok(db)) = (identity(track), self.0.db.lock()) {
            let _ = db.execute(
                "INSERT OR REPLACE INTO download_refs VALUES (?1,?2,?3)",
                params![id, source, track],
            );
        }
    }
    // JSON download history remains authoritative, including old records and removals.
    pub fn clear(&self, saved: &[crate::download_history::SavedDownload]) -> rusqlite::Result<()> {
        let mut db = self.0.db.lock().unwrap();
        let tx = db.transaction()?;
        tx.execute("DELETE FROM download_refs", [])?;
        for row in saved {
            if let Some((source, track)) = identity(&row.identity) {
                tx.execute(
                    "INSERT INTO download_refs VALUES(?1,?2,?3)",
                    params![row.id, source, track],
                )?;
            }
        }
        tx.execute("DELETE FROM tracks WHERE NOT EXISTS(SELECT 1 FROM download_refs r WHERE r.source=tracks.source AND r.track=tracks.track)",[])?;
        let keys = {
            let mut stmt=tx.prepare("SELECT key FROM covers WHERE NOT EXISTS(SELECT 1 FROM tracks WHERE tracks.cover_key=covers.key)")?;
            let rows = stmt
                .query_map([], |r| r.get::<_, String>(0))?
                .collect::<rusqlite::Result<Vec<_>>>()?;
            rows
        };
        for key in &keys {
            tx.execute("DELETE FROM covers WHERE key=?1", [key])?;
        }
        tx.commit()?;
        for key in keys {
            if key.len() == 64 && key.bytes().all(|c| c.is_ascii_hexdigit()) {
                let _ = std::fs::remove_file(self.0.root.join(format!("covers/{key}.img")));
            }
        }
        Ok(())
    }
    pub fn router(self) -> Router {
        Router::new()
            .route("/cached-covers/{key}", get(image))
            .with_state(self)
    }
}

async fn image(State(cache): State<MediaCache>, RoutePath(key): RoutePath<String>) -> Response {
    match tokio::task::spawn_blocking(move || cache.read_image(&key))
        .await
        .ok()
        .flatten()
    {
        Some((bytes, mime)) => (
            [
                ("Content-Type", mime),
                ("Access-Control-Allow-Origin", "*"),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
            ],
            bytes,
        )
            .into_response(),
        None => StatusCode::NOT_FOUND.into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn track(id: &str) -> Value {
        json!({"providerId":"qq","platformId":id})
    }
    fn saved(id: &str, format: &str) -> crate::download_history::SavedDownload {
        crate::download_history::SavedDownload {
            id: id.into(),
            identity: track("sample"),
            title: "fixture".into(),
            artist: "fixture".into(),
            path: PathBuf::from(format!("fixture.{format}")),
            format: format.into(),
            size_bytes: 100,
            saved_at: 1,
            source_preserved: false,
        }
    }
    #[tokio::test]
    async fn repeated_download_reuses_resources_and_clear_preserves_other_record() {
        let folder = tempfile::tempdir().unwrap();
        let cache = MediaCache::open(folder.path()).unwrap();
        let url = "https://y.gtimg.cn/music/photo_new/T002R500x500M000sample.jpg";
        let key = cover_key("qq", url);
        let doc = json!({"identity":track("sample"),"status":"synced","lines":[{"startMs":1000,"text":"fixture","translation":"translation"}]});
        cache.put_image(&key, b"\xff\xd8\xfffixture").unwrap();
        cache
            .0
            .db
            .lock()
            .unwrap()
            .execute(
                "INSERT INTO tracks VALUES('qq','sample',?1,?2,?3)",
                params![key, url, doc.to_string()],
            )
            .unwrap();
        cache
            .0
            .db
            .lock()
            .unwrap()
            .execute(
                "INSERT INTO tracks VALUES('qq','ordinary',NULL,NULL,?1)",
                [json!({"identity":track("ordinary"),"status":"plain"}).to_string()],
            )
            .unwrap();
        drop(cache);
        let cache = MediaCache::open(folder.path()).unwrap();
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::ZERO)
            .build()
            .unwrap();
        let reader = crate::covers::Covers::default();
        let mp3 = saved("mp3", "mp3");
        let flac = saved("flac", "flac");
        for row in [&mp3, &flac] {
            cache.pin(&row.id, &row.identity);
            let cover = cache
                .cover(&reader, &row.identity, Some(url), 1234)
                .await
                .unwrap();
            assert!(cover.ends_with(&key));
            assert_eq!(cache.lyrics(&client, &row.identity).await.unwrap(), doc);
        }
        cache.clear(&[flac]).unwrap();
        assert!(cache.cached_lyrics(&track("ordinary")).is_none());
        assert_eq!(cache.cached_lyrics(&track("sample")), Some(doc));
        assert!(cache
            .cached_for_track(&track("sample"), 4321)
            .unwrap()
            .contains(":4321/"));
        std::fs::write(
            folder.path().join(format!("covers/{key}.img")),
            b"\xff\xd8\xffchanged",
        )
        .unwrap();
        assert!(cache.cached_for_track(&track("sample"), 4321).is_none());
        cache.clear(&[]).unwrap();
        assert!(!folder.path().join(format!("covers/{key}.img")).exists());
    }
}
