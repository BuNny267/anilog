"""Anime detail page + franchise + characters + recommendations."""
import json as _json
from flask import Blueprint, jsonify, render_template, session
import database
from api import ApiError, NotFoundError
from models import anime as M
from services import anime_repo
from auth import login_required, get_current_user_id

bp = Blueprint("anime", __name__)


@bp.route("/anime/<int:mal_id>")
@login_required
def detail(mal_id):
    uid = get_current_user_id()
    meta, error = None, None
    try:
        meta = anime_repo.get_anime(mal_id)
    except NotFoundError:
        return render_template("error.html", code=404, active="",
                               title="Anime not found",
                               message="This anime does not exist."), 404
    except ApiError as exc:
        error = str(exc)

    entry = M.get_entry(mal_id, uid)
    sheet_data = None
    if meta:
        sheet_data = {
            "mal_id": mal_id, "title": meta["title"], "image_url": meta["image_url"],
            "type": meta["type"], "year": meta["year"], "score": meta["score"],
            "episodes": meta["episodes"], "in_list": bool(entry),
            "status": entry["status"] if entry else "",
            "current_episode": entry["current_episode"] if entry else 0,
            "notes": entry["notes"] if entry else "",
            "favorite": bool(entry["favorite"]) if entry else False,
        }
    return render_template("anime.html", active="", meta=meta, entry=entry,
                           sheet_data=sheet_data, error=error, mal_id=mal_id)


@bp.route("/api/anime/<int:mal_id>/franchise")
@login_required
def franchise(mal_id):
    in_list = M.my_list_ids(get_current_user_id())
    try:
        edges = anime_repo.get_relations(mal_id)
    except ApiError as exc:
        return jsonify({"error": str(exc)})

    groups = {}
    for e in edges:
        groups.setdefault(e["relation"], []).append(e)
    categories = []
    for label in M.CATEGORY_ORDER:
        if label in groups:
            categories.append({"label": label,
                               "items": [M.relation_to_card(e, in_list) for e in groups[label]]})
    for label in sorted(set(groups) - set(M.CATEGORY_ORDER)):
        categories.append({"label": label,
                           "items": [M.relation_to_card(e, in_list) for e in groups[label]]})

    own_edges = [{"relation": e["relation"],
                  "mal_id": e.get("mal_id") or e.get("related_id"),
                  "title": e["title"], "type": e["type"], "year": e["year"],
                  "episodes": e["episodes"], "image_url": e["image_url"]} for e in edges]
    return jsonify({"categories": categories,
                    "timeline": M.build_timeline(mal_id, own_edges, in_list)})


@bp.route("/api/anime/<int:mal_id>/characters")
@login_required
def characters(mal_id):
    return jsonify({"characters": anime_repo.get_characters(mal_id)})


@bp.post("/api/anime/<int:mal_id>/rewatch")
@login_required
def rewatch(mal_id):
    uid = get_current_user_id()
    entry = M.get_entry(mal_id, uid)
    if not entry:
        return jsonify({"ok": False, "error": "Not in your list"}), 400
    database.execute(
        "UPDATE user_anime SET rewatch_count=?, current_episode=0, status='watching', "
        "date_completed=NULL, last_updated=? WHERE user_id=? AND anime_id=?",
        (entry["rewatch_count"] + 1, M.now_str(), uid, mal_id))
    return jsonify({"ok": True, "rewatch_count": entry["rewatch_count"] + 1})


@bp.route("/api/anime/<int:mal_id>/recommendations")
@login_required
def recommendations(mal_id):
    """Fetch recommendations from AniList API + user's list."""
    import json as _json
    from api import anilist as anilist_api
    
    current = database.query_one(
        "SELECT type, genres FROM anime WHERE mal_id=?", (mal_id,))
    if not current:
        return jsonify({"items": []})
    
    try:
        cur_genres = set(_json.loads(current["genres"] or "[]"))
    except Exception:
        cur_genres = set()
    
    uid = session.get("user_id")
    results = []
    
    # 1) Try user's list first
    if uid and cur_genres:
        rows = database.query("""
            SELECT a.mal_id, a.title, a.image_url, a.type, a.year, a.score, a.episodes,
                   a.genres, ua.favorite, ua.current_episode, ua.total_episodes, ua.status
            FROM user_anime ua JOIN anime a ON a.mal_id = ua.anime_id
            WHERE ua.user_id=? AND a.mal_id != ?
        """, (uid, mal_id))
        
        scored = []
        for row in rows:
            try:
                rg = set(_json.loads(row["genres"] or "[]"))
            except Exception:
                rg = set()
            overlap = len(cur_genres & rg)
            if row["type"] == current["type"]:
                overlap += 0.5
            sv = row.get("score") or 0
            sv = sv / 10.0 if sv > 10 else sv
            if sv >= 7.5:
                overlap += 0.3
            if overlap >= 1:
                scored.append((row, overlap))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        results = [r[0] for r in scored[:4]]
        for r in results:
            r["in_list"] = True
            r["favorite"] = bool(r.get("favorite"))
    
    # 2) Fetch NEW recommendations from AniList API
    if len(results) < 8:
        try:
            # Use AniList's recommendation system
            query = """
            query ($idMal: Int) {
              Media(idMal: $idMal, type: ANIME) {
                recommendations(perPage: 10, sort: RATING_DESC) {
                  nodes {
                    mediaRecommendation {
                      idMal
                      title { userPreferred }
                      type
                      format
                      episodes
                      seasonYear
                      averageScore
                      coverImage { medium large }
                    }
                  }
                }
              }
            }
            """
            
            data = anilist_api._query(query, {"idMal": mal_id})
            media = data.get("Media")
            if media:
                recs = (media.get("recommendations") or {}).get("nodes") or []
                for rec in recs:
                    rec_media = rec.get("mediaRecommendation")
                    if not rec_media or not rec_media.get("idMal"):
                        continue
                    
                    # Skip if already in results
                    if any(r["mal_id"] == rec_media["idMal"] for r in results):
                        continue
                    
                    # Skip if it's the current anime
                    if rec_media["idMal"] == mal_id:
                        continue
                    
                    cover = rec_media.get("coverImage") or {}
                    FMT = {"TV": "TV", "TV_SHORT": "TV", "MOVIE": "Movie", 
                           "SPECIAL": "Special", "OVA": "OVA", "ONA": "ONA", "MUSIC": "Music"}
                    
                    results.append({
                        "mal_id": rec_media["idMal"],
                        "title": (rec_media.get("title") or {}).get("userPreferred") or "Unknown",
                        "image_url": cover.get("large") or cover.get("medium"),
                        "type": FMT.get(rec_media.get("format"), rec_media.get("format")),
                        "year": rec_media.get("seasonYear"),
                        "episodes": rec_media.get("episodes"),
                        "score": rec_media.get("averageScore"),
                        "in_list": False,
                        "favorite": False,
                    })
                    
                    if len(results) >= 8:
                        break
        except Exception as e:
            print(f"[Recommendations] AniList API error: {e}")
    
    return jsonify({"items": results[:8]})

@bp.route("/api/anime/<int:mal_id>/staff")
@login_required
def staff(mal_id):
    return jsonify({"staff": anime_repo.get_staff(mal_id)})