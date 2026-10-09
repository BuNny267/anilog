"""Airing schedule page."""
from flask import Blueprint, jsonify, render_template
from api import anilist, ApiError
from models import anime as M
from auth import login_required, get_current_user_id

bp = Blueprint("schedule", __name__)


@bp.route("/schedule")
@login_required
def schedule_page():
    return render_template("schedule.html", active="schedule")


@bp.route("/api/schedule")
@login_required
def api_schedule():
    try:
        items = anilist.fetch_schedule(days=7)
        in_list = M.my_list_ids(get_current_user_id())
        for it in items:
            it["in_list"] = it["mal_id"] in in_list
        return jsonify({"items": items})
    except ApiError as exc:
        return jsonify({"items": [], "error": str(exc)})