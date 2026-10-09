"""Profile home + settings + account endpoints."""
import json, time
from datetime import datetime
from flask import (Blueprint, Response, jsonify, render_template,
                   request, redirect, url_for, session)
from werkzeug.security import generate_password_hash, check_password_hash
import config, database
from models import anime as M
from auth import (login_required, get_current_user_id, get_current_user,
                  generate_verification_code, hash_code, send_verification_email,
                  can_change_username, validate_username)

bp = Blueprint("profile", __name__)

ALLOWED_SETTINGS = {
    "theme": {"dark", "light", "system"},
    "animations": {"on", "off"},
    "default_view": {"grid", "list"},
    "default_sort": {"updated", "added", "title", "score", "year", "progress"},
    "default_status": {"all", "watching", "completed", "plan_to_watch", "on_hold", "dropped"},
    "auto_complete": {"on", "off"},
    "accent_color": {"purple", "blue", "green", "red", "orange", "pink"},
    "card_layout": {"large", "compact"},
    "profile_visibility": {"public", "private"},
}

CODE_TTL_MIN = 10
CODE_COOLDOWN_SEC = 60
CODE_MAX_ATTEMPTS = 5


@bp.route("/profile")
@login_required
def profile_page():
    user = get_current_user()
    entries, totals = M.profile_bundle(user["id"], 10)
    return render_template("user_profile.html", active="profile",
                           profile_user=user, is_own_profile=True,
                           show_list=True, entries=entries, totals=totals)


@bp.route("/settings")
@login_required
def settings_page():
    uid = get_current_user_id()
    user = get_current_user()
    s = database.all_user_settings(uid)
    entry_count = database.query_one(
        "SELECT COUNT(*) AS n FROM user_anime WHERE user_id=?", (uid,))["n"]
    can_change, days_remaining = can_change_username(uid)
    return render_template("settings.html", active="settings", s=s, user=user,
                           entry_count=entry_count, version=config.APP_VERSION,
                           can_change_username=can_change, days_remaining=days_remaining)


@bp.post("/api/profile/update-display-name")
@login_required
def update_display_name():
    uid = get_current_user_id()
    name = ((request.get_json() or {}).get("display_name") or "").strip()
    if len(name) > 50:
        return jsonify({"ok": False, "error": "Display name too long."}), 400
    database.execute("UPDATE users SET display_name=? WHERE id=?", (name or None, uid))
    return jsonify({"ok": True, "message": "Display name updated", "display_name": name or None})


@bp.post("/api/profile/update-username")
@login_required
def update_username():
    uid = get_current_user_id()
    username = ((request.get_json() or {}).get("username") or "").strip()
    can_change, days = can_change_username(uid)
    if not can_change:
        return jsonify({"ok": False,
                        "error": f"You can change your username again in {days} days."}), 400
    ok, msg = validate_username(username)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 400
    if database.query_one(
            "SELECT id FROM users WHERE LOWER(username)=LOWER(?) AND id!=?", (username, uid)):
        return jsonify({"ok": False, "error": "Username already taken."}), 400
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    database.execute("UPDATE users SET username=?, username_changed_at=? WHERE id=?",
                     (username, now, uid))
    session["username"] = username
    return jsonify({"ok": True, "username": username,
                    "message": "Username updated. You can change it again in 30 days."})


@bp.post("/api/profile/send-verification")
@login_required
def send_verification():
    uid = get_current_user_id()
    user = get_current_user()
    if not user.get("email"):
        return jsonify({"ok": False, "error": "No email on file."}), 400
    if user.get("email_verified"):
        return jsonify({"ok": False, "error": "Email already verified."}), 400
    last = database.query_one(
        "SELECT created_at FROM email_verification_codes WHERE user_id=? "
        "ORDER BY created_at DESC LIMIT 1", (uid,))
    if last and (time.time() - last["created_at"]) < CODE_COOLDOWN_SEC:
        wait = CODE_COOLDOWN_SEC - int(time.time() - last["created_at"])
        return jsonify({"ok": False,
                        "error": f"Please wait {wait} seconds before requesting another code."}), 429
    code = generate_verification_code()
    now = time.time()
    database.execute("""
        INSERT INTO email_verification_codes(user_id, code_hash, created_at, expires_at, used, attempts)
        VALUES(?,?,?,?,0,0)
    """, (uid, hash_code(code), now, now + CODE_TTL_MIN * 60))
    if not send_verification_email(user["email"], code):
        return jsonify({"ok": False, "error": "Failed to send email."}), 500
    return jsonify({"ok": True, "message": "Verification code sent to your email."})


@bp.post("/api/profile/verify-email")
@login_required
def verify_email():
    uid = get_current_user_id()
    code = ((request.get_json() or {}).get("code") or "").strip()
    if not code or len(code) != 6 or not code.isdigit():
        return jsonify({"ok": False, "error": "Code must be 6 digits."}), 400
    rec = database.query_one(
        "SELECT * FROM email_verification_codes WHERE user_id=? AND code_hash=? AND used=0 "
        "ORDER BY created_at DESC LIMIT 1", (uid, hash_code(code)))
    if not rec:
        return jsonify({"ok": False, "error": "Invalid verification code."}), 400
    if time.time() > rec["expires_at"]:
        return jsonify({"ok": False, "error": "Code expired. Request a new one."}), 400
    if rec["attempts"] >= CODE_MAX_ATTEMPTS:
        database.execute("UPDATE email_verification_codes SET used=1 WHERE id=?", (rec["id"],))
        return jsonify({"ok": False, "error": "Too many attempts. Request a new code."}), 400
    database.execute("UPDATE email_verification_codes SET attempts=attempts+1 WHERE id=?",
                     (rec["id"],))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    database.execute("UPDATE users SET email_verified=1, email_verified_at=? WHERE id=?",
                     (now, uid))
    database.execute("UPDATE email_verification_codes SET used=1 WHERE id=?", (rec["id"],))
    return jsonify({"ok": True, "email_verified": True, "message": "Email verified successfully!"})


