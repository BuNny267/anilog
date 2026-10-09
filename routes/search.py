"""Search page + API."""
from flask import Blueprint, jsonify, render_template, request
from api import anilist
from models import anime as M
from auth import login_required, get_current_user_id

bp = Blueprint("search", __name__)


@bp.route("/search")
@login_required
def search():
    return render_template("search.html", active="search")


@bp.route("/api/search")
@login_required
def api_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"results": []})
    try:
        items = anilist.search(q, limit=30)
        in_list = M.my_list_ids(get_current_user_id())
        for it in items:
            it["in_list"] = it["mal_id"] in in_list
        return jsonify({"results": items})
    except Exception as e:
        return jsonify({"error": str(e), "results": []})