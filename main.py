"""AniLog — multi-user anime tracker."""
import datetime, json, os
from flask import Flask, render_template, session
import config, database
from models import anime as M

from routes import (home, lists, search, discover, anime, stats,
                    schedule, profile, users, comments, admin)
from auth import bp as auth_bp, get_current_user


def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY
    app.permanent_session_lifetime = datetime.timedelta(days=config.SESSION_DAYS)
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SECURE"] = False

    app.jinja_env.globals["STATUS_LABELS"] = M.STATUS_LABELS
    app.jinja_env.globals["STATUS_COLORS"] = M.STATUS_COLORS
    database.init_app(app)

    @app.before_request
    def _keep_session_alive():
        # Sliding expiry + enforce disabled accounts instantly
        if "user_id" in session:
            u = database.query_one(
                "SELECT is_active FROM users WHERE id=?", (session["user_id"],))
            if not u or not u.get("is_active", 1):
                session.clear()
                from flask import redirect, url_for
                return redirect(url_for("auth.login"))
            session.permanent = True

    for module in (home, lists, search, discover, anime, stats,
                   schedule, profile, users, comments, admin):
        app.register_blueprint(module.bp)
    app.register_blueprint(auth_bp)

    @app.after_request
    def add_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response

    try:
        from flask_compress import Compress
        Compress(app)
    except ImportError:
        pass

    @app.context_processor
    def inject_globals():
        user = get_current_user()
        try:
            s = database.all_user_settings(user["id"]) if user else dict(config.DEFAULT_SETTINGS)
            my_list = [r["anime_id"] for r in database.query(
                "SELECT anime_id FROM user_anime WHERE user_id=?", (user["id"],))] if user else []
        except Exception:
            s = dict(config.DEFAULT_SETTINGS)
            my_list = []
        for k, v in config.DEFAULT_SETTINGS.items():
            s.setdefault(k, v)
        return {
            "APP_NAME": config.APP_NAME,
            "APP_TAGLINE": config.APP_TAGLINE,
            "APP_VERSION": config.APP_VERSION,
            "settings": s,
            "my_list_json": json.dumps(my_list),
            "current_user": user,
        }

    @app.template_filter("score2")
    def score2(v):
        return f"{v:.2f}" if v else "—"

    @app.template_filter("dur")
    def dur(minutes):
        """AniList duration is minutes per episode."""
        try:
            m = int(minutes)
        except (TypeError, ValueError):
            return "Unknown"
        if not m:
            return "Unknown"
        if m < 60:
            return f"{m} min"
        h, mm = divmod(m, 60)
        return f"{h} hr {mm} min" if mm else f"{h} hr"

    @app.template_filter("dt")
    def dt(s):
        return str(s)[:10] if s else "—"

    @app.template_filter("pct")
    def pct(cur, total):
        try:
            cur, total = float(cur or 0), float(total or 0)
        except (TypeError, ValueError):
            return 0
        if total <= 0:
            return 100 if cur > 0 else 0
        return min(100, round(cur / total * 100))

    @app.template_filter("s10")
    def s10(v):
        """Convert AniList 0-100 score to 0-10 for display."""
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return v / 10.0 if v > 10 else v

    @app.template_filter("ago")
    def ago(s):
        if not s:
            return ""
        try:
            d = datetime.datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return ""
        delta = datetime.datetime.now() - d
        if delta.days > 30:
            return d.strftime("%b %d")
        if delta.days > 0:
            return f"{delta.days}d ago"
        hours = delta.seconds // 3600
        if hours > 0:
            return f"{hours}h ago"
        mins = delta.seconds // 60
        return f"{mins}m ago" if mins else "just now"

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, active="",
                               title="Page not found",
                               message="That page does not exist."), 404

    @app.errorhandler(500)
    def server_error(_e):
        return render_template("error.html", code=500, active="",
                               title="Something broke",
                               message="An internal error occurred. Your data is safe."), 500

    return app


app = create_app()

if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
    from services.scheduler import init_scheduler
    with app.app_context():
        init_scheduler()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)