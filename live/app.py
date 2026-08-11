#!/usr/bin/env python3
"""Phase 7d — MAJOR-PAIN live demo (Flask).

Routes:
  GET  /        demo login form (one card per persona + custom event form)
  POST /login   score one login event, show the verdict
  POST /burst   attacker persona: 5 rapid failed attempts in quick succession
  GET  /admin   recent events + alerts, the security dashboard

Run:  venv/bin/python live/app.py   (then open http://127.0.0.1:5000)
"""
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live"))

from db import get_con, init_schema  # noqa: E402
from scoring import score_event  # noqa: E402

app = Flask(__name__)
_con_lock = threading.Lock()


def con():
    con = get_con()
    init_schema(con)
    return con


def _login_success() -> bool:
    return request.form.get("login_success", "1") == "1"


def _event_from_form(user: dict, login_success: bool) -> dict:
    return {
        "user_id": user["user_id"],
        "ts": datetime.now(timezone.utc),
        "ip": request.form.get("ip") or user.get("ip"),
        "country": request.form.get("country") or user.get("country"),
        "device_type": request.form.get("device_type") or user.get("device_type"),
        "os_family": request.form.get("os_family") or user.get("os_family"),
        "browser_family": request.form.get("browser_family") or user.get("browser_family"),
        "asn": request.form.get("asn") or user.get("asn"),
        "login_success": login_success,
        "is_attack_ip": bool(user.get("persona") == "attacker"),
        "is_ato": bool(user.get("persona") == "attacker" and not login_success),
        "is_private_ip": False,
        "geo_unreliable": False,
        "rtt_missing": True,
        "ua_os_conflict": False,
        "is_generator_bot": False,
        "is_vlc": False,
    }


def _users(c) -> list:
    rows = c.execute("SELECT * FROM users ORDER BY persona, name").fetchall()
    return [dict(zip([d[0] for d in c.description], r)) for r in rows]


@app.route("/")
def index():
    c = con()
    return render_template("login.html", users=_users(c))


@app.route("/login", methods=["POST"])
def login():
    c = con()
    user = c.execute("SELECT * FROM users WHERE user_id = ?",
                     [request.form["user_id"]]).fetchone()
    if user is None:
        return redirect(url_for("index"))
    user = dict(zip([d[0] for d in c.description], user))
    ev = _event_from_form(user, _login_success())
    with _con_lock:
        result = score_event(c, ev)
    return render_template("result.html", user=user, result=result)


@app.route("/burst", methods=["POST"])
def burst():
    """Attacker persona: 5 rapid login attempts ~1s apart (demonstrates
    failed_recently + rapid_login_rate escalation)."""
    c = con()
    user = c.execute("SELECT * FROM users WHERE persona = 'attacker'").fetchone()
    user = dict(zip([d[0] for d in c.description], user))
    results = []
    for i in range(5):
        ev = _event_from_form(user, login_success=(i == 4))
        with _con_lock:
            results.append(score_event(c, ev))
        time.sleep(1)
    return render_template("burst.html", user=user, results=results)


@app.route("/admin")
def admin():
    c = con()
    events = c.execute("""
        SELECT e.*, u.name, u.persona
        FROM events e LEFT JOIN users u ON u.user_id = e.user_id
        WHERE e.decision != 'history'
        ORDER BY e.row_id DESC LIMIT 50
    """).fetchall()
    cols = [d[0] for d in c.description]
    events = [dict(zip(cols, r)) for r in events]
    alerts = c.execute("SELECT * FROM alerts ORDER BY alert_id DESC LIMIT 20").fetchall()
    alerts = [dict(zip([d[0] for d in c.description], r)) for r in alerts]
    return render_template("admin.html", events=events, alerts=alerts)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
