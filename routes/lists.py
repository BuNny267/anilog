"""My Anime List + public user lists + mutation endpoints."""
from flask import Blueprint, jsonify, render_template, request, redirect, url_for
import database
from models import anime as M
from auth import login_required, get_current_user_id

bp = Blueprint("lists", __name__)

TABS = [("all", "All")] + [(s, M.STATUS_LABELS[s]) for s in
                           ["watching", "completed", "plan_to_watch", "on_hold", "dropped"]]

SORTS = {
    "updated": "ua.last_updated DESC",
    "added": "ua.date_added DESC",
    "title": "a.title IS NULL, a.title COLLATE NOCASE ASC",
    "score": "a.score IS NULL, a.score DESC",
    "year": "a.year IS NULL, a.year DESC",
    "progress": ("(CASE WHEN COALESCE(ua.total_episodes, a.episodes, 0) > 0 "
                 "THEN ua.current_episode * 1.0 / COALESCE(ua.total_episodes, a.episodes) "
                 "ELSE 0 END) DESC"),
}
SORT_LABELS = {
    "updated": "Recently updated", "added": "Recently added", "title": "Title",
    "score": "Community score", "year": "Release year", "progress": "Progress",
}

BASE_SELECT = """
SELECT ua.anime_id AS mal_id, ua.status, ua.current_episode,
       ua.total_episodes AS ua_total, ua.notes, ua.rewatch_count, ua.favorite,
       ua.date_added, ua.date_started, ua.date_completed, ua.last_updated,
       a.title, a.title_japanese, a.type, a.year, a.score, a.episodes,
       a.image_url, a.genres, a.duration
FROM user_anime ua LEFT JOIN anime a ON a.mal_id = ua.anime_id
WHERE ua.user_id = ?
"""


def _counts(uid):
    rows = database.query(
        "SELECT status, COUNT(*) AS c FROM user_anime WHERE user_id=? GROUP BY status", (uid,))
    d = {s: 0 for s in M.STATUSES}
    for r in rows:
        d[r["status"]] = r["c"]
    d["all"] = sum(d.values())
    return d


def _entry_dicts(rows, view_only=False):
    out = []
    for r in M.hydrate(rows):
        r["total_episodes"] = r.pop("ua_total", None) or r.get("episodes")
        if view_only:
            r["in_list"] = False
            r["view_only"] = True
            r["favorite"] = False
        else:
            r["in_list"] = True
            r["favorite"] = bool(r.get("favorite"))
        out.append(r)
    return out


