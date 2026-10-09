"""Anime models and business logic."""
import datetime, json, time
import config, database
from api import anilist
from api.anilist import ApiError, NotFoundError

STATUSES = ["watching", "completed", "plan_to_watch", "on_hold", "dropped"]
STATUS_LABELS = {
    "watching": "Watching", "completed": "Completed",
    "plan_to_watch": "Plan to Watch", "on_hold": "On Hold", "dropped": "Dropped",
}
STATUS_COLORS = {
    "watching": "#4da3ff", "completed": "#3ddc97", "plan_to_watch": "#8b93a7",
    "on_hold": "#ffb454", "dropped": "#ff6b6b",
}
CATEGORY_ORDER = ["Sequel", "Prequel", "Side Story", "Spin Off", "Alternative",
                  "Summary", "Adaptation", "Parent", "Character", "Source", "Other"]
JSON_FIELDS = ("genres", "themes", "studios", "streaming", "synonyms")


def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def store_anime(a, full=True):
    db = database.get_db()
    existing = db.execute("SELECT mal_id FROM anime WHERE mal_id=?", (a["mal_id"],)).fetchone()
    vals = (
        a["title"], a.get("title_english"), a.get("title_japanese"), a.get("title_romaji"),
        json.dumps(a.get("synonyms") or []),
        a.get("type"), a.get("episodes"), a.get("status"), 1 if a.get("airing") else 0,
        a.get("score"), a.get("popularity"), a.get("members"), a.get("favorites"),
        a.get("year"), a.get("season"), a.get("aired_from"), a.get("aired_to"),
        a.get("duration"), a.get("source"), a.get("synopsis") or "",
        a.get("image_url"), a.get("trailer_url"),
        json.dumps(a.get("genres") or []), json.dumps(a.get("tags") or a.get("themes") or []),
        json.dumps(a.get("studios") or []), json.dumps(a.get("streaming") or []),
    )
    if existing and full:
        db.execute("""UPDATE anime SET title=?, title_english=?, title_japanese=?, title_romaji=?,
            synonyms=?, type=?, episodes=?, status=?, airing=?, score=?, popularity=?, members=?,
            favorites=?, year=?, season=?, aired_from=?, aired_to=?, duration=?, source=?,
            synopsis=?, image_url=?, trailer_url=?, genres=?, themes=?, studios=?, streaming=?
            WHERE mal_id=?""", vals + (a["mal_id"],))
    elif not existing:
        db.execute("""INSERT INTO anime(mal_id, title, title_english, title_japanese, title_romaji,
            synonyms, type, episodes, status, airing, score, popularity, members, favorites,
            year, season, aired_from, aired_to, duration, source, synopsis, image_url,
            trailer_url, genres, themes, studios, streaming)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (a["mal_id"],) + vals)
    db.commit()


def hydrate(rows):
    out = []
    for r in rows:
        d = dict(r)
        for k in JSON_FIELDS:
            v = d.get(k)
            if isinstance(v, str):
                try:
                    d[k] = json.loads(v)
                except ValueError:
                    d[k] = []
        out.append(d)
    return out


def get_anime_row(mal_id):
    row = database.query_one("SELECT * FROM anime WHERE mal_id=?", (mal_id,))
    return hydrate([row])[0] if row else None


def get_entry(mal_id, user_id):
    return database.query_one(
        "SELECT * FROM user_anime WHERE user_id=? AND anime_id=?", (user_id, mal_id))


def my_list_ids(user_id):
    return {r["anime_id"] for r in
            database.query("SELECT anime_id FROM user_anime WHERE user_id=?", (user_id,))}


def compute_totals(entries):
    t = {"entries": len(entries), "completed": 0, "watching": 0, "planned": 0,
         "hold": 0, "dropped": 0, "episodes": 0, "minutes": 0.0, "scores": []}
    for e in entries:
        st = e.get("status")
        total = e.get("total_episodes") or e.get("episodes") or 0
        cur = e.get("current_episode") or 0
        if st == "completed":
            t["completed"] += 1
            watched = total if total else cur
        elif st == "plan_to_watch":
            t["planned"] += 1
            watched = 0
        else:
            watched = cur
            key = "watching" if st == "watching" else ("hold" if st == "on_hold" else "dropped")
            t[key] += 1
        t["episodes"] += watched
        if e.get("duration"):
            t["minutes"] += watched * (e["duration"] / 60.0)
        if e.get("score"):
            s = float(e["score"])
            if s > 10:
                s = s / 10.0
            t["scores"].append(s)
    t["hours"] = round(t["minutes"] / 60.0, 1)
    t["avg_score"] = round(sum(t["scores"]) / len(t["scores"]), 2) if t["scores"] else None
    return t


def store_relations(mal_id, edges):
    db = database.get_db()
    db.execute("DELETE FROM anime_relations WHERE anime_id=?", (mal_id,))
    now = time.time()
    for i, e in enumerate(edges):
        db.execute("""INSERT INTO anime_relations(anime_id, position, relation, related_id,
            title, type, image_url, year, episodes, cached_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (mal_id, i, e["relation"], e.get("mal_id") or e.get("related_id"),
             e["title"], e.get("type"), e.get("image_url"), e.get("year"),
             e.get("episodes"), now))
    db.commit()


def get_relations(mal_id, force=False):
    rows = database.query(
        "SELECT * FROM anime_relations WHERE anime_id=? ORDER BY position", (mal_id,))
    fresh = database.cache_get(f"relfresh:{mal_id}", config.CACHE_TTL["relations"])

    def norm(rs):
        out = []
        for r in rs:
            d = dict(r)
            d["mal_id"] = d.pop("related_id")
            out.append(d)
        return out

    if rows and fresh and not force:
        return norm(rows)
    try:
        edges = anilist.relations(mal_id)
    except ApiError:
        if rows:
            return norm(rows)
        raise
    store_relations(mal_id, edges)
    database.cache_set(f"relfresh:{mal_id}", {"n": len(edges)})
    return edges


def relation_to_card(e, in_list):
    mid = e.get("mal_id") or e.get("related_id")
    return {"mal_id": mid, "title": e.get("title"), "type": e.get("type"),
            "year": e.get("year"), "image_url": e.get("image_url"),
            "episodes": e.get("episodes"), "relation": e.get("relation"),
            "in_list": mid in in_list}


def build_timeline(mal_id, own_edges, in_list, max_steps=6):
    own = get_anime_row(mal_id)
    own_node = {
        "mal_id": mal_id,
        "title": own.get("title") if own else f"Anime #{mal_id}",
        "image_url": own.get("image_url") if own else None,
        "year": own.get("year") if own else None,
        "type": own.get("type") if own else None,
        "episodes": own.get("episodes") if own else None,
        "in_list": mal_id in in_list, "current": True,
    }
    nodes = {mal_id: own_node}
    order = [mal_id]

    def from_edge(e):
        return {"mal_id": e["mal_id"], "title": e["title"], "image_url": e.get("image_url"),
                "year": e.get("year"), "type": e.get("type"), "episodes": e.get("episodes"),
                "in_list": e["mal_id"] in in_list}

    cur = own_edges
    for _ in range(max_steps):
        pre = next((e for e in cur if e["relation"] == "Prequel"), None)
        if not pre or pre["mal_id"] in nodes:
            break
        nodes[pre["mal_id"]] = from_edge(pre)
        order.insert(0, pre["mal_id"])
        try:
            cur = get_relations(pre["mal_id"])
        except Exception:
            break

    cur = own_edges
    for _ in range(max_steps):
        seq = next((e for e in cur if e["relation"] == "Sequel"), None)
        if not seq or seq["mal_id"] in nodes:
            break
        nodes[seq["mal_id"]] = from_edge(seq)
        order.append(seq["mal_id"])
        try:
            cur = get_relations(seq["mal_id"])
        except Exception:
            break

    return [nodes[m] for m in order] if len(order) > 1 else []

def profile_bundle(uid, limit=10):
    """Recent entries + totals for profile pages."""
    entries = hydrate(database.query("""
        SELECT ua.anime_id AS mal_id, ua.status, ua.current_episode, ua.total_episodes,
               ua.favorite, a.title, a.image_url, a.type, a.year, a.score, a.episodes
        FROM user_anime ua LEFT JOIN anime a ON a.mal_id = ua.anime_id
        WHERE ua.user_id=? ORDER BY ua.last_updated DESC LIMIT ?
    """, (uid, limit)))
    for e in entries:
        e["total_episodes"] = e.get("total_episodes") or e.get("episodes")
        e["in_list"] = True
        e["favorite"] = bool(e.get("favorite"))
    all_rows = hydrate(database.query("""
        SELECT ua.status, ua.current_episode, ua.total_episodes, ua.favorite,
               a.score, a.duration, a.episodes
        FROM user_anime ua LEFT JOIN anime a ON a.mal_id = ua.anime_id
        WHERE ua.user_id=?
    """, (uid,)))
    for r in all_rows:
        r["total_episodes"] = r.get("total_episodes") or r.get("episodes")
    totals = compute_totals(all_rows)
    totals["favorites"] = sum(1 for r in all_rows if r.get("favorite"))
    return entries, totals