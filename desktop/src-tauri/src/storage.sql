CREATE TABLE local_files (
    file_id INTEGER PRIMARY KEY,
    path TEXT NOT NULL COLLATE BINARY UNIQUE,
    stored_path_key TEXT NOT NULL,
    manual INTEGER NOT NULL DEFAULT 0 CHECK (manual IN (0, 1))
);
CREATE INDEX local_files_by_key ON local_files(stored_path_key);

CREATE TABLE library_directories (
    seq INTEGER PRIMARY KEY,
    directory_id TEXT NOT NULL UNIQUE,
    path TEXT NOT NULL COLLATE BINARY
);
CREATE TABLE directory_files (
    directory_id TEXT NOT NULL REFERENCES library_directories(directory_id) ON DELETE CASCADE,
    file_id INTEGER NOT NULL REFERENCES local_files(file_id) ON DELETE RESTRICT,
    PRIMARY KEY (directory_id, file_id)
);
CREATE INDEX directory_files_by_file ON directory_files(file_id);

CREATE TABLE downloads (
    seq INTEGER PRIMARY KEY,
    download_id TEXT NOT NULL UNIQUE,
    file_id INTEGER NOT NULL REFERENCES local_files(file_id) ON DELETE RESTRICT,
    provider_id TEXT NOT NULL CHECK (provider_id IN ('qq', 'netease', 'kuwo', 'migu')),
    platform_id TEXT NOT NULL CHECK (length(platform_id) > 0),
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    format TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
    saved_at INTEGER NOT NULL CHECK (saved_at >= 0),
    source_preserved INTEGER NOT NULL DEFAULT 0 CHECK (source_preserved IN (0, 1))
);
CREATE INDEX downloads_by_file ON downloads(file_id);
CREATE INDEX downloads_by_track ON downloads(provider_id, platform_id);

CREATE TABLE excluded_files (
    song_id TEXT NOT NULL PRIMARY KEY
);
CREATE TABLE download_settings (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    directory TEXT,
    naming TEXT NOT NULL DEFAULT 'artist_title'
        CHECK (naming IN ('title', 'artist_title', 'title_artist'))
);
INSERT INTO download_settings(singleton) VALUES (1);

CREATE TABLE covers (
    cover_key TEXT NOT NULL PRIMARY KEY,
    sha256 TEXT NOT NULL
);
CREATE TABLE track_resources (
    provider_id TEXT NOT NULL CHECK (provider_id IN ('qq', 'netease', 'kuwo', 'migu')),
    platform_id TEXT NOT NULL CHECK (length(platform_id) > 0),
    cover_key TEXT REFERENCES covers(cover_key) ON DELETE SET NULL,
    origin TEXT,
    lyrics TEXT,
    PRIMARY KEY (provider_id, platform_id)
);
CREATE INDEX track_resources_by_cover ON track_resources(cover_key);
PRAGMA user_version = 1;