def _render_list(status, owner_id, owner_user=None):
    uid = get_current_user_id()
    own = owner_user is None or owner_user["id"] == uid

    sort = request.args.get("sort") or database.get_user_setting(uid, "default_sort", "updated")
    if sort not in SORTS:
        sort = "updated"
    view = request.args.get("view") or database.get_user_setting(uid, "default_view", "grid")
    if view not in ("grid", "list"):
        view = "grid"

    sql, args = BASE_SELECT, [owner_id]
    if status != "all":
        sql += " AND ua.status = ?"
        args.append(status)

    q = request.args.get("q", "").strip()
    if q:
        sql += " AND a.title LIKE ?"
        args.append(f"%{q}%")
    genre = request.args.get("genre", "").strip()
    if genre:
        sql += " AND (a.genres LIKE ? OR a.themes LIKE ?)"
        args += [f'%"{genre}"%', f'%"{genre}"%']
    year = request.args.get("year", "").strip()
    if year.isdigit():
        sql += " AND a.year = ?"
        args.append(int(year))
    ftype = request.args.get("type", "").strip()
    if ftype:
        sql += " AND a.type = ?"
        args.append(ftype)
    min_score = request.args.get("score", "").strip()
    if min_score.isdigit():
        sql += " AND a.score >= ?"
        args.append(int(min_score) * 10)
    prog = request.args.get("prog", "").strip()
    tot = "COALESCE(ua.total_episodes, a.episodes, 0)"
    if prog == "partial":
        sql += f" AND ua.current_episode > 0 AND ua.current_episode < {tot}"
    elif prog == "not_started":
        sql += " AND ua.current_episode = 0"
    elif prog == "finished":
        sql += f" AND {tot} > 0 AND ua.current_episode >= {tot}"

    sql += f" ORDER BY {SORTS[sort]}, ua.last_updated DESC"
    entries = _entry_dicts(database.query(sql, args), view_only=not own)

    my_rows = database.query(
        "SELECT a.genres, a.year, a.type FROM user_anime ua "
        "JOIN anime a ON a.mal_id = ua.anime_id WHERE ua.user_id=?", (owner_id,))
    genre_counts, years, types = {}, set(), set()
    import json as _json
    for r in my_rows:
        try:
            for gname in _json.loads(r["genres"] or "[]"):
                genre_counts[gname] = genre_counts.get(gname, 0) + 1
        except ValueError:
            pass
        if r["year"]:
            years.add(r["year"])
        if r["type"]:
            types.add(r["type"])

    if own:
        list_base = "/list"
        page_title = "My Anime List"
    else:
        list_base = f"/user/{owner_user['username']}/list"
        page_title = f"{owner_user['display_name'] or owner_user['username']}'s List"

    return render_template(
        "list.html", active="list", status=status, tabs=TABS, counts=_counts(owner_id),
        entries=entries, sort=sort, sorts=SORTS, sort_labels=SORT_LABELS, view=view,
        genres=sorted(genre_counts, key=lambda x: (-genre_counts[x], x)),
        years=sorted(years, reverse=True), types=sorted(types),
        filters={"q": q, "genre": genre, "year": year, "type": ftype,
                 "score": min_score, "prog": prog, "notes": ""},
        list_base=list_base, page_title=page_title,
        is_own_list=own, owner_user=owner_user,
    )


@bp.route("/list")
@login_required
def list_root():
    uid = get_current_user_id()
    default_status = database.get_user_setting(uid, "default_status", "watching")
    return _render_list(default_status if default_status in dict(TABS) else "all", uid)


@bp.route("/list/<status>")
@login_required
def list_status(status):
    if status not in dict(TABS):
        status = "all"
    return _render_list(status, get_current_user_id())


@bp.route("/user/<username>/list")
@login_required
def user_list_root(username):
    return _user_list(username, "all")


@bp.route("/user/<username>/list/<status>")
@login_required
def user_list_status(username, status):
    return _user_list(username, status)


def _user_list(username, status):
    owner = database.query_one("SELECT * FROM users WHERE username=?", (username,))
    if not owner:
        return render_template("error.html", code=404, active="",
                               title="User not found", message="This user does not exist."), 404
    uid = get_current_user_id()
    if owner["id"] == uid:
        return redirect(url_for("lists.list_status", status=status))
    visibility = database.get_user_setting(owner["id"], "profile_visibility", "public")
    if visibility != "public":
        return redirect(url_for("users.user_profile", username=username))
    if status not in dict(TABS):
        status = "all"
    return _render_list(status, owner["id"], owner)


def _clamp_ep(ep, total):
    ep = max(0, int(ep or 0))
    if total:
        ep = min(ep, int(total))
    return ep


def _ensure_anime_row(mal_id, payload):
    if database.query_one("SELECT mal_id FROM anime WHERE mal_id=?", (mal_id,)):
        return
    title = (payload.get("title") or "").strip()
    if not title:
        raise ValueError("Anime title is required")
    database.execute(
        "INSERT INTO anime(mal_id, title, image_url, type, year, score, episodes) "
        "VALUES(?,?,?,?,?,?,?)",
        (mal_id, title[:300], payload.get("image_url"), payload.get("type"),
         payload.get("year"), payload.get("score"),
         payload.get("episodes") or None))