@bp.post("/api/profile/update-password")
@login_required
def update_password():
    uid = get_current_user_id()
    p = request.get_json() or {}
    current, new_pw, confirm = (p.get("current_password", ""),
                                p.get("new_password", ""), p.get("confirm_password", ""))
    if not current:
        return jsonify({"ok": False, "error": "Current password is required."}), 400
    if len(new_pw) < 8:
        return jsonify({"ok": False, "error": "Password must be at least 8 characters."}), 400
    if new_pw != confirm:
        return jsonify({"ok": False, "error": "New passwords do not match."}), 400
    user = get_current_user()
    if not user or not check_password_hash(user["password_hash"] or "", current):
        return jsonify({"ok": False, "error": "Current password is incorrect."}), 400
    database.execute("UPDATE users SET password_hash=? WHERE id=?",
                     (generate_password_hash(new_pw), uid))
    return jsonify({"ok": True, "message": "Password updated successfully!"})


@bp.post("/api/profile/settings")
@login_required
def save_settings():
    uid = get_current_user_id()
    p = request.get_json(silent=True) or {}
    changed = []
    for key, value in p.items():
        if key in ALLOWED_SETTINGS and str(value) in ALLOWED_SETTINGS[key]:
            database.set_user_setting(uid, key, value)
            changed.append(key)
    return jsonify({"ok": True, "changed": changed})


@bp.route("/profile/export")
@login_required
def export_list():
    uid = get_current_user_id()
    entries = database.query("SELECT * FROM user_anime WHERE user_id=?", (uid,))
    payload = {"app": config.APP_NAME, "version": config.APP_VERSION,
               "exported_at": M.now_str(), "entries": entries,
               "settings": database.all_user_settings(uid)}
    return Response(json.dumps(payload, indent=2), mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=anilog-export.json"})


@bp.post("/profile/import")
@login_required
def import_list():
    uid = get_current_user_id()
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded."}), 400
    f = request.files["file"]
    if not f.filename or not f.filename.endswith(".json"):
        return jsonify({"ok": False, "error": "Only .json files are accepted."}), 400
    try:
        data = json.load(f)
    except Exception:
        return jsonify({"ok": False, "error": "Invalid JSON file."}), 400
    entries = data.get("entries", [])
    if not entries:
        return jsonify({"ok": False, "error": "No entries found in file."}), 400

    now = M.now_str()
    added = updated = failed = 0
    for entry in entries:
        status = entry.get("status", "plan_to_watch")
        if status not in set(M.STATUSES):
            failed += 1
            continue
        if data.get("format") == "import_v1":
            title = (entry.get("title") or "").strip()
            if not title:
                failed += 1
                continue
            existing = database.query_one(
                "SELECT mal_id FROM anime WHERE LOWER(title)=LOWER(?)", (title,))
            if existing:
                mal_id = existing["mal_id"]
            else:
                min_row = database.query_one("SELECT MIN(mal_id) AS m FROM anime")
                mal_id = (min_row["m"] or 0) - 1
                database.execute("INSERT INTO anime(mal_id, title, type) VALUES(?,?,?)",
                                 (mal_id, title[:300], "TV"))
            cur_ep, tot_ep, notes = 0, None, ""
        else:
            mal_id = entry.get("anime_id")
            if mal_id is None or not database.query_one(
                    "SELECT mal_id FROM anime WHERE mal_id=?", (mal_id,)):
                failed += 1
                continue
            cur_ep = entry.get("current_episode", 0) or 0
            tot_ep = entry.get("total_episodes")
            notes = entry.get("notes", "") or ""

        if database.query_one("SELECT anime_id FROM user_anime WHERE user_id=? AND anime_id=?",
                              (uid, mal_id)):
            database.execute("""
                UPDATE user_anime SET status=?, current_episode=?, total_episodes=?,
                    notes=?, last_updated=? WHERE user_id=? AND anime_id=?
            """, (status, cur_ep, tot_ep, notes, now, uid, mal_id))
            updated += 1
        else:
            database.execute("""
                INSERT INTO user_anime(user_id, anime_id, status, current_episode,
                    total_episodes, notes, date_added, last_updated)
                VALUES(?,?,?,?,?,?,?,?)
            """, (uid, mal_id, status, cur_ep, tot_ep, notes, now, now))
            added += 1

    return jsonify({"ok": True,
                    "message": f"Import complete: {added} added, {updated} updated, {failed} skipped.",
                    "added": added, "updated": updated, "failed": failed})


@bp.post("/api/cache/clear")
@login_required
def clear_cache():
    database.cache_clear()
    return jsonify({"ok": True})


@bp.post("/profile/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))