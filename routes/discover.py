"""Discover rails, genres browse, seasonal page."""
import time
from flask import Blueprint, jsonify, render_template
import database, config
from api import anilist
from models import anime as M
from services.scheduler import (get_discovery, refresh_discovery,
                                force_refresh_discovery, DISCOVERY_SECTIONS)
from auth import login_required, get_current_user_id

bp = Blueprint("discover", __name__)

SECTIONS = [
    ("trending", "Trending Now"),
    ("seasonal", "This Season"),
    ("popular", "Most Popular"),
    ("top", "Top Rated"),
    ("upcoming", "Upcoming"),
    ("movies", "Top Movies"),
]

GENRES = ["Action", "Adventure", "Comedy", "Drama", "Fantasy", "Horror",
          "Mahou Shoujo", "Mecha", "Music", "Mystery", "Psychological",
          "Romance", "Sci-Fi", "Slice of Life", "Sports", "Supernatural",
          "Thriller"]


def _season_label():
    season, year = anilist.current_season()
    return f"{season.capitalize()} {year}"


def _mark_in_list(items):
    in_list = M.my_list_ids(get_current_user_id())
    for it in items:
        it["in_list"] = it["mal_id"] in in_list
    return items


@bp.route("/discover")
@login_required
def discover():
    return render_template("discover.html", active="discover",
                           sections=[{"key": k, "title": t} for k, t in SECTIONS],
                           season=_season_label())


@bp.route("/api/discover/<key>")
@login_required
def api_discover(key):
    if key not in DISCOVERY_SECTIONS:
        return jsonify({"error": "Unknown section.", "items": []}), 404
    try:
        items = _mark_in_list(get_discovery(key))
        return jsonify({"items": items, "sub": "Powered by AniList"})
    except Exception as e:
        return jsonify({"error": str(e), "items": []}), 500


@bp.post("/api/discover/refresh")
@login_required
def api_refresh():
    try:
        return jsonify(force_refresh_discovery())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/genres")
@login_required
def genres():
    return render_template("genres.html", active="genres", genres=GENRES)


@bp.route("/seasonal")
@login_required
def seasonal_page():
    cache_key = "seasonal_page"
    items = database.cache_get(cache_key, config.CACHE_TTL["browse"])
    if items is None:
        try:
            items = anilist.seasonal(24)
            database.cache_set(cache_key, items)
        except Exception:
            items = []
    return render_template("seasonal.html", active="seasonal",
                           items=_mark_in_list(items or []),
                           season=_season_label())

@bp.route("/studios")
@login_required
def studios_page():
    import json as _json
    from collections import Counter
    rows = database.query("SELECT studios FROM anime WHERE studios IS NOT NULL AND studios != '[]'")
    counts = Counter()
    for r in rows:
        try:
            for s in _json.loads(r["studios"] or "[]"):
                if s:
                    counts[s] += 1
        except ValueError:
            pass
    return render_template("studios.html", active="studios", studios=counts.most_common(80))


@bp.route("/studio/<path:name>")
@login_required
def studio_detail(name):
    rows = database.query("SELECT * FROM anime WHERE studios LIKE ?", (f'%"{name}"%',))
    entries = M.hydrate(rows)
    in_list = M.my_list_ids(get_current_user_id())
    for e in entries:
        e["in_list"] = e["mal_id"] in in_list
        e["total_episodes"] = e.get("episodes")
    entries.sort(key=lambda x: x.get("score") or 0, reverse=True)
    return render_template("studio.html", active="studios", name=name, entries=entries)