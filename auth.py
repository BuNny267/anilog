"""Authentication: register, login, sessions, password reset, email verification."""
import time, secrets, hashlib, smtplib, re
from email.mime.text import MIMEText
from functools import wraps
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

import config, database

bp = Blueprint("auth", __name__)
RESET_MAX_AGE = 3600
RESET_RATE_LIMIT = 300
USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]{3,30}$')
RESERVED = {"admin", "root", "mod", "moderator", "system", "anilog", "api", "www", "mail"}

LOGIN_FAILS = {}
LOGIN_WINDOW = 900      # 15 minutes
LOGIN_MAX_FAILS = 5


def _login_limited(key):
    now = time.time()
    arr = [t for t in LOGIN_FAILS.get(key, []) if now - t < LOGIN_WINDOW]
    LOGIN_FAILS[key] = arr
    return len(arr) >= LOGIN_MAX_FAILS


def _login_fail(key):
    LOGIN_FAILS.setdefault(key, []).append(time.time())


def _login_ok(key):
    LOGIN_FAILS.pop(key, None)


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def get_current_user_id():
    return session.get("user_id")


def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return database.query_one("SELECT * FROM users WHERE id=?", (uid,))


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def send_email(to, subject, body):
    if not config.SMTP_HOST or not config.SMTP_USERNAME:
        print(f"[email disabled] To: {to}\n{subject}\n{body}")
        return False
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = config.SMTP_FROM or config.SMTP_USERNAME
        msg["To"] = to
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            server.sendmail(msg["From"], [to], msg.as_string())
        return True
    except Exception as e:
        print(f"Email send failed: {e}")
        return False


def generate_verification_code():
    return ''.join(str(secrets.randbelow(10)) for _ in range(6))


def hash_code(code):
    return hashlib.sha256(code.encode()).hexdigest()


def send_verification_email(user_email, code):
    body = (f"Hello,\n\nYour {config.APP_NAME} email verification code is:\n\n{code}\n\n"
            f"This code expires in 10 minutes.\n\n"
            f"If you did not request this code, you can ignore this email.")
    return send_email(user_email, f"{config.APP_NAME} — Email Verification", body)


def can_change_username(user_id):
    user = database.query_one("SELECT username_changed_at FROM users WHERE id=?", (user_id,))
    if not user or not user.get("username_changed_at"):
        return True, 0
    try:
        last = datetime.strptime(user["username_changed_at"], "%Y-%m-%d %H:%M:%S")
        days = (datetime.now() - last).days
        if days < 30:
            return False, 30 - days
    except ValueError:
        pass
    return True, 0


def validate_username(username):
    if not username or not USERNAME_PATTERN.match(username):
        return False, "Username must be 3-30 characters: letters, numbers, underscores."
    if username.lower() in RESERVED:
        return False, "This username is reserved."
    return True, None


@bp.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("home.home"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        ok, msg = validate_username(username)
        if not ok:
            return render_template("auth/register.html", error=msg)
        if "@" not in email:
            return render_template("auth/register.html", error="Valid email required.")
        if len(password) < 8:
            return render_template("auth/register.html", error="Password must be at least 8 characters.")
        exists = database.query_one(
            "SELECT id FROM users WHERE LOWER(username)=LOWER(?) OR LOWER(email)=LOWER(?)",
            (username, email))
        if exists:
            return render_template("auth/register.html", error="Username or email already in use.")
        database.execute("INSERT INTO users(username, email, password_hash) VALUES(?,?,?)",
                         (username, email, generate_password_hash(password)))
        user = database.query_one("SELECT id FROM users WHERE LOWER(username)=LOWER(?)", (username,))
        if database.query_one("SELECT COUNT(*) AS n FROM users")["n"] == 1:
            database.execute("UPDATE users SET is_admin=1 WHERE id=?", (user["id"],))
        session.permanent = True
        session["user_id"] = user["id"]
        session["username"] = username
        return redirect(url_for("home.home"))
    return render_template("auth/register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home.home"))
    if request.method == "POST":
        ident = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        limit_key = f"{request.remote_addr}:{ident.lower()}"
        if _login_limited(limit_key):
            return render_template("auth/login.html",
                                   error="Too many failed attempts. Try again in 15 minutes.")
        user = database.query_one(
            "SELECT * FROM users WHERE LOWER(username)=LOWER(?) OR LOWER(email)=LOWER(?)",
            (ident, ident.lower()))
        if not user or not check_password_hash(user["password_hash"] or "", password):
            _login_fail(limit_key)
            return render_template("auth/login.html", error="Invalid credentials.")
        _login_ok(limit_key)
        if not user.get("is_active", 1):
            return render_template("auth/login.html", error="Account disabled.")
        session.permanent = True
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        nxt = request.args.get("next")
        return redirect(nxt if nxt and nxt.startswith("/") else url_for("home.home"))
    return render_template("auth/login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = database.query_one("SELECT * FROM users WHERE LOWER(email)=LOWER(?)", (email,))
        if user:
            last = database.query_one(
                "SELECT MAX(created_at) AS t FROM password_reset_tokens WHERE user_id=?", (user["id"],))
            if not (last and last["t"] and (time.time() - last["t"]) < RESET_RATE_LIMIT):
                token = secrets.token_urlsafe(32)
                database.execute(
                    "INSERT INTO password_reset_tokens(user_id, token_hash, expires_at, created_at) VALUES(?,?,?,?)",
                    (user["id"], hash_token(token), time.time() + RESET_MAX_AGE, time.time()))
                link = url_for("auth.reset_password", token=token, _external=True)
                send_email(email, "AniLog Password Reset",
                           f"Reset your password:\n{link}\n\nThis link expires in 1 hour.")
        return render_template("auth/forgot.html", sent=True,
                               message="If that email exists, a reset link was sent.")
    return render_template("auth/forgot.html")


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    row = database.query_one(
        "SELECT * FROM password_reset_tokens WHERE token_hash=? AND used=0", (hash_token(token),))
    if not row or row["expires_at"] < time.time():
        return render_template("auth/reset.html", error="Invalid or expired link.")
    if request.method == "POST":
        pw = request.form.get("password", "")
        if len(pw) < 8:
            return render_template("auth/reset.html", error="Password must be at least 8 characters.")
        database.execute("UPDATE users SET password_hash=? WHERE id=?",
                         (generate_password_hash(pw), row["user_id"]))
        database.execute("UPDATE password_reset_tokens SET used=1 WHERE id=?", (row["id"],))
        return redirect(url_for("auth.login"))
    return render_template("auth/reset.html")