#!/usr/bin/env python3
"""Phase 7d — MAJOR-PAIN live demo (Flask).

Routes:
  GET  /                     demo login form (one card per persona + custom event form)
  POST /login                score one login event; show verdict / challenge / blocked
  POST /burst                attacker persona: 5 rapid failed attempts in quick succession
  GET  /blocked/<event_id>   blocked page (decision = block)
  GET  /challenge/<event_id> challenge flow page (+ POST verifies, demo-only)
  GET  /admin                recent events + alerts, the security dashboard (live via SSE)
  GET  /events/stream        SSE: pushes every new scored event to the dashboard

JSON API:
  POST /events               score one login event -> JSON verdict
  GET  /risk/<event_id>      risk details for one event
  GET  /users/<id>/profile   user profile (usual country/device/hours, daily counts)
  GET  /alerts               recent alerts

Run:  venv/bin/python live/app.py   (then open http://127.0.0.1:5000)
"""
import json
import math
import queue
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import (Flask, Response, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)
from werkzeug.routing import IntegerConverter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live"))

from db import get_con, init_schema  # noqa: E402
from scoring import score_event, feature_sql, score_sql, load_model  # noqa: E402

from geolocation import get_country_coords  # noqa: E402

app = Flask(__name__)
_con_lock = threading.Lock()
_live_feed: "queue.Queue[dict]" = queue.Queue(maxsize=500)


class SignedIntConverter(IntegerConverter):
    """Like <int:...> but accepts negative ids (seeded user_ids are negative)."""

    regex = r"-?\d+"


app.url_map.converters["sint"] = SignedIntConverter

SAMPLE = ROOT / "data" / "processed" / "sample.parquet"
RULES = ROOT / "reports" / "rule_baseline_scores.parquet"
ML_SCORES = ROOT / "data" / "processed" / "sample_ml_scores.parquet"
SAMPLE_JOIN = f"""
    read_parquet('{SAMPLE}') s
    JOIN read_parquet('{RULES}') r USING (row_id)
    LEFT JOIN read_parquet('{ML_SCORES}') m USING (row_id)
"""

REASON_LABELS = {
    "country": "New Country", "device": "New Device", "hour": "Off-Hours Access",
    "failed": "Recent Failures", "rapid": "Rapid Login Burst", "freq": "Login Frequency",
    "new ip": "Unknown IP", "new asn": "Unknown ASN", "new os": "Unknown OS",
    "new browser": "Unknown Browser",
}

SEV_COLORS = {"low": "#22c55e", "medium": "#f59e0b", "high": "#ef4444", "critical": "#dc2626"}


def con():
    con = get_con()
    init_schema(con)
    return con


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("1", "true", "yes", "on")


def _login_success(payload: dict) -> bool:
    return _truthy(payload.get("login_success", True))


