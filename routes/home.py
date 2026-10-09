"""Home dashboard + activity feed."""
import datetime
from flask import Blueprint, render_template
import config, database
from api import anilist
from models import anime as M
from auth import login_required, get_current_user_id

bp = Blueprint("home", __name__)

JOIN = """
    SELECT ua.anime_id AS mal_id, ua.status, ua.current_episode, ua.total_episodes,
           ua.date_added, ua.last_updated, ua.favorite, ua.rewatch_count,
           a.title, a.image_url, a.type, a.year, a.score, a.episodes, a.duration
    FROM user_anime ua LEFT JOIN anime a ON a.mal_id = ua.anime_id
    WHERE ua.user_id = ?
"""


def _rows(sql, args=()):
    rows = M.hydrate(database.query(sql, args))
    for r in rows:
        r["favorite"] = bool(r.get("favorite"))
        if not r.get("total_episodes"):
            r["total_episodes"] = r.get("episodes")
        r["in_list"] = True
    return rows


def _week_schedule():
    items = database.cache_get("airing_week", config.CACHE_TTL["airing"])
    if items is None:
        try:
            items = anilist.fetch_schedule(days=7)
        except Exception:
            items = []
        database.cache_set("airing_week", items)
    return items or []


@bp.route("/")
@login_required
def home():
    uid = get_current_user_id()

    def section(where, order, limit):
        return _rows(JOIN + f" AND {where} ORDER BY {order} LIMIT {limit}", (uid,))

    continue_watching = section("ua.status='watching'", "ua.last_updated DESC", 10)
    recent_updated = section("1=1", "ua.last_updated DESC", 10)
    planned = section("ua.status='plan_to_watch'", "RANDOM()", 8)
    favorites = section("ua.favorite=1", "ua.last_updated DESC", 8)

    all_entries = _rows(JOIN, (uid,))
    totals = M.compute_totals(all_entries)
    totals["favorites"] = sum(1 for r in all_entries if r.get("favorite"))

    # Airing this week + next-episode stamps on continue-watching
    amap = {}
    for it in _week_schedule():
        amap.setdefault(it["mal_id"], it)
    for row in continue_watching:
        a = amap.get(row["mal_id"])
        if a:
            row["next_ep"] = a.get("episode")
            row["next_airing"] = a.get("airing_at")
    my_ids = {r["mal_id"] for r in all_entries}
    airing_week = []
    for mid, it in amap.items():
        if mid in my_ids:
            it = dict(it)
            e = M.get_entry(mid, uid)
            it["my_episode"] = e["current_episode"] if e else 0
            airing_week.append(it)
    airing_week.sort(key=lambda x: x.get("airing_at") or 0)
    airing_week = airing_week[:10]

    activity = database.query("""
        SELECT h.id, h.anime_id, h.episode_from, h.episode_to, h.status_from, h.status_to,
               h.created_at, a.title, a.image_url
        FROM history h LEFT JOIN anime a ON a.mal_id = h.anime_id
        WHERE h.user_id=? ORDER BY h.created_at DESC LIMIT 6
    """, (uid,))

    hour = datetime.datetime.now().hour
    greeting = ("Good evening" if hour >= 18 else "Good afternoon" if hour >= 12 else "Good morning")

    return render_template(
        "home.html", active="home", greeting=greeting,
        continue_watching=continue_watching, recent_updated=recent_updated,
        planned=planned, favorites=favorites, totals=totals,
        has_any=bool(all_entries), airing_week=airing_week, activity=activity,
    )


@bp.route("/activity")
@login_required
def activity_page():
    uid = get_current_user_id()
    events = database.query("""
        SELECT h.id, h.anime_id, h.episode_from, h.episode_to, h.status_from, h.status_to,
               h.created_at, a.title, a.image_url
        FROM history h LEFT JOIN anime a ON a.mal_id = h.anime_id
        WHERE h.user_id=? ORDER BY h.created_at DESC LIMIT 100
    """, (uid,))
    return render_template("activity.html", active="activity", events=events)


@bp.route("/recent")
@login_required
def recent():
    uid = get_current_user_id()
    entries = _rows(JOIN + " ORDER BY ua.last_updated DESC LIMIT 60", (uid,))
    return render_template("recent.html", active="recent", entries=entries)