"""Background scheduler: discovery cache refresh + cleanup."""
import time, json, threading, logging
import database, config
from api import anilist

logger = logging.getLogger(__name__)

DISCOVERY_SECTIONS = {
    "trending": ("Trending Now", lambda: anilist.trending(20)),
    "seasonal": ("This Season", lambda: anilist.seasonal(20)),
    "popular": ("Most Popular", lambda: anilist.popular(20)),
    "top": ("Top Rated", lambda: anilist.top_rated(20)),
    "upcoming": ("Upcoming", lambda: anilist.upcoming(20)),
    "movies": ("Top Movies", lambda: anilist.top_movies(20)),
}
DISCOVERY_TTL = config.CACHE_TTL["discovery"]


def get_discovery(key):
    if key not in DISCOVERY_SECTIONS:
        return []
    row = database.query_one(
        "SELECT data, expires_at FROM discovery_cache WHERE section=?", (key,))
    now = time.time()
    if row and row["expires_at"] > now:
        try:
            return json.loads(row["data"])
        except Exception:
            pass
    return refresh_discovery(key)


def refresh_discovery(key):
    if key not in DISCOVERY_SECTIONS:
        return []
    _, fetch_fn = DISCOVERY_SECTIONS[key]
    try:
        items = fetch_fn()
    except Exception as e:
        logger.error(f"Discovery fetch failed for {key}: {e}")
        row = database.query_one("SELECT data FROM discovery_cache WHERE section=?", (key,))
        if row:
            try:
                return json.loads(row["data"])
            except Exception:
                pass
        return []
    now = time.time()
    database.execute("""
        INSERT INTO discovery_cache(section, data, fetched_at, expires_at) VALUES(?,?,?,?)
        ON CONFLICT(section) DO UPDATE SET data=excluded.data,
            fetched_at=excluded.fetched_at, expires_at=excluded.expires_at
    """, (key, json.dumps(items), now, now + DISCOVERY_TTL))
    return items


def refresh_all_discovery():
    for key in DISCOVERY_SECTIONS:
        try:
            refresh_discovery(key)
            logger.info(f"  ✓ discovery:{key}")
        except Exception as e:
            logger.error(f"  ✗ discovery:{key}: {e}")
        time.sleep(0.6)


def cleanup_expired_cache():
    cutoff = time.time() - 30 * 86400
    database.execute("DELETE FROM api_cache WHERE fetched_at < ?", (cutoff,))
    database.execute("DELETE FROM password_reset_tokens WHERE expires_at < ? OR used=1",
                     (time.time(),))


def _loop():
    while True:
        time.sleep(6 * 3600)
        try:
            refresh_all_discovery()
            cleanup_expired_cache()
        except Exception as e:
            logger.error(f"Scheduler error: {e}")


_thread = None


def init_scheduler():
    global _thread
    if _thread and _thread.is_alive():
        return
    logger.info("Initial discovery refresh...")
    refresh_all_discovery()
    _thread = threading.Thread(target=_loop, daemon=True, name="scheduler")
    _thread.start()
    logger.info("Scheduler started")


def force_refresh_discovery():
    refresh_all_discovery()
    return {"ok": True, "message": "Discovery cache refreshed"}