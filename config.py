"""Central configuration."""
import os
from os.path import join, dirname
import secrets as _secrets

from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "anime.db")

APP_NAME = "AniLog"
APP_VERSION = "4.6.0"
APP_TAGLINE = "Your personal anime tracker"

def _load_secret():
    """Secret key that survives restarts (stored in data/secret.key)."""
    env = os.getenv("SECRET_KEY")
    if env:
        return env
    key_file = os.path.join(DATA_DIR, "secret.key")
    try:
        if os.path.exists(key_file):
            with open(key_file) as f:
                val = f.read().strip()
            if val:
                return val
        os.makedirs(DATA_DIR, exist_ok=True)
        val = _secrets.token_hex(32)
        with open(key_file, "w") as f:
            f.write(val)
        return val
    except OSError:
        return "dev-fallback-key-change-me"

SECRET_KEY = _load_secret()
SESSION_DAYS = 30


SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")

ANILIST_URL = "https://graphql.anilist.co"
REQUEST_TIMEOUT = 14
ANILIST_MIN_INTERVAL = 0.55

CACHE_TTL = {
    "anime": 60 * 60 * 24 * 7,
    "relations": 60 * 60 * 24 * 7,
    "characters": 60 * 60 * 24 * 7,
    "search": 60 * 30,
    "browse": 60 * 60 * 6,
    "trending": 60 * 60 * 6,
    "airing": 60 * 60 * 3,
    "discovery": 60 * 60 * 24,
}

DEFAULT_SETTINGS = {
    "theme": "dark",
    "animations": "on",
    "default_view": "grid",
    "default_sort": "updated",
    "default_status": "watching",
    "auto_complete": "on",
    "accent_color": "purple",
    "card_layout": "compact",
    "profile_visibility": "public",
}