@bp.post("/api/list/save")
@login_required
def save_entry():
    uid = get_current_user_id()
    p = request.get_json(silent=True) or {}
    try:
        mal_id = int(p.get("mal_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Missing anime id."}), 400

    status = p.get("status")
    if status and status not in M.STATUSES:
        return jsonify({"ok": False, "error": "Invalid status."}), 400
    notes = (p.get("notes") or "").strip()[:4000]

    try:
        _ensure_anime_row(mal_id, p)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    row = M.get_anime_row(mal_id) or {}
    total = p.get("total_episodes") or p.get("episodes") or row.get("episodes")
    try:
        total = int(total) if int(total) > 0 else None
    except (TypeError, ValueError):
        total = None

    existing = M.get_entry(mal_id, uid)
    now = M.now_str()
    old_status = existing["status"] if existing else None
    new_status = status or (existing["status"] if existing else "plan_to_watch")

    ep_raw = p.get("current_episode")
    ep = (existing["current_episode"] if existing and ep_raw is None
          else int(ep_raw or 0))

    if new_status == "completed" and total:
        ep = total
    elif new_status == "watching" and old_status == "completed":
        ep = 0
    elif new_status == "plan_to_watch":
        ep = 0
    if total:
        ep = max(0, min(ep, total))

    date_started = existing["date_started"] if existing else None
    date_completed = existing["date_completed"] if existing else None
    if new_status == "watching" and not date_started:
        date_started = now
    if new_status == "completed" and not date_completed:
        date_completed = now
    if new_status == "watching" and old_status == "completed":
        date_completed = None

    suggest_complete = False
    auto = database.get_user_setting(uid, "auto_complete", "on") == "on"
    if total and ep >= total and new_status == "watching":
        if auto:
            new_status = "completed"
            date_completed = date_completed or now
        else:
            suggest_complete = True

    fav = 1 if p.get("favorite") else (existing.get("favorite", 0) if existing else 0)

    if existing:
        database.execute("""
            UPDATE user_anime SET status=?, current_episode=?, total_episodes=?,
                notes=?, date_started=?, date_completed=?, last_updated=?, favorite=?
            WHERE user_id=? AND anime_id=?
        """, (new_status, ep, total,
              notes if "notes" in p else existing["notes"],
              date_started, date_completed, now, fav, uid, mal_id))
        if ep != existing["current_episode"] or new_status != existing["status"]:
            database.execute(
                "INSERT INTO history(user_id, anime_id, episode_from, episode_to, status_from, status_to) "
                "VALUES(?,?,?,?,?,?)",
                (uid, mal_id, existing["current_episode"], ep, existing["status"], new_status))
    else:
        database.execute("""
            INSERT INTO user_anime(user_id, anime_id, status, current_episode, total_episodes,
                notes, date_added, date_started, date_completed, last_updated, favorite)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """, (uid, mal_id, new_status, ep, total, notes, now,
              date_started, date_completed, now, fav))
        database.execute(
            "INSERT INTO history(user_id, anime_id, episode_from, episode_to, status_from, status_to) "
            "VALUES(?,?,?,?,?,?)", (uid, mal_id, 0, ep, None, new_status))

    entry = M.get_entry(mal_id, uid)
    return jsonify({
        "ok": True, "suggest_complete": suggest_complete,
        "entry": {
            "mal_id": mal_id, "status": entry["status"],
            "current_episode": entry["current_episode"],
            "total_episodes": entry["total_episodes"] or total,
            "notes": entry["notes"], "favorite": bool(entry.get("favorite", 0)),
        },
    })


