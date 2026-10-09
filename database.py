"""SQLite layer — full multi-user schema."""
import json, os, sqlite3, time
from flask import g
import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT,
    display_name TEXT,
    is_active INTEGER DEFAULT 1,
    is_admin INTEGER DEFAULT 0,
    email_verified INTEGER DEFAULT 0,
    email_verified_at TEXT,
    username_changed_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT,
    PRIMARY KEY (user_id, key),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS anime (
    mal_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    title_english TEXT, title_japanese TEXT, title_romaji TEXT, synonyms TEXT,
    type TEXT, episodes INTEGER, status TEXT, airing INTEGER DEFAULT 0,
    score REAL, popularity INTEGER, members INTEGER, favorites INTEGER,
    year INTEGER, season TEXT,
    aired_from TEXT, aired_to TEXT, duration INTEGER, source TEXT,
    synopsis TEXT, image_url TEXT, trailer_url TEXT,
    genres TEXT DEFAULT '[]', themes TEXT DEFAULT '[]',
    studios TEXT DEFAULT '[]', streaming TEXT DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS user_anime (
    user_id INTEGER NOT NULL,
    anime_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'plan_to_watch',
    current_episode INTEGER NOT NULL DEFAULT 0,
    total_episodes INTEGER,
    notes TEXT DEFAULT '',
    rewatch_count INTEGER DEFAULT 0,
    favorite INTEGER DEFAULT 0,
    date_added TEXT, date_started TEXT, date_completed TEXT, last_updated TEXT,
    PRIMARY KEY (user_id, anime_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_anime ON user_anime(user_id, anime_id);
CREATE INDEX IF NOT EXISTS idx_ua_user_status ON user_anime(user_id, status);
CREATE INDEX IF NOT EXISTS idx_ua_user_updated ON user_anime(user_id, last_updated);
CREATE INDEX IF NOT EXISTS idx_ua_user_favorite ON user_anime(user_id, favorite);
CREATE TABLE IF NOT EXISTS anime_relations (
    anime_id INTEGER NOT NULL, position INTEGER NOT NULL, relation TEXT NOT NULL,
    related_id INTEGER NOT NULL, title TEXT, type TEXT, image_url TEXT,
    year INTEGER, episodes INTEGER, cached_at REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_relations_anime ON anime_relations(anime_id);
CREATE TABLE IF NOT EXISTS api_cache (
    key TEXT PRIMARY KEY, data TEXT NOT NULL, fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS discovery_cache (
    section TEXT PRIMARY KEY, data TEXT NOT NULL,
    fetched_at REAL NOT NULL, expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    job_name TEXT PRIMARY KEY, last_run REAL,
    last_success INTEGER DEFAULT 0, last_error TEXT
);
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, token_hash TEXT NOT NULL,
    expires_at REAL NOT NULL, used INTEGER DEFAULT 0, created_at REAL NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS email_verification_codes (
    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, code_hash TEXT NOT NULL,
    created_at REAL NOT NULL, expires_at REAL NOT NULL,
    used INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL, anime_id INTEGER NOT NULL,
    episode_from INTEGER, episode_to INTEGER,
    status_from TEXT, status_to TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_id, created_at);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anime_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
    text TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(anime_id) REFERENCES anime(mal_id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_comments_anime ON comments(anime_id, created_at DESC);

CREATE TABLE IF NOT EXISTS comment_likes (
    comment_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (comment_id, user_id),
    FOREIGN KEY(comment_id) REFERENCES comments(id) ON DELETE CASCADE
);
"""


def get_db():
    if "db" not in g:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    if "is_admin" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    conn.commit()
    conn.close()


def init_app(app):
    init_db()
    app.teardown_appcontext(close_db)


def query(sql, args=()):
    return [dict(r) for r in get_db().execute(sql, args).fetchall()]


def query_one(sql, args=()):
    row = get_db().execute(sql, args).fetchone()
    return dict(row) if row else None


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid


def get_user_setting(user_id, key, default=None):
    row = query_one("SELECT value FROM user_settings WHERE user_id=? AND key=?", (user_id, key))
    return row["value"] if row else default


def set_user_setting(user_id, key, value):
    execute("INSERT INTO user_settings(user_id, key, value) VALUES(?,?,?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value",
            (user_id, key, str(value)))


def all_user_settings(user_id):
    out = dict(config.DEFAULT_SETTINGS)
    for row in query("SELECT key, value FROM user_settings WHERE user_id=?", (user_id,)):
        out[row["key"]] = row["value"]
    return out


def cache_get(key, max_age):
    row = query_one("SELECT data, fetched_at FROM api_cache WHERE key=?", (key,))
    if not row or time.time() - row["fetched_at"] > max_age:
        return None
    try:
        return json.loads(row["data"])
    except (TypeError, ValueError):
        return None


def cache_set(key, data):
    execute("INSERT INTO api_cache(key, data, fetched_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET data=excluded.data, fetched_at=excluded.fetched_at",
            (key, json.dumps(data), time.time()))


def cache_delete(key):
    execute("DELETE FROM api_cache WHERE key=?", (key,))


def cache_clear():
    execute("DELETE FROM api_cache")
    execute("DELETE FROM anime_relations")