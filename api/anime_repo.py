"""Repository layer — AniList calls with DB + cache fallback."""
import time
import database, config
from models import anime as M
from api import anilist
from api.anilist import ApiError, NotFoundError


def get_anime(mal_id, force=False):
    """Get full anime metadata, falling back to DB if API fails."""
    row = M.get_anime_row(mal_id)
    
    # If it's a synthetic ID (from custom import), just return DB row
    if mal_id < 1:
        if row: 
            return row
        raise NotFoundError(f"Anime {mal_id} not found")

    # Check cache validity
    if row and not force and _valid(mal_id):
        return row
        
    try:
        data = anilist.fetch_metadata(mal_id)
        M.store_anime(data, full=True)
        _mark(mal_id)
        return M.get_anime_row(mal_id)
    except (ApiError, NotFoundError) as e:
        print(f"[anime_repo] API error for {mal_id}: {e}")
        # Fallback to DB if we have it!
        if row:
            print(f"[anime_repo] Falling back to cached DB data for {mal_id}")
            return row
        raise


def _valid(anime_id):
    if not _has_meta_table():
        return False
    row = database.query_one(
        "SELECT expires_at FROM anime_cache_meta WHERE anime_id=?", (anime_id,))
    return row and row["expires_at"] and row["expires_at"] > time.time()


def _has_meta_table():
    r = database.query_one(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='anime_cache_meta'")
    return bool(r)


def _mark(anime_id):
    if not _has_meta_table():
        database.execute("""CREATE TABLE IF NOT EXISTS anime_cache_meta(
            anime_id INTEGER PRIMARY KEY, source TEXT DEFAULT 'anilist',
            fetched_at REAL, expires_at REAL)""")
    database.execute(
        "INSERT INTO anime_cache_meta(anime_id, source, fetched_at, expires_at) VALUES(?,?,?,?) "
        "ON CONFLICT(anime_id) DO UPDATE SET fetched_at=excluded.fetched_at, expires_at=excluded.expires_at",
        (anime_id, "anilist", time.time(), time.time() + config.CACHE_TTL["anime"]))


def get_relations(mal_id):
    try:
        return M.get_relations(mal_id)
    except ApiError:
        return []


def get_characters(mal_id):
    cache_key = f"chars:{mal_id}"
    hit = database.cache_get(cache_key, config.CACHE_TTL["characters"])
    if hit is not None:
        return hit
    try:
        chars = anilist.fetch_characters(mal_id)
    except ApiError:
        return []
    database.cache_set(cache_key, chars)
    return chars