@bp.post("/api/list/progress")
@login_required
def progress_entry():
    uid = get_current_user_id()
    p = request.get_json(silent=True) or {}
    try:
        mal_id = int(p.get("mal_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Missing anime id."}), 400

    row = M.get_anime_row(mal_id) or {}
    entry = M.get_entry(mal_id, uid)
    if not entry:
        if not row.get("title"):
            return jsonify({"ok": False, "error": "Open the anime page to add it first."}), 400
        _ensure_anime_row(mal_id, row)
        database.execute(
            "INSERT INTO user_anime(user_id, anime_id, status, current_episode, total_episodes, "
            "date_added, date_started, last_updated) VALUES(?,?,?,?,?,?,?,?)",
            (uid, mal_id, "watching", 0, row.get("episodes"),
             M.now_str(), M.now_str(), M.now_str()))
        entry = M.get_entry(mal_id, uid)

    total = entry["total_episodes"] or row.get("episodes")
    cur = entry["current_episode"]
    if "set" in p:
        try:
            new_ep = int(p["set"])
        except (TypeError, ValueError):
            new_ep = cur
    else:
        try:
            new_ep = cur + int(p.get("delta") or 0)
        except (TypeError, ValueError):
            new_ep = cur
    new_ep = _clamp_ep(new_ep, total)

    status = entry["status"]
    if new_ep > 0 and status == "plan_to_watch":
        status = "watching"

    suggest_complete = False
    auto = database.get_user_setting(uid, "auto_complete", "on") == "on"
    if total and new_ep >= total and status == "watching":
        if auto:
            status = "completed"
        else:
            suggest_complete = True

    now = M.now_str()
    database.execute("""
        UPDATE user_anime SET current_episode=?, status=?, total_episodes=?,
            date_started=COALESCE(date_started, ?), date_completed=?, last_updated=?
        WHERE user_id=? AND anime_id=?
    """, (new_ep, status, total,
          now if status == "watching" else entry["date_started"],
          now if status == "completed" else entry["date_completed"],
          now, uid, mal_id))

    if new_ep != cur:
        database.execute(
            "INSERT INTO history(user_id, anime_id, episode_from, episode_to, status_from, status_to) "
            "VALUES(?,?,?,?,?,?)", (uid, mal_id, cur, new_ep, entry["status"], status))

    return jsonify({
        "ok": True, "suggest_complete": suggest_complete,
        "entry": {"mal_id": mal_id, "status": status, "current_episode": new_ep,
                  "total_episodes": total, "notes": entry["notes"],
                  "favorite": bool(entry.get("favorite", 0))},
    })


@bp.post("/api/list/favorite")
@login_required
def toggle_favorite():
    uid = get_current_user_id()
    p = request.get_json(silent=True) or {}
    try:
        mal_id = int(p.get("mal_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Missing anime id."}), 400

    entry = M.get_entry(mal_id, uid)
    if not entry:
        return jsonify({"ok": False, "error": "Add to your list first."}), 400

    new_val = 0 if entry.get("favorite") else 1
    database.execute(
        "UPDATE user_anime SET favorite=?, last_updated=? WHERE user_id=? AND anime_id=?",
        (new_val, M.now_str(), uid, mal_id))
    return jsonify({"ok": True, "mal_id": mal_id, "favorite": bool(new_val)})


@bp.post("/api/list/delete")
@login_required
def delete_entry():
    uid = get_current_user_id()
    p = request.get_json(silent=True) or {}
    try:
        mal_id = int(p.get("mal_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Missing anime id."}), 400
    database.execute("DELETE FROM user_anime WHERE user_id=? AND anime_id=?", (uid, mal_id))
    return jsonify({"ok": True})


@bp.route("/api/list/stats")
@login_required
def list_stats():
    uid = get_current_user_id()
    rows = database.query("""
        SELECT ua.status, ua.current_episode, ua.total_episodes, ua.favorite,
               a.score, a.duration, a.episodes
        FROM user_anime ua LEFT JOIN anime a ON a.mal_id = ua.anime_id
        WHERE ua.user_id = ?
    """, (uid,))
    entries = M.hydrate(rows)
    totals = M.compute_totals(entries)
    totals["favorites"] = sum(1 for r in entries if r.get("favorite"))
    return jsonify({"totals": totals})