def _event_from_form(user: dict, payload: dict, login_success: bool) -> dict:
    return {
        "user_id": user["user_id"],
        "ts": datetime.now(timezone.utc),
        "ip": payload.get("ip") or user.get("ip"),
        "country": payload.get("country") or user.get("country"),
        "device_type": payload.get("device_type") or user.get("device_type"),
        "os_family": payload.get("os_family") or user.get("os_family"),
        "browser_family": payload.get("browser_family") or user.get("browser_family"),
        "asn": payload.get("asn") or user.get("asn"),
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


def _jdict(d: dict) -> dict:
    """JSON-safe dict: datetimes become ISO strings, numpy scalars to python."""
    out = {}
    for k, v in d.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif hasattr(v, "item"):
            out[k] = v.item()
        else:
            out[k] = v
    return out


@app.template_filter("fmt")
def _fmt_ts(ts) -> str:
    """Human timestamp: '12 Aug 2026, 14:32:07' (local time)."""
    if ts is None:
        return "-"
    return ts.astimezone().strftime("%d %b %Y, %H:%M:%S")


def _users(c) -> list:
    rows = c.execute("SELECT * FROM users ORDER BY persona, name").fetchall()
    return [dict(zip([d[0] for d in c.description], r)) for r in rows]


def _publish(c, result: dict) -> None:
    """Push a scored event onto the SSE feed for the admin dashboard."""
    row = c.execute("SELECT name, persona FROM users WHERE user_id = ?",
                    [result["user_id"]]).fetchone()
    name, persona = (row if row else (None, None))
    try:
        _live_feed.put_nowait({
            "event_id": result["row_id"],
            "user_id": result["user_id"],
            "name": name,
            "persona": persona,
            "ts": result["ts"].isoformat() if hasattr(result["ts"], "isoformat") else str(result["ts"]),
            "ip": result["ip"],
            "country": result["country"],
            "device_type": result["device_type"],
            "os_family": result["os_family"],
            "browser_family": result["browser_family"],
            "login_success": bool(result["login_success"]),
            "rule_score": result["rule_score"],
            "ml_score": result["ml_score"],
            "risk_level": result["risk_level"],
            "reasons": result["reasons"],
            "decision": result["decision"],
        })
    except queue.Full:
        pass


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
    ev = _event_from_form(user, request.form, _login_success(request.form))
    with _con_lock:
        result = score_event(c, ev)
    _publish(c, result)
    if result["decision"] == "block":
        return redirect(url_for("blocked", event_id=result["row_id"]))
    if result["decision"] == "flag":
        return redirect(url_for("challenge", event_id=result["row_id"]))
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
        ev = _event_from_form(user, {}, login_success=(i == 4))
        with _con_lock:
            result = score_event(c, ev)
            _publish(c, result)
            results.append(result)
        time.sleep(1)
    return render_template("burst.html", user=user, results=results)


@app.route("/blocked/<int:event_id>")
def blocked(event_id: int):
    c = con()
    row = c.execute("""
        SELECT e.*, u.name FROM events e JOIN users u ON u.user_id = e.user_id
        WHERE e.row_id = ?
    """, [event_id]).fetchone()
    if row is None:
        return redirect(url_for("index"))
    return render_template("blocked.html", event=dict(zip([d[0] for d in c.description], row)))


@app.route("/challenge/<int:event_id>", methods=["GET", "POST"])
def challenge(event_id: int):
    """Challenge flow: FLAG decision -> extra verification step. Demo-only:
    any OTP is accepted (no real verification, no DB change)."""
    c = con()
    row = c.execute("""
        SELECT e.*, u.name FROM events e JOIN users u ON u.user_id = e.user_id
        WHERE e.row_id = ?
    """, [event_id]).fetchone()
    if row is None:
        return redirect(url_for("index"))
    event = dict(zip([d[0] for d in c.description], row))
    verified = request.method == "POST"
    return render_template("challenge.html", event=event, verified=verified)


@app.route("/admin")
def admin():
    return redirect(url_for("spa"))


@app.route("/events/stream")
def stream():
    """Server-Sent Events: one `score` message per scored event. The admin
    dashboard subscribes and prepends rows without a page refresh."""
    def gen():
        while True:
            try:
                item = _live_feed.get(timeout=15)
                yield f"event: score\ndata: {json.dumps(item)}\n\n"
            except queue.Empty:
                yield ": keep-alive\n\n"

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------- JSON API ----------------

@app.route("/events", methods=["POST"])
def api_events():
    c = con()
    payload = request.get_json(silent=True) or request.form
    try:
        uid = int(payload["user_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "user_id (int) required"}), 400
    user = c.execute("SELECT * FROM users WHERE user_id = ?", [uid]).fetchone()
    if user is None:
        return jsonify({"error": "unknown user_id"}), 404
    user = dict(zip([d[0] for d in c.description], user))
    ev = _event_from_form(user, payload, _login_success(payload))
    with _con_lock:
        result = score_event(c, ev)
    _publish(c, result)
    return jsonify(_jdict(result))


@app.route("/risk/<int:event_id>")
def api_risk(event_id: int):
    c = con()
    row = c.execute("""
        SELECT e.*, u.name, u.persona
        FROM events e JOIN users u ON u.user_id = e.user_id
        WHERE e.row_id = ? AND e.decision != 'history'
    """, [event_id]).fetchone()
    if row is None:
        return jsonify({"error": "event not found"}), 404
    return jsonify(_jdict(dict(zip([d[0] for d in c.description], row))))


@app.route("/users/<sint:user_id>/profile")
def api_profile(user_id: int):
    c = con()
    row = c.execute("""
        SELECT u.name, u.persona, p.usual_country, p.usual_device_type,
               p.usual_os_family, p.usual_browser_family, p.usual_ip,
               p.usual_asn, p.top_hours, p.avg_logins_per_day, p.failed_24h,
               p.updated_at
        FROM users u LEFT JOIN user_profile p ON p.user_id = u.user_id
        WHERE u.user_id = ?
    """, [user_id]).fetchone()
    if row is None:
        return jsonify({"error": "unknown user_id"}), 404
    d = dict(zip([d[0] for d in c.description], row))
    return jsonify(_jdict(d))


@app.route("/alerts")
def api_alerts():
    c = con()
    rows = c.execute("SELECT * FROM alerts ORDER BY alert_id DESC LIMIT 50").fetchall()
    alerts = [dict(zip([d[0] for d in c.description], r)) for r in rows]
    return jsonify([_jdict(a) for a in alerts])


# ---------------- React dashboard (Phase 8.5) ----------------

WEB = ROOT / "live" / "web" / "dist"


def _haversine_km(a_lnglat, b_lnglat) -> float:
    lng1, lat1 = a_lnglat
    lng2, lat2 = b_lnglat
    if lat1 == 0 and lng1 == 0:
        return 0.0
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(h)))


def _sev_by_share(share: float) -> str:
    if share >= 0.5:
        return "critical"
    if share >= 0.3:
        return "high"
    if share >= 0.15:
        return "medium"
    return "low"


def _alert_json(a: dict) -> dict:
    return {
        "id": a["alert_id"], "eventId": a["event_id"], "severity": a["level"],
        "user": a["user_id"], "displayName": a.get("name") or a["user_id"],
        "type": a["decision"], "description": a.get("reasons") or "-",
        "timestamp": a["ts"], "riskScore": a.get("rule_score") or 0,
        "status": "acknowledged" if a.get("acked_at") else "new",
        "mitre": None,
    }


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})


