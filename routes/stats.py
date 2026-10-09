"""Statistics page."""
import datetime
from collections import Counter
from flask import Blueprint, render_template
import database
from models import anime as M
from auth import login_required, get_current_user_id

bp = Blueprint("stats", __name__)


@bp.route("/stats")
@login_required
def stats():
    uid = get_current_user_id()
    entries = M.hydrate(database.query("""
        SELECT ua.status, ua.current_episode, ua.total_episodes, ua.date_added,
               a.year, a.score, a.duration, a.genres
        FROM user_anime ua LEFT JOIN anime a ON a.mal_id = ua.anime_id
        WHERE ua.user_id = ?
    """, (uid,)))
    totals = M.compute_totals(entries)
    totals["favorites"] = database.query_one(
        "SELECT COUNT(*) AS n FROM user_anime WHERE user_id=? AND favorite=1", (uid,))["n"]

    status_counts = Counter(e["status"] for e in entries)
    donut, acc, C = [], 0.0, 6.2831853 * 48.0
    for st in M.STATUSES:
        n = status_counts.get(st, 0)
        if not n or not entries:
            continue
        frac = n / len(entries)
        donut.append({"status": st, "label": M.STATUS_LABELS[st], "count": n,
                      "color": M.STATUS_COLORS[st],
                      "dash": round(frac * C, 2), "gap": round(C, 2),
                      "offset": round(-acc, 2)})
        acc += frac * C
    donut_map = {d["status"]: d["count"] for d in donut}

    genre_counts = Counter()
    for e in entries:
        for g in e.get("genres") or []:
            genre_counts[g] += 1
    genres = genre_counts.most_common(12)
    max_genre = max((c for _, c in genres), default=1)

    year_counts = Counter(e["year"] for e in entries if e.get("year"))
    years = sorted(year_counts.items())[-14:]
    max_year = max((c for _, c in years), default=1)

    today = datetime.date.today()
    months = []
    for i in range(11, -1, -1):
        y, m = today.year, today.month - i
        while m <= 0:
            m += 12
            y -= 1
        months.append((f"{y}-{m:02d}", datetime.date(y, m, 1).strftime("%b")))
    sums = {r["m"]: r["s"] for r in database.query("""
        SELECT strftime('%Y-%m', created_at) AS m,
               SUM(MAX(episode_to - episode_from, 0)) AS s
        FROM history WHERE user_id=? AND created_at >= date('now', '-366 days')
        GROUP BY m""", (uid,))}
    monthly = [{"label": lbl, "eps": int(sums.get(key) or 0)} for key, lbl in months]
    max_month = max((m["eps"] for m in monthly), default=1)

    return render_template(
        "stats.html", active="stats", totals=totals, donut=donut, donut_map=donut_map,
        genres=genres, max_genre=max_genre, years=years, max_year=max_year,
        monthly=monthly, max_month=max_month,
        status_labels=M.STATUS_LABELS, status_colors=M.STATUS_COLORS,
        has_data=bool(entries),
    )