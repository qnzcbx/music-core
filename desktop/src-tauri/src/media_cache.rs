use crate::storage::Database;
use axum::{
    extract::{Path as RoutePath, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::get,
    Router,
};
use rusqlite::{params, params_from_iter};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::{
    io::Write,
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
};

#[derive(Clone)]
pub struct MediaCache(Arc<Inner>);
#[derive(Clone, Copy)]
pub enum ClearScope {
    Cover,
    Lyrics,
    All,
}
struct Inner {
    db: Database,
    cover_files: Mutex<()>,
    root: PathBuf,
    gates: [tokio::sync::Mutex<()>; 32],
    cover_changed: tokio::sync::Notify,
}
fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub(crate) fn identity(value: &Value) -> Option<(&str, &str)> {
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

fn valid_key(key: &str) -> bool {
    key.len() == 64 && key.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn cover_url(key: &str, port: u16) -> String {
    format!("http://127.0.0.1:{port}/cached-covers/{key}")
}

impl MediaCache {
    pub(crate) fn open(root: &Path, db: Database) -> std::io::Result<Self> {
        std::fs::create_dir_all(root.join("covers"))?;
        Ok(Self(Arc::new(Inner {
            db,
            root: root.to_owned(),
            cover_files: Mutex::new(()),
            gates: std::array::from_fn(|_| tokio::sync::Mutex::new(())),
            cover_changed: tokio::sync::Notify::new(),
        })))
    }

    fn gate(&self, key: &str) -> &tokio::sync::Mutex<()> {
        let hash = Sha256::digest(key.as_bytes());
        &self.0.gates[usize::from(hash[0]) % self.0.gates.len()]
    }
    fn read_image(&self, key: &str) -> Option<(Vec<u8>, &'static str)> {
        if !valid_key(key) {
            return None;
        }
        let checksum: String = self
            .0
            .db
            .lock()
            .query_row(
                "SELECT sha256 FROM covers WHERE cover_key=?1",
                [key],
                |row| row.get(0),
            )
            .ok()?;
        let file = self.0.root.join(format!("covers/{key}.img"));
        if file.metadata().ok()?.len() > 2 * 1024 * 1024 {
            return None;
        }
        let data = std::fs::read(file).ok()?;
        let mime = crate::covers::image_type(&data)?;
        (digest(&data) == checksum).then_some((data, mime))
    }
    fn link_image(
        &self,
        source: &str,
        id: &str,
        key: &str,
        url: &str,
        bytes: Option<&[u8]>,
    ) -> Option<bool> {
        let _files = self.0.cover_files.lock().ok()?;
        if let Some(bytes) = bytes {
            let mut tmp = tempfile::NamedTempFile::new_in(self.0.root.join("covers")).ok()?;
            tmp.write_all(bytes).ok()?;
            tmp.persist(self.0.root.join(format!("covers/{key}.img")))
                .ok()?;
        }
        let mut db = self.0.db.lock();
        let tx = db.transaction().ok()?;
        if let Some(bytes) = bytes {
            tx.execute(
                "INSERT INTO covers(cover_key,sha256) VALUES (?1,?2)
                 ON CONFLICT(cover_key) DO UPDATE SET sha256=excluded.sha256",
                params![key, digest(bytes)],
            )
            .ok()?;
        }
        if !tx
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM covers WHERE cover_key=?1)",
                [key],
                |row| row.get::<_, bool>(0),
            )
            .ok()?
        {
            return None;
        }
        let changed = tx.execute(
            "INSERT INTO track_resources(provider_id,platform_id,cover_key,origin) VALUES (?1,?2,?3,?4)
             ON CONFLICT(provider_id,platform_id) DO UPDATE SET cover_key=excluded.cover_key,origin=excluded.origin
             WHERE track_resources.cover_key IS NOT excluded.cover_key OR track_resources.origin IS NOT excluded.origin",
            params![source,id,key,url],
        ).ok()? > 0;
        tx.commit().ok()?;
        Some(changed || bytes.is_some())
    }

    pub async fn cover(
        &self,
        covers: &crate::covers::Covers,
        track: &Value,
        supplied: Option<&str>,
        port: u16,
    ) -> Option<String> {
        let (source, id) = identity(track)?;
        let (source, id) = (source.to_owned(), id.to_owned());
        let supplied = supplied
            .filter(|url| url.len() <= 2048 && crate::covers::valid_url(&source, url))
            .map(str::to_owned);
        let url = if let Some(url) = supplied {
            url
        } else {
            let cache = self.clone();
            let (source, id) = (source.clone(), id.clone());
            tokio::task::spawn_blocking(move || {
                cache.0.db.lock().query_row(
                    "SELECT origin FROM track_resources WHERE provider_id=?1 AND platform_id=?2",
                    params![source,id], |r| r.get::<_, Option<String>>(0),
                ).ok().flatten()
            })
            .await
            .ok()
            .flatten()?
        };
        let key = cover_key(&source, &url);
        let _guard = self.gate(&format!("cover:{key}")).lock().await;
        let needs_image = {
            let cache = self.clone();
            let (source, id, key, url) = (source.clone(), id.clone(), key.clone(), url.clone());
            tokio::task::spawn_blocking(move || {
                if cache.read_image(&key).is_some() {
                    return Some(false);
                }
                let changed = cache.0.db.lock().execute(
                    "INSERT INTO track_resources(provider_id,platform_id,origin) VALUES (?1,?2,?3)
                     ON CONFLICT(provider_id,platform_id) DO UPDATE SET origin=excluded.origin,cover_key=NULL
                     WHERE track_resources.origin IS NOT excluded.origin",
                    params![source,id,url],
                ).ok()? > 0;
                if changed {
                    cache.0.cover_changed.notify_one();
                }
                Some(true)
            }).await.ok().flatten()?
        };
        let bytes = if needs_image {
            Some(covers.load(&source, &url).await.ok()?.0)
        } else {
            None
        };
        let cache = self.clone();
        tokio::task::spawn_blocking(move || {
            if cache.link_image(&source, &id, &key, &url, bytes.as_deref())? {
                cache.0.cover_changed.notify_one();
            }
            Some(cover_url(&key, port))
        })
        .await
        .ok()
        .flatten()
    }

    pub async fn cover_changed(&self) {
        self.0.cover_changed.notified().await;
    }

    // 列表只读取索引，回环路由在返回实际图片时校验字节。
    pub fn indexed_covers(&self, tracks: &[Option<&Value>], port: u16) -> Vec<Option<String>> {
        let requested = tracks
            .iter()
            .map(|track| track.and_then(identity))
            .collect::<Vec<_>>();
        let mut keys = requested.iter().copied().flatten().collect::<Vec<_>>();
        keys.sort_unstable();
        keys.dedup();
        let mut urls = HashMap::new();
        let db = self.0.db.lock();
        for batch in keys.chunks(200) {
            let pairs = vec!["(?,?)"; batch.len()].join(",");
            let sql = format!(
                "SELECT r.provider_id,r.platform_id,c.cover_key
                FROM track_resources r JOIN covers c ON r.cover_key=c.cover_key
                WHERE (r.provider_id,r.platform_id) IN (VALUES {pairs})"
            );
            let Ok(mut stmt) = db.prepare_cached(&sql) else {
                continue;
            };
            let Ok(rows) = stmt.query_map(
                params_from_iter(batch.iter().flat_map(|&(a, b)| [a, b])),
                |row| {
                    Ok((
                        (row.get::<_, String>(0)?, row.get::<_, String>(1)?),
                        row.get::<_, String>(2)?,
                    ))
                },
            ) else {
                continue;
            };
            for (track, key) in rows.flatten() {
                if valid_key(&key) {
                    urls.insert(track, cover_url(&key, port));
                }
            }
        }
        requested
            .into_iter()
            .map(|track| {
                let (provider, id) = track?;
                urls.get(&(provider.to_owned(), id.to_owned())).cloned()
            })
            .collect()
    }

    pub fn decorate_library(
        &self,
        view: &mut Value,
        records: &[crate::download_history::SavedDownload],
        port: u16,
    ) {
        let identities: HashMap<_, _> = records
            .iter()
            .map(|r| (r.id.as_str(), &r.identity))
            .collect();
        let Some(rows) = view["downloads"].as_array() else {
            return;
        };
        let tracks = rows
            .iter()
            .map(|row| {
                row["recordId"]
                    .as_str()
                    .and_then(|id| identities.get(id).copied())
            })
            .collect::<Vec<_>>();
        let urls: HashMap<_, _> = rows
            .iter()
            .zip(self.indexed_covers(&tracks, port))
            .filter_map(|(row, url)| Some((row["id"].as_str()?.to_owned(), url?)))
            .collect();
        for list in ["songs", "downloads"] {
            if let Some(rows) = view[list].as_array_mut() {
                for row in rows {
                    if let Some(url) = row["id"].as_str().and_then(|id| urls.get(id)) {
                        row["cover"] = serde_json::json!(url);
                    }
                }
            }
        }
    }

    pub fn cached_for_track(&self, track: &Value, port: u16) -> Option<String> {
        let (source, id) = identity(track)?;
        let key = self
            .0
            .db
            .lock()
            .query_row(
                "SELECT cover_key FROM track_resources WHERE provider_id=?1 AND platform_id=?2",
                params![source, id],
                |r| r.get::<_, String>(0),
            )
            .ok()?;
        self.read_image(&key)?;
        Some(cover_url(&key, port))
    }
    pub fn cached_lyrics(&self, track: &Value) -> Option<Value> {
        let (source, id) = identity(track)?;
        let raw: String = self
            .0
            .db
            .lock()
            .query_row(
                "SELECT lyrics FROM track_resources WHERE provider_id=?1 AND platform_id=?2",
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
    async fn read_lyrics_async(&self, track: &Value) -> Option<Value> {
        let cache = self.clone();
        let track = track.clone();
        tokio::task::spawn_blocking(move || cache.cached_lyrics(&track))
            .await
            .ok()
            .flatten()
    }

    pub async fn lyrics(&self, client: &reqwest::Client, track: &Value) -> Result<Value, String> {
        let (source, id) = identity(track).ok_or("歌词曲目无效")?;
        if let Some(doc) = self.read_lyrics_async(track).await {
            return Ok(doc);
        }
        let _guard = self.gate(&format!("lyrics:{source}:{id}")).lock().await;
        if let Some(doc) = self.read_lyrics_async(track).await {
            return Ok(doc);
        }
        let doc = crate::lyrics::get(client, track).await?;
        if matches!(
            doc["status"].as_str(),
            Some("synced" | "plain" | "instrumental")
        ) {
            let cache = self.clone();
            let (source, id, body) = (source.to_owned(), id.to_owned(), doc.to_string());
            let _ = tokio::task::spawn_blocking(move || {
                cache.0.db.lock().execute(
                    "INSERT INTO track_resources(provider_id,platform_id,lyrics) VALUES(?1,?2,?3)
                 ON CONFLICT(provider_id,platform_id) DO UPDATE SET lyrics=excluded.lyrics",
                    params![source, id, body],
                )
            })
            .await;
        }
        Ok(doc)
    }
    pub fn directory(&self) -> &Path {
        &self.0.root
    }

    pub fn clear(&self, live_ids: &[String], scope: ClearScope) -> rusqlite::Result<()> {
        let covers = matches!(scope, ClearScope::Cover | ClearScope::All);
        let _files = covers.then(|| self.0.cover_files.lock().unwrap());
        let removed = {
            let mut db = self.0.db.lock();
            let tx = db.transaction()?;
            // 临时表的创建与销毁都在同一事务内，回滚也不留下本次有效集合。
            tx.execute(
                "CREATE TEMP TABLE live_downloads(download_id TEXT PRIMARY KEY)",
                [],
            )?;
            {
                let mut insert = tx.prepare("INSERT INTO temp.live_downloads VALUES (?1)")?;
                for id in live_ids {
                    insert.execute([id])?;
                }
            }
            let unprotected = "NOT EXISTS (
                SELECT 1 FROM downloads d JOIN temp.live_downloads l ON l.download_id=d.download_id
                WHERE d.provider_id=track_resources.provider_id AND d.platform_id=track_resources.platform_id
            )";
            if covers {
                tx.execute(&format!("UPDATE track_resources SET cover_key=NULL, origin=NULL WHERE {unprotected}"), [])?;
            }
            if matches!(scope, ClearScope::Lyrics | ClearScope::All) {
                tx.execute(
                    &format!("UPDATE track_resources SET lyrics=NULL WHERE {unprotected}"),
                    [],
                )?;
            }
            tx.execute("DELETE FROM track_resources WHERE cover_key IS NULL AND origin IS NULL AND lyrics IS NULL", [])?;
            let keys = if covers {
                let mut stmt = tx.prepare("DELETE FROM covers
                    WHERE NOT EXISTS(SELECT 1 FROM track_resources r WHERE r.cover_key=covers.cover_key)
                    RETURNING cover_key")?;
                let rows = stmt.query_map([], |r| r.get::<_, String>(0))?;
                rows.collect::<rusqlite::Result<Vec<_>>>()?
            } else {
                Vec::new()
            };
            tx.execute("DROP TABLE temp.live_downloads", [])?;
            tx.commit()?;
            keys
        };
        // 索引已提交，仍持封面门，避免删掉同键刚发布的新图片。
        for key in removed.into_iter().filter(|key| valid_key(key)) {
            if let Err(error) = std::fs::remove_file(self.0.root.join(format!("covers/{key}.img")))
            {
                if error.kind() != std::io::ErrorKind::NotFound {
                    eprintln!("无法清理封面缓存 {key}: {error}");
                }
            }
        }
        if covers {
            self.0.cover_changed.notify_one();
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
    use crate::{download_history::SavedDownload, downloads::Downloads};
    use serde_json::json;

    #[tokio::test]
    async fn offline_cache_protects_live_products_and_clears_only_selected_resources() {
        let root = tempfile::tempdir().unwrap();
        let db_path = root.path().join("music-core.sqlite3");
        let db = Database::open(&db_path).unwrap();
        let cache = MediaCache::open(root.path(), db.clone()).unwrap();
        let downloads = Downloads::with_database(db.clone(), root.path().into());
        let mp3 = root.path().join("sample.mp3");
        let flac = root.path().join("sample.flac");
        let track = json!({"providerId":"qq","platformId":"sample"});
        let other = json!({"providerId":"netease","platformId":"123"});
        let same_id_qq = json!({"providerId":"qq","platformId":"123"});
        let doc = json!({"identity":track,"status":"plain","plainText":"offline"});
        let url = "https://y.gtimg.cn/music/photo_new/T002R500x500M000sample.jpg";
        let key = cover_key("qq", url);
        let bytes = b"\xff\xd8\xfffixture";
        cache
            .link_image("qq", "sample", &key, url, Some(bytes))
            .unwrap();
        cache.link_image("qq", "123", &key, url, None).unwrap();
        db.lock().execute("INSERT INTO track_resources(provider_id,platform_id,lyrics) VALUES('netease','123','{}')", []).unwrap();
        db.lock().execute("UPDATE track_resources SET lyrics=?1 WHERE provider_id='qq' AND platform_id='sample'", [doc.to_string()]).unwrap();
        for (id, path, format) in [("mp3", &mp3, "mp3"), ("flac", &flac, "flac")] {
            std::fs::write(path, b"audio").unwrap();
            downloads
                .access_history(|history| {
                    history.add(SavedDownload {
                        id: id.into(),
                        identity: track.clone(),
                        title: "fixture".into(),
                        artist: String::new(),
                        path: path.clone(),
                        format: format.into(),
                        size_bytes: 5,
                        saved_at: 1,
                        source_preserved: false,
                    })
                })
                .unwrap();
        }
        drop(cache);
        drop(downloads);
        drop(db);
        let db = Database::open(&db_path).unwrap();
        let cache = MediaCache::open(root.path(), db.clone()).unwrap();
        let mut downloads = Downloads::with_database(db.clone(), root.path().into());
        downloads.media_covers.1 = Some(cache.clone());
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::ZERO)
            .build()
            .unwrap();
        let relay = crate::covers::Covers::default();
        assert_eq!(cache.lyrics(&client, &track).await.unwrap(), doc);
        assert!(cache
            .cover(&relay, &track, None, 4321)
            .await
            .unwrap()
            .ends_with(&key));
        let batch = cache.indexed_covers(&[Some(&other), Some(&same_id_qq), Some(&track)], 4321);
        assert!(batch[0].is_none());
        assert_eq!(batch[1], batch[2]);

        downloads
            .access_history(|history| {
                history.remove_song(&mp3, &crate::local_library::path_key(&mp3), false)
            })
            .unwrap();
        downloads.clear_media_cache(ClearScope::Lyrics).unwrap();
        assert!(cache.cached_lyrics(&track).is_some());
        assert!(cache.read_image(&key).is_some());
        assert_eq!(
            db.lock()
                .query_row(
                    "SELECT count(*) FROM track_resources WHERE provider_id='netease'",
                    [],
                    |r| r.get::<_, i64>(0)
                )
                .unwrap(),
            0
        );
        downloads.clear_media_cache(ClearScope::Cover).unwrap();
        assert!(cache.cached_lyrics(&track).is_some());
        assert!(cache.read_image(&key).is_some());
        assert_eq!(cache.indexed_covers(&[Some(&same_id_qq)], 4321), vec![None]);

        let image = root.path().join(format!("covers/{key}.img"));
        std::fs::write(&image, b"\xff\xd8\xffchanged").unwrap();
        assert!(cache.cached_for_track(&track, 4321).is_none());
        std::fs::remove_file(&image).unwrap();
        assert!(cache.cached_for_track(&track, 4321).is_none());
        cache
            .link_image("qq", "sample", &key, url, Some(bytes))
            .unwrap();
        std::fs::remove_file(&flac).unwrap();
        downloads.clear_media_cache(ClearScope::All).unwrap();
        assert!(cache.cached_lyrics(&track).is_none() && !image.exists());
        assert!(mp3.is_file());
        assert_eq!(downloads.saved_records().unwrap().len(), 1);
    }

    #[test]
    fn failed_cache_transaction_does_not_reuse_temporary_ids_or_damage_downloads() {
        let root = tempfile::tempdir().unwrap();
        let db = Database::memory();
        let cache = MediaCache::open(root.path(), db.clone()).unwrap();
        let key = digest(b"image");
        cache
            .link_image("qq", "sample", &key, "origin", Some(b"\xff\xd8\xfffixture"))
            .unwrap();
        db.lock()
            .execute_batch(
                "CREATE TEMP TRIGGER refuse_cover BEFORE UPDATE ON track_resources
            BEGIN SELECT RAISE(ABORT, 'cache write failed'); END",
            )
            .unwrap();
        assert!(cache
            .clear(&["previous-id".into()], ClearScope::Cover)
            .is_err());
        assert!(cache.read_image(&key).is_some());
        assert_eq!(
            db.lock()
                .query_row(
                    "SELECT count(*) FROM sqlite_temp_schema WHERE name='live_downloads'",
                    [],
                    |r| r.get::<_, i64>(0)
                )
                .unwrap(),
            0
        );
        db.lock().execute("DROP TRIGGER refuse_cover", []).unwrap();
        cache.clear(&[], ClearScope::Cover).unwrap();
        assert!(cache.read_image(&key).is_none());
    }
}

#[cfg(test)]
mod concurrency_tests {
    use super::*;
    use crate::{download_history::SavedDownload, downloads::Downloads};
    use serde_json::json;

    #[test]
    fn cleanup_waits_for_download_registration_and_never_leaves_unindexed_same_key() {
        let root = tempfile::tempdir().unwrap();
        let db = Database::memory();
        let cache = MediaCache::open(root.path(), db.clone()).unwrap();
        let mut downloads = Downloads::with_database(db.clone(), root.path().into());
        downloads.media_covers.1 = Some(cache.clone());
        let key = digest(b"shared-image");
        let bytes = b"\xff\xd8\xfffixture";
        cache
            .link_image("qq", "sample", &key, "origin", Some(bytes))
            .unwrap();
        let path = root.path().join("sample.mp3");
        std::fs::write(&path, b"media").unwrap();
        std::thread::scope(|scope| {
            let cleanup = downloads
                .access_history(|history| {
                    let (started, wait) = std::sync::mpsc::channel();
                    let manager = &downloads;
                    let task = scope.spawn(move || {
                        started.send(()).unwrap();
                        manager.clear_media_cache(ClearScope::All).unwrap();
                    });
                    wait.recv().unwrap();
                    // 已持有业务锁但未持 SQLite 连接，清理应在登记之后取有效成品。
                    assert!(cache.read_image(&key).is_some());
                    history.add(SavedDownload {
                        id: "saved".into(),
                        identity: json!({"providerId":"qq","platformId":"sample"}),
                        title: "fixture".into(),
                        artist: String::new(),
                        path: path.clone(),
                        format: "mp3".into(),
                        size_bytes: 5,
                        saved_at: 1,
                        source_preserved: false,
                    })?;
                    Ok(task)
                })
                .unwrap();
            cleanup.join().unwrap();
        });
        assert!(cache.read_image(&key).is_some());
        std::fs::remove_file(&path).unwrap();
        std::thread::scope(|scope| {
            scope.spawn(|| downloads.clear_media_cache(ClearScope::Cover).unwrap());
            scope.spawn(|| {
                cache
                    .link_image("qq", "sample", &key, "origin", Some(bytes))
                    .unwrap();
            });
        });
        let resource = cache.indexed_covers(
            &[Some(&json!({"providerId":"qq","platformId":"sample"}))],
            1,
        );
        let exists = root.path().join(format!("covers/{key}.img")).is_file();
        assert_eq!(resource[0].is_some(), exists);
        assert_eq!(cache.read_image(&key).is_some(), exists);
    }
}
