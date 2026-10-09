"""Admin dashboard."""
from functools import wraps
from flask import Blueprint, jsonify, render_template
import database
from auth import get_current_user, login_required

bp = Blueprint("admin", __name__)


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        u = get_current_user()
        if not u or not u.get("is_admin"):
            return render_template("error.html", code=403, active="",
                                   title="Forbidden", message="Admin access required."), 403
        return f(*a, **k)
    return wrapper


@bp.route("/admin")
@login_required
@admin_required
def dashboard():
    q = lambda s: database.query_one(s)["n"]
    stats = {
        "users": q("SELECT COUNT(*) n FROM users"),
        "admins": q("SELECT COUNT(*) n FROM users WHERE is_admin=1"),
        "disabled": q("SELECT COUNT(*) n FROM users WHERE is_active=0"),
        "entries": q("SELECT COUNT(*) n FROM user_anime"),
        "comments": q("SELECT COUNT(*) n FROM comments"),
        "anime_cached": q("SELECT COUNT(*) n FROM anime"),
        "cache_rows": q("SELECT COUNT(*) n FROM api_cache"),
        "history": q("SELECT COUNT(*) n FROM history"),
    }
    users = database.query("""
        SELECT u.id, u.username, u.display_name, u.email, u.is_active, u.is_admin,
               u.created_at,
               (SELECT COUNT(*) FROM user_anime ua WHERE ua.user_id=u.id) AS entries
        FROM users u ORDER BY u.id
    """)
    return render_template("admin.html", active="admin", stats=stats, users=users)


@bp.post("/api/admin/user/<int:uid>/toggle-active")
@login_required
@admin_required
def toggle_active(uid):
    me = get_current_user()
    if uid == me["id"]:
        return jsonify({"ok": False, "error": "You cannot disable yourself."}), 400
    u = database.query_one("SELECT is_active FROM users WHERE id=?", (uid,))
    if not u:
        return jsonify({"ok": False, "error": "User not found."}), 404
    new = 0 if u["is_active"] else 1
    database.execute("UPDATE users SET is_active=? WHERE id=?", (new, uid))
    return jsonify({"ok": True, "is_active": new})


@bp.post("/api/admin/user/<int:uid>/toggle-admin")
@login_required
@admin_required
def toggle_admin(uid):
    me = get_current_user()
    if uid == me["id"]:
        return jsonify({"ok": False, "error": "You cannot change your own role."}), 400
    u = database.query_one("SELECT is_admin FROM users WHERE id=?", (uid,))
    if not u:
        return jsonify({"ok": False, "error": "User not found."}), 404
    new = 0 if u["is_admin"] else 1
    database.execute("UPDATE users SET is_admin=? WHERE id=?", (new, uid))
    return jsonify({"ok": True, "is_admin": new})