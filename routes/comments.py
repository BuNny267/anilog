"""Comments + likes."""
from flask import Blueprint, jsonify, request
import database
from auth import login_required, get_current_user_id, get_current_user

bp = Blueprint("comments", __name__)


@bp.route("/api/anime/<int:mal_id>/comments")
@login_required
def get_comments(mal_id):
    uid = get_current_user_id()
    comments = database.query("""
        SELECT c.id, c.text, c.created_at, c.user_id, u.username, u.display_name,
               (SELECT COUNT(*) FROM comment_likes cl WHERE cl.comment_id = c.id) AS likes,
               (SELECT COUNT(*) FROM comment_likes cl WHERE cl.comment_id = c.id AND cl.user_id = ?) AS liked
        FROM comments c JOIN users u ON u.id = c.user_id
        WHERE c.anime_id=? ORDER BY c.created_at DESC LIMIT 100
    """, (uid, mal_id))
    for c in comments:
        c["can_delete"] = (c["user_id"] == uid)
        c["liked"] = bool(c["liked"])
        c["display_name"] = c["display_name"] or c["username"]
    return jsonify({"comments": comments})


@bp.post("/api/anime/<int:mal_id>/comments")
@login_required
def add_comment(mal_id):
    uid = get_current_user_id()
    text = ((request.get_json() or {}).get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "Comment cannot be empty."}), 400
    if len(text) > 1000:
        return jsonify({"ok": False, "error": "Comment too long (max 1000 chars)."}), 400
    if not database.query_one("SELECT mal_id FROM anime WHERE mal_id=?", (mal_id,)):
        return jsonify({"ok": False, "error": "Anime not found."}), 404

    now = database.query_one("SELECT datetime('now') AS t")["t"]
    cid = database.execute(
        "INSERT INTO comments(anime_id, user_id, text, created_at) VALUES(?,?,?,?)",
        (mal_id, uid, text, now))
    user = get_current_user()
    return jsonify({"ok": True, "comment": {
        "id": cid, "text": text, "created_at": now, "user_id": uid,
        "username": user["username"],
        "display_name": user.get("display_name") or user["username"],
        "likes": 0, "liked": False, "can_delete": True,
    }})


@bp.post("/api/comments/<int:comment_id>/like")
@login_required
def like_comment(comment_id):
    uid = get_current_user_id()
    if not database.query_one("SELECT id FROM comments WHERE id=?", (comment_id,)):
        return jsonify({"ok": False, "error": "Comment not found."}), 404
    existing = database.query_one(
        "SELECT 1 AS x FROM comment_likes WHERE comment_id=? AND user_id=?", (comment_id, uid))
    if existing:
        database.execute("DELETE FROM comment_likes WHERE comment_id=? AND user_id=?", (comment_id, uid))
        liked = False
    else:
        database.execute("INSERT INTO comment_likes(comment_id, user_id) VALUES(?,?)", (comment_id, uid))
        liked = True
    count = database.query_one(
        "SELECT COUNT(*) AS n FROM comment_likes WHERE comment_id=?", (comment_id,))["n"]
    return jsonify({"ok": True, "liked": liked, "likes": count})


@bp.delete("/api/comments/<int:comment_id>")
@login_required
def delete_comment(comment_id):
    uid = get_current_user_id()
    comment = database.query_one("SELECT * FROM comments WHERE id=?", (comment_id,))
    if not comment:
        return jsonify({"ok": False, "error": "Comment not found."}), 404
    if comment["user_id"] != uid:
        return jsonify({"ok": False, "error": "Not authorized."}), 403
    database.execute("DELETE FROM comments WHERE id=?", (comment_id,))
    return jsonify({"ok": True})