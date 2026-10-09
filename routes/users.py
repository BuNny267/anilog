"""Public user profiles + user search."""
from flask import Blueprint, jsonify, render_template, request
import database
from models import anime as M
from auth import login_required, get_current_user_id

bp = Blueprint("users", __name__)


@bp.route("/user/<username>")
@login_required
def user_profile(username):
    user = database.query_one("SELECT * FROM users WHERE username=?", (username,))
    if not user:
        return render_template("error.html", code=404, active="",
                               title="User not found",
                               message="This user does not exist."), 404

    uid = get_current_user_id()
    is_own = (uid == user["id"])
    visibility = database.get_user_setting(user["id"], "profile_visibility", "public")
    show_list = (visibility == "public") or is_own

    entries, totals = [], {}
    if show_list:
        entries, totals = M.profile_bundle(user["id"], 10)

    return render_template("user_profile.html",
                           active="profile" if is_own else "",
                           profile_user=user, is_own_profile=is_own,
                           show_list=show_list, entries=entries, totals=totals)


@bp.route("/api/search/users")
@login_required
def search_users():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"results": []})
    users = database.query("""
        SELECT id, username, display_name FROM users
        WHERE LOWER(username) LIKE LOWER(?) OR LOWER(display_name) LIKE LOWER(?)
        LIMIT 20
    """, (f"%{q}%", f"%{q}%"))
    return jsonify({"results": users})