@app.route("/api/dashboard")
def api_dashboard():
    c = con()
    agg = c.execute(f"""
        SELECT COUNT(*) total,
               COUNT(*) FILTER (WHERE r.risk_level IN ('high', 'critical')) flagged,
               COUNT(DISTINCT s.user_id) users,
               COUNT(DISTINCT s.user_id)
                 FILTER (WHERE r.risk_level IN ('high', 'critical')) risky_users
        FROM {SAMPLE_JOIN}
    """).fetchone()
    total, flagged, users, risky_users = agg

    trend = c.execute(f"""
        SELECT dayofweek(s.ts) d,
               COUNT(*) FILTER (WHERE r.risk_level IN ('high', 'critical')) flagged,
               COUNT(*) FILTER (WHERE s.login_success
                                AND r.risk_level IN ('high', 'critical')) fp
        FROM {SAMPLE_JOIN} GROUP BY 1 ORDER BY 1
    """).fetchall()
    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    anomaly_trend = [{"date": days[d], "anomalies": f, "falsePositives": fp}
                     for d, f, fp in trend]

    risk_dist = c.execute(f"""
        SELECT COALESCE(r.risk_level, 'low') lvl, COUNT(*) n
        FROM {SAMPLE_JOIN} GROUP BY 1
    """).fetchall()
    risk_dist = [{"name": lvl.title(), "value": n, "color": SEV_COLORS[lvl]}
                 for lvl, n in risk_dist if lvl in SEV_COLORS]

    activity = c.execute(f"""
        SELECT s.hour h,
               COUNT(*) FILTER (WHERE r.risk_level IN ('high', 'critical')) anom,
               COUNT(*) FILTER (WHERE r.risk_level IN ('low', 'medium')) norm
        FROM {SAMPLE_JOIN} GROUP BY 1 ORDER BY 1
    """).fetchall()
    user_activity = [{"hour": f"{h:02d}", "normal": norm, "anomalous": anom}
                     for h, anom, norm in activity]

    reasons = c.execute(f"""
        SELECT reason, COUNT(*) n
        FROM {SAMPLE_JOIN}, unnest(string_split(r.reasons, ', ')) AS t(reason)
        WHERE r.reasons IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 7
    """).fetchall()
    top = max((n for _, n in reasons), default=1)
    top_reasons = [{"reason": REASON_LABELS.get(rz, rz.title()),
                    "count": n, "percentage": max(1, round(100 * n / top))}
                   for rz, n in reasons]

    logins = c.execute("""
        SELECT e.row_id, e.user_id, u.name, e.ip, e.country, e.device_type,
               e.os_family, e.decision, e.rule_score, e.ts
        FROM events e LEFT JOIN users u ON u.user_id = e.user_id
        WHERE e.decision != 'history'
        ORDER BY e.row_id DESC LIMIT 20
    """).fetchall()
    recent_logins = [{
        "id": e[0], "user": e[1], "displayName": e[2] or e[1], "ip": e[3] or "-",
        "country": e[4] or "-", "device": e[5] or "-", "os": e[6] or "-",
        "status": e[7], "riskScore": e[8] or 0,
        "time": e[9].strftime("%H:%M:%S"),
    } for e in logins]

    al = c.execute("""
        SELECT a.*, u.name FROM alerts a
        LEFT JOIN users u ON u.user_id = a.user_id
        ORDER BY a.alert_id DESC LIMIT 15
    """).fetchall()
    alerts = [_alert_json(dict(zip([d[0] for d in c.description], r))) for r in al]

    scatter = c.execute(f"""
        SELECT s.user_id, r.rule_score, s.is_attack_ip, s.login_frequency_today
        FROM {SAMPLE_JOIN} USING SAMPLE 60
    """).fetchall()
    scatter_data = [{"user": u, "riskScore": r, "isAnomaly": bool(a),
                     "loginFrequency": lf} for u, r, a, lf in scatter]

    return jsonify({
        "kpis": {
            "totalEvents": total, "anomalies": flagged,
            "highRiskUsers": risky_users, "usersMonitored": users,
            "totalEventsChange": 0, "anomaliesChange": 0, "highRiskChange": 0,
        },
        "anomalyTrend": anomaly_trend, "riskDistribution": risk_dist,
        "userActivity": user_activity, "topReasons": top_reasons,
        "recentLogins": recent_logins, "alerts": alerts,
        "scatterData": scatter_data,
    })


@app.route("/api/map")
def api_map():
    c = con()
    locs = c.execute(f"""
        SELECT s.country, COUNT(*) n, SUM(s.is_attack_ip) attacks,
               ROUND(AVG(r.rule_score)) risk
        FROM {SAMPLE_JOIN}
        WHERE s.country IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 40
    """).fetchall()
    locations = []
    for country, n, attacks, risk in locs:
        coords = get_country_coords(country)
        if coords == [0, 0]:
            continue
        share = (attacks or 0) / n
        locations.append({
            "name": country, "country": country, "coords": coords,
            "risk": int(risk or 0), "user": "",
            "severity": _sev_by_share(share),
            "totalEvents": n, "anomalies": int(attacks or 0),
        })

    paths = c.execute("""
        SELECT e.*, u.name, u.persona, u.country usual_country
        FROM events e LEFT JOIN users u ON u.user_id = e.user_id
        WHERE e.decision IN ('flag', 'block')
        ORDER BY e.row_id DESC LIMIT 25
    """).fetchall()
    path_cols = [x[0] for x in c.description]
    travel_paths = []
    for e in paths:
        d = dict(zip(path_cols, e))
        from_coords = get_country_coords(d.get("usual_country") or "US")
        to_coords = get_country_coords(d.get("country") or "US")
        if from_coords == [0, 0] or to_coords == [0, 0]:
            continue
        prev = c.execute("""
            SELECT ts FROM events
            WHERE user_id = ? AND row_id < ? AND decision != 'history'
            ORDER BY row_id DESC LIMIT 1
        """, [d["user_id"], d["row_id"]]).fetchone()
        gap = "-"
        if prev:
            mins = int((d["ts"] - prev[0]).total_seconds() // 60)
            gap = f"{mins} min"
        travel_paths.append({
            "from": {"name": d.get("usual_country") or "US",
                     "country": d.get("usual_country") or "US",
                     "coords": from_coords},
            "to": {"name": d.get("country") or "US",
                   "country": d.get("country") or "US",
                   "coords": to_coords},
            "risk": d.get("rule_score") or 0,
            "user": d.get("name") or d["user_id"],
            "type": d["decision"],
            "distance": f"{_haversine_km(from_coords, to_coords):,} km",
            "timeGap": gap,
        })
    return jsonify({"locations": locations, "travelPaths": travel_paths})


@app.route("/api/alerts")
def api_alerts_spa():
    c = con()
    rows = c.execute("""
        SELECT a.*, u.name FROM alerts a
        LEFT JOIN users u ON u.user_id = a.user_id
        ORDER BY a.alert_id DESC LIMIT 50
    """).fetchall()
    alerts = [_alert_json(dict(zip([d[0] for d in c.description], r))) for r in rows]
    return jsonify(alerts)


@app.route("/api/alerts/<int:alert_id>/ack", methods=["POST"])
def api_alert_ack(alert_id: int):
    c = con()
    c.execute("UPDATE alerts SET acked_at = now() WHERE alert_id = ?", [alert_id])
    return jsonify({"ok": True, "alert_id": alert_id})


@app.route("/api/investigation/<int:event_id>")
def api_investigation(event_id: int):
    c = con()
    row = c.execute("""
        SELECT e.*, u.name, u.country usual_country, p.usual_country,
               p.usual_device_type, p.usual_os_family, p.usual_browser_family,
               p.usual_ip, p.usual_asn, p.top_hours, p.avg_logins_per_day
        FROM events e
        LEFT JOIN users u ON u.user_id = e.user_id
        LEFT JOIN user_profile p ON p.user_id = e.user_id
        WHERE e.row_id = ?
    """, [event_id]).fetchone()
    if row is None:
        return jsonify({"error": "event not found"}), 404
    e = dict(zip([d[0] for d in c.description], row))

    user_src = f"(SELECT row_id, ts, user_id, ip, country, asn, device_type, os_family, browser_family, login_success, is_attack_ip, is_ato, is_private_ip, geo_unreliable, rtt_missing, ua_os_conflict, is_generator_bot, is_vlc FROM events WHERE user_id = {e['user_id']})"
    parts = c.execute(f"""
        SELECT * FROM ({score_sql(f"({feature_sql(user_src)})")})
        WHERE row_id = {event_id}
    """).fetchdf().iloc[0]

    score_labels = {
        "score_country": "New Country", "score_device": "New Device",
        "score_hour": "Off-Hours", "score_failed": "Recent Failures",
        "score_rapid": "Rapid Burst", "score_freq": "Login Frequency",
        "score_new_ip": "Unknown IP", "score_new_asn": "Unknown ASN",
        "score_new_os": "Unknown OS", "score_new_browser": "Unknown Browser",
    }
    contributions = []
    for col, label in score_labels.items():
        v = int(parts[col])
        if v > 0:
            color = "#ef4444" if v >= 30 else "#f59e0b" if v >= 20 else "#3b82f6"
            contributions.append({"feature": label, "value": v, "color": color})

    timeline_rows = c.execute("""
        SELECT ts, country, login_success, decision FROM events
        WHERE user_id = ? AND decision != 'history'
        ORDER BY row_id DESC LIMIT 8
    """, [e["user_id"]]).fetchall()
    timeline = [{
        "event": "Login OK" if ok else "Failed Login",
        "icon": "check" if ok else "x",
        "severity": "critical" if d == "block" else ("high" if d == "flag" else None),
        "time": ts.strftime("%H:%M:%S %d %b"), "country": country or "-",
    } for ts, country, ok, d in reversed(timeline_rows)]

    from_coords = get_country_coords(e.get("usual_country") or "US")
    to_coords = get_country_coords(e.get("country") or "US")
    top_hours = (e.get("top_hours") or "0").split(",")[0]
    threshold = float(load_model()["threshold"])

    return jsonify({
        "displayName": e.get("name") or e["user_id"], "user": e["user_id"],
        "severity": e.get("risk_level") or "low",
        "riskScore": e.get("rule_score") or 0,
        "type": e.get("decision") or "allow",
        "description": e.get("reasons") or "-",
        "ip": e.get("ip") or "-", "asn": e.get("asn") or "-",
        "country": e.get("country") or "-",
        "previousCountry": e.get("usual_country") or "-",
        "device": e.get("device_type") or "-", "browser": e.get("browser_family") or "-",
        "os": e.get("os_family") or "-",
        "distanceKm": _haversine_km(from_coords, to_coords),
        "previousCity": "-", "city": e.get("country") or "-",
        "timeSincePreviousLogin": "-",
        "timeline": timeline, "featureContributions": contributions,
        "mitreId": None, "mitreName": "—", "mitreDescription": "",
        "aiExplanation": (
            f"Rule points {e.get('rule_score') or 0}; supervised HGB probability "
            f"{e.get('ml_score') or 0:.3f} vs threshold {threshold:.3f}.\n"
            f"Reasons: {e.get('reasons') or 'none'}"),
        "confidence": min(99, int((e.get("ml_score") or 0) * 100)),
        "baseline": {
            "avgLoginHour": f"{int(top_hours):02d}:00" if top_hours else "-",
            "avgLogoutHour": "-",
            "avgLoginsPerDay": round(e.get("avg_logins_per_day") or 0, 1),
            "mfaEnabled": False,
            "countries": [e.get("usual_country")] if e.get("usual_country") else [],
            "devices": [e.get("usual_device_type")] if e.get("usual_device_type") else [],
        },
    })


@app.route("/api/users")
def api_users():
    c = con()
    rows = c.execute("""
        SELECT u.user_id, u.name, u.persona, u.country, u.ip,
               COUNT(e.row_id) FILTER (WHERE e.decision != 'history') live_events,
               COUNT(e.row_id) FILTER (WHERE e.decision IN ('flag', 'block')) flags,
               MAX(CASE WHEN e.decision != 'history' THEN e.rule_score END) max_rule
        FROM users u LEFT JOIN events e ON e.user_id = u.user_id
        GROUP BY u.user_id, u.name, u.persona, u.country, u.ip
        ORDER BY u.persona, u.user_id
    """).fetchall()
    cols = [d[0] for d in c.description]
    users = [dict(zip(cols, r)) for r in rows]
    top_risky = c.execute(f"""
        SELECT s.user_id, COUNT(*) n, MAX(r.rule_score) risk
        FROM {SAMPLE_JOIN} WHERE r.risk_level IN ('high', 'critical')
        GROUP BY 1 ORDER BY 3 DESC LIMIT 8
    """).fetchall()
    return jsonify({
        "personas": users, "topRisky": [dict(zip(("user_id", "events", "risk"), r))
                                        for r in top_risky],
        "counts": c.execute(f"""
            SELECT COUNT(DISTINCT s.user_id) users, COUNT(*) events
            FROM {SAMPLE_JOIN}
        """).fetchone(),
    })


@app.route("/api/dataset/summary")
def api_dataset_summary():
    c = con()
    row = c.execute(f"""
        SELECT COUNT(*) total,
               COUNT(*) FILTER (WHERE s.is_attack_ip) attacks,
               COUNT(*) FILTER (WHERE s.is_ato) ato,
               COUNT(*) FILTER (WHERE s.login_success) success,
               COUNT(*) FILTER (WHERE r.risk_level IN ('high', 'critical')) flagged,
               ROUND(AVG(r.rule_score)) avg_rule,
               ROUND(AVG(m.ml_score) FILTER (WHERE m.ml_score IS NOT NULL), 3) avg_ml
        FROM {SAMPLE_JOIN}
    """).fetchone()
    total, attacks, ato, success, flagged, avg_rule, avg_ml = row
    dist = c.execute(f"""
        SELECT COALESCE(r.risk_level, 'low'), COUNT(*) FROM {SAMPLE_JOIN} GROUP BY 1
    """).fetchall()
    return jsonify({
        "total": total, "attacks": attacks,
        "attackShare": round(100 * attacks / total, 2),
        "ato": ato, "success": success, "flagged": flagged,
        "avgRule": avg_rule, "avgMl": avg_ml, "mlReady": ML_SCORES.exists(),
        "riskDist": {lvl: n for lvl, n in dist},
    })


@app.route("/api/dataset/rows")
def api_dataset_rows():
    page = max(1, int(request.args.get("page", 1)))
    per = min(100, max(10, int(request.args.get("per_page", 25))))
    risk = request.args.get("risk", "")
    attack = request.args.get("attack", "")
    ato = request.args.get("ato", "")
    country = (request.args.get("country") or "").strip().upper()
    q = (request.args.get("q") or "").strip()

    where, args = [], []
    if risk:
        where.append("r.risk_level = ?")
        args.append(risk)
    if attack in ("0", "1"):
        where.append("s.is_attack_ip = ?")
        args.append(attack == "1")
    if ato in ("0", "1"):
        where.append("s.is_ato = ?")
        args.append(ato == "1")
    if country:
        where.append("s.country = ?")
        args.append(country)
    if q:
        where.append("(CAST(s.user_id AS VARCHAR) LIKE ? OR s.country LIKE ? OR s.ip LIKE ?)")
        args += [f"%{q}%", f"%{q.upper()}%", f"%{q}%"]
    sql = f"FROM {SAMPLE_JOIN} " + ("WHERE " + " AND ".join(where) if where else "")

    c = con()
    total = c.execute(f"SELECT COUNT(*) {sql}", args).fetchone()[0]
    rows = c.execute(f"""
        SELECT s.row_id, s.ts, s.user_id, s.country, s.device_type, s.os_family,
               s.login_success, s.is_attack_ip, s.is_ato, r.rule_score,
               m.ml_score, r.risk_level, r.reasons
        {sql} ORDER BY r.rule_score DESC, s.row_id LIMIT ? OFFSET ?
    """, args + [per, (page - 1) * per]).fetchall()
    cols = [d[0] for d in c.description]
    return jsonify({
        "total": total, "page": page, "perPage": per,
        "rows": [_jdict(dict(zip(cols, r))) for r in rows],
    })


@app.route("/dashboard")
def spa():
    return send_from_directory(WEB, "index.html")


@app.route("/dashboard/<path:path>")
def spa_files(path: str):
    target = WEB / path
    if target.is_file():
        return send_from_directory(WEB, path)
    return send_from_directory(WEB, "index.html")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)