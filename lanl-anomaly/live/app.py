#!/usr/bin/env python3
"""LANL live demo — Flask backend.

Routes:
  POST /events               score one LANL event -> JSON verdict
  GET  /events/stream        SSE: pushes every scored event to dashboard
  GET  /api/dashboard        KPIs, recent events, alerts
  GET  /api/investigation/<id>  feature breakdown + timeline
  GET  /api/users/<id>/profile  baseline + distributions
  GET  /api/users            all users + stats
  GET  /api/alerts           recent alerts
  POST /api/alerts/<id>/ack  acknowledge alert
  GET  /api/health           system status
  GET  /dashboard            serve React SPA

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

from flask import Flask, Response, jsonify, render_template, request, send_from_directory
from werkzeug.routing import IntegerConverter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live"))

import db as db  # noqa: E402
from db import get_con, init_schema, refresh_profile  # noqa: E402
from scoring import score_event, lanl_feature_sql  # noqa: E402

app = Flask(__name__)
_con_lock = threading.Lock()
_live_feed: "queue.Queue[dict]" = queue.Queue(maxsize=500)


class SignedIntConverter(IntegerConverter):
    """Like <int:...> but accepts negative ids (seeded user_ids are negative)."""
    regex = r"-?\d+"

app.url_map.converters["sint"] = SignedIntConverter

SEV_COLORS = {"low": "#57b06c", "medium": "#e8a33d", "high": "#ff9b9e", "critical": "#e5484d"}


def con():
    c = get_con()
    init_schema(c)
    return c


def _jdict(d: dict) -> dict:
    """JSON-safe dict."""
    out = {}
    for k, v in d.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif hasattr(v, "item"):
            out[k] = v.item()
        else:
            out[k] = v
    return out


def _users(c) -> list:
    rows = c.execute("SELECT * FROM users ORDER BY persona, name").fetchall()
    return [dict(zip([d[0] for d in c.description], r)) for r in rows]


def _publish(c, result: dict) -> None:
    """Push a scored event onto the SSE feed."""
    row = c.execute("SELECT name, raw_id, persona FROM users WHERE user_id = ?",
                    [result["user_id"]]).fetchone()
    name, raw_id, persona = (row if row else (None, None, None))
    try:
        _live_feed.put_nowait({
            "event_id": result["row_id"],
            "user_id": result["user_id"],
            "name": name,
            "raw_id": raw_id,
            "persona": persona,
            "ts": result["ts"],
            "src_computer": result["src_computer"],
            "dst_computer": result["dst_computer"],
            "auth_type": result.get("auth_type"),
            "result": result.get("result"),
            "lgb_score": result.get("lgb_score", 0.0),
            "if_score": result.get("if_score", 0.0),
            "combined_score": result["combined_score"],
            "dev_points": result.get("dev_points", 0),
            "dev_reasons": result.get("dev_reasons", ""),
            "risk_level": result["risk_level"],
            "reasons": result["reasons"],
            "decision": result["decision"],
        })
    except queue.Full:
        pass


# ---------------- Routes ----------------

TEMPLATES = ROOT / "live" / "templates"


@app.route("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/dashboard")
def spa():
    return send_from_directory(WEB, "index.html")


@app.route("/dashboard/<path:path>")
def spa_files(path: str):
    target = WEB / path
    if target.is_file():
        return send_from_directory(WEB, path)
    return send_from_directory(WEB, "index.html")


@app.route("/events/stream")
def stream():
    """SSE: one `score` message per scored event."""
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

def _normalize_result(raw: str) -> str:
    """Canonicalize result values. Training data and feature SQL use 'Fail';
    clients (login.html) send 'Failure'."""
    return "Fail" if str(raw).strip().lower() in {"fail", "failure", "failed"} else "Success"


@app.route("/events", methods=["POST"])
def api_events():
    """Score one LANL event. Expects JSON with:
      user_id, src_computer, dst_computer, auth_type, logon_type,
      orientation, result, ts (optional), time (optional)
    """
    c = con()
    payload = request.get_json(silent=True) or request.form
    try:
        uid = int(payload["user_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "user_id (int) required"}), 400
    user = c.execute("SELECT * FROM users WHERE user_id = ?", [uid]).fetchone()
    if user is None:
        return jsonify({"error": "unknown user_id"}), 404

    ts = datetime.now(timezone.utc).replace(tzinfo=None)
    if payload.get("ts"):
        try:
            ts = datetime.fromisoformat(str(payload["ts"]).replace("Z", "+00:00"))
            if ts.tzinfo:
                ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            pass

    time_val = payload.get("time")
    if time_val is None:
        # Continue the seeded demo timeline: history-end + real elapsed
        # seconds since seeding. Keeps pseudo-hours near user habits and
        # makes vel/fail windows see both history and session events.
        anchor = db.get_seed_anchor(c)
        if anchor:
            frame_start, wallclock_at_seed = anchor
            time_val = frame_start + max(0, int(time.time()) - wallclock_at_seed)
        else:
            time_val = int(ts.timestamp())

    ev = {
        "user_id": uid,
        "ts": ts,
        "time": int(time_val),
        "src_computer": payload.get("src_computer", ""),
        "dst_computer": payload.get("dst_computer", ""),
        "auth_type": payload.get("auth_type", ""),
        "logon_type": payload.get("logon_type", ""),
        "orientation": payload.get("orientation", ""),
        "result": _normalize_result(payload.get("result", "Success")),
    }

    with _con_lock:
        result = score_event(c, ev)
    _publish(c, result)
    return jsonify(_jdict(result))


@app.route("/risk/<int:event_id>")
def api_risk(event_id: int):
    c = con()
    row = c.execute("""
        SELECT e.*, u.name, u.raw_id, u.persona
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
        SELECT u.name, u.raw_id, u.persona,
               p.typical_src_computers, p.typical_dst_computers,
               p.typical_hours, p.typical_auth_types,
               p.avg_events_per_hour, p.total_events, p.failure_rate,
               p.profile_status, p.updated_at
        FROM users u LEFT JOIN user_profile p ON p.user_id = u.user_id
        WHERE u.user_id = ?
    """, [user_id]).fetchone()
    if row is None:
        return jsonify({"error": "unknown user_id"}), 404
    d = dict(zip([d[0] for d in c.description], row))
    return jsonify(_jdict(d))


@app.route("/api/health")
def api_health():
    from scoring import _models_loaded
    return jsonify({
        "status": "ok",
        "models_loaded": _models_loaded,
    })


LIVE_EVENTS = "events WHERE decision != 'history'"


@app.route("/api/dashboard")
def api_dashboard():
    c = con()
    agg = c.execute(f"""
        SELECT COUNT(*) total,
               COUNT(*) FILTER (WHERE risk_level IN ('high', 'critical')) flagged,
               COUNT(DISTINCT user_id) users,
               COUNT(DISTINCT user_id)
                 FILTER (WHERE risk_level IN ('high', 'critical')) risky_users
        FROM {LIVE_EVENTS}
    """).fetchone()
    total, flagged, users, risky_users = agg

    # Events per minute (last 5 minutes of events)
    epm = c.execute(f"""
        SELECT COUNT(*) FROM {LIVE_EVENTS}
        AND ts >= now() - INTERVAL '5 minutes'
    """).fetchone()[0]

    # Risk distribution
    risk_dist = c.execute(f"""
        SELECT COALESCE(risk_level, 'low') lvl, COUNT(*) n
        FROM {LIVE_EVENTS} GROUP BY 1
    """).fetchall()
    risk_dist = [{"name": lvl.title(), "value": n, "color": SEV_COLORS.get(lvl, "#718296")}
                 for lvl, n in risk_dist]

    # Recent events
    logins = c.execute("""
        SELECT e.row_id, e.user_id, u.name, u.raw_id, e.src_computer, e.dst_computer,
               e.auth_type, e.result, e.decision, e.combined_score, e.lgb_score,
               e.if_score, e.ts, e.risk_level, e.reasons
        FROM events e LEFT JOIN users u ON u.user_id = e.user_id
        WHERE e.decision != 'history'
        ORDER BY e.row_id DESC LIMIT 30
    """).fetchall()
    recent_events = [{
        "id": e[0], "user_id": e[1], "name": e[2] or str(e[1]), "raw_id": e[3] or "",
        "src_computer": e[4] or "-", "dst_computer": e[5] or "-",
        "auth_type": e[6] or "-", "result": e[7] or "-",
        "decision": e[8], "combined_score": e[9] or 0,
        "lgb_score": e[10] or 0, "if_score": e[11] or 0,
        "ts": e[12].strftime("%H:%M:%S") if e[12] else "-",
        "risk_level": e[13] or "low", "reasons": e[14] or "",
    } for e in logins]

    # Alerts
    al = c.execute("""
        SELECT a.*, u.name, u.raw_id FROM alerts a
        LEFT JOIN users u ON u.user_id = a.user_id
        ORDER BY a.alert_id DESC LIMIT 20
    """).fetchall()
    alerts = [{
        "id": a[0], "eventId": a[1], "severity": a[4],
        "user_id": a[2], "name": a[9] or str(a[2]), "raw_id": a[10] or "",
        "combined_score": a[5], "reasons": a[6], "decision": a[7],
        "timestamp": a[3].strftime("%H:%M:%S") if a[3] else "-",
        "status": "acknowledged" if a[8] else "new",
    } for a in al]

    return jsonify({
        "kpis": {
            "totalEvents": total, "anomalies": flagged,
            "highRiskUsers": risky_users, "usersMonitored": users,
            "eventsPerMinute": epm,
        },
        "riskDistribution": risk_dist,
        "recentEvents": recent_events,
        "alerts": alerts,
    })


@app.route("/api/alerts")
def api_alerts_spa():
    c = con()
    rows = c.execute("""
        SELECT a.*, u.name, u.raw_id FROM alerts a
        LEFT JOIN users u ON u.user_id = a.user_id
        ORDER BY a.alert_id DESC LIMIT 50
    """).fetchall()
    alerts = [{
        "id": r[0], "eventId": r[1], "severity": r[4],
        "user_id": r[2], "name": r[9] or str(r[2]), "raw_id": r[10] or "",
        "combined_score": r[5], "reasons": r[6], "decision": r[7],
        "timestamp": r[3].strftime("%H:%M:%S") if r[3] else "-",
        "status": "acknowledged" if r[8] else "new",
    } for r in rows]
    return jsonify(alerts)


@app.route("/api/alerts/<int:alert_id>/ack", methods=["POST"])
def api_alert_ack(alert_id: int):
    c = con()
    c.execute("UPDATE alerts SET acked_at = now() WHERE alert_id = ? OR event_id = ?",
              [alert_id, alert_id])
    return jsonify({"ok": True, "alert_id": alert_id})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Clear all live scored events + alerts. History & profiles preserved."""
    c = con()
    c.execute("DELETE FROM events WHERE decision != 'history'")
    c.execute("DELETE FROM alerts")
    return jsonify({"ok": True})


@app.route("/api/stats")
def api_stats():
    c = con()
    total = c.execute("SELECT COUNT(*) FROM events WHERE decision != 'history'").fetchone()[0]
    alerts = c.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    history = c.execute("SELECT COUNT(*) FROM events WHERE decision = 'history'").fetchone()[0]
    users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return jsonify({"live_events": total, "alerts": alerts, "history_events": history, "users": users})


@app.route("/api/investigation/<int:event_id>")
def api_investigation(event_id: int):
    c = con()
    row = c.execute("""
        SELECT e.*, u.name, u.raw_id, u.persona,
               p.typical_src_computers, p.typical_dst_computers,
               p.typical_hours, p.typical_auth_types,
               p.avg_events_per_hour, p.total_events, p.failure_rate
        FROM events e
        LEFT JOIN users u ON u.user_id = e.user_id
        LEFT JOIN user_profile p ON p.user_id = e.user_id
        WHERE e.row_id = ?
    """, [event_id]).fetchone()
    if row is None:
        return jsonify({"error": "event not found"}), 404
    e = dict(zip([d[0] for d in c.description], row))

    # Feature contributions
    features = []
    if e.get("dst_first"):
        features.append({"feature": "First-time Destination", "value": 1, "color": "#e5484d",
                         "detail": f"Never visited {e.get('dst_computer')}"})
    if e.get("src_first"):
        features.append({"feature": "First-time Source", "value": 1, "color": "#e5484d",
                         "detail": f"Never used {e.get('src_computer')}"})
    if e.get("dst_prior_events", 0) == 0 and not e.get("dst_first"):
        features.append({"feature": "Unfamiliar Destination", "value": 0, "color": "#e5484d",
                         "detail": f"0 prior visits to {e.get('dst_computer')}"})
    if e.get("vel_1h", 0) > 10:
        features.append({"feature": "High Velocity", "value": e["vel_1h"], "color": "#ff9b9e",
                         "detail": f"{e['vel_1h']} events in last hour"})
    if e.get("fail_1h", 0) > 0:
        features.append({"feature": "Recent Failures", "value": e["fail_1h"], "color": "#ff9b9e",
                         "detail": f"{e['fail_1h']:.0f} failures in last hour"})
    if e.get("hour_ratio", 0) > 0.01:
        features.append({"feature": "Unusual Hour", "value": e["hour_ratio"], "color": "#e8a33d",
                         "detail": f"hour_ratio={e['hour_ratio']:.4f} (unusual time for this user)"})

    # Timeline
    timeline_rows = c.execute("""
        SELECT ts, src_computer, dst_computer, decision, combined_score, result
        FROM events
        WHERE user_id = ? AND decision != 'history'
        ORDER BY row_id DESC LIMIT 10
    """, [e["user_id"]]).fetchall()
    timeline = [{
        "event": f"{src} -> {dst}" if ok == "Success" else f"{src} -> {dst} (FAIL)",
        "icon": "check" if ok == "Success" else "x",
        "severity": "critical" if d == "block" else ("high" if d == "flag" else None),
        "time": ts.strftime("%H:%M:%S") if ts else "-",
        "src_computer": src, "dst_computer": dst,
        "score": score or 0,
    } for ts, src, dst, d, score, ok in reversed(timeline_rows)]

    return jsonify({
        "displayName": e.get("name") or str(e["user_id"]),
        "rawId": e.get("raw_id") or "",
        "user_id": e["user_id"],
        "severity": e.get("risk_level") or "low",
        "combinedScore": e.get("combined_score") or 0,
        "ifScore": e.get("if_score") or 0,
        "devPoints": e.get("dev_points") or 0,
        "devReasons": e.get("dev_reasons") or "",
        "type": e.get("decision") or "allow",
        "description": e.get("reasons") or "-",
        "src_computer": e.get("src_computer") or "-",
        "dst_computer": e.get("dst_computer") or "-",
        "auth_type": e.get("auth_type") or "-",
        "logon_type": e.get("logon_type") or "-",
        "result": e.get("result") or "-",
        "timeline": timeline,
        "featureContributions": features,
        "baseline": {
            "typicalSrcComputers": (e.get("typical_src_computers") or "").split(","),
            "typicalDstComputers": (e.get("typical_dst_computers") or "").split(","),
            "typicalHours": (e.get("typical_hours") or "").split(","),
            "typicalAuthTypes": (e.get("typical_auth_types") or "").split(","),
            "avgEventsPerHour": e.get("avg_events_per_hour") or 0,
            "totalEvents": e.get("total_events") or 0,
            "failureRate": e.get("failure_rate") or 0,
        },
        "features": {
            "dst_first": e.get("dst_first"), "src_first": e.get("src_first"),
            "hour_ratio": e.get("hour_ratio"), "dst_prior_events": e.get("dst_prior_events"),
            "vel_1h": e.get("vel_1h"), "fail_1h": e.get("fail_1h"),
            "hour_sin": e.get("hour_sin"), "hour_cos": e.get("hour_cos"),
        },
    })


@app.route("/api/users")
def api_users():
    c = con()
    rows = c.execute("""
        SELECT u.user_id, u.name, u.raw_id, u.persona,
               COUNT(e.row_id) FILTER (WHERE e.decision != 'history') live_events,
               COUNT(e.row_id) FILTER (WHERE e.decision IN ('flag', 'block')) flags,
               MAX(CASE WHEN e.decision != 'history' THEN e.combined_score END) max_score
        FROM users u LEFT JOIN events e ON e.user_id = u.user_id
        GROUP BY u.user_id, u.name, u.raw_id, u.persona
        ORDER BY u.persona, u.user_id
    """).fetchall()
    cols = [d[0] for d in c.description]
    return jsonify([dict(zip(cols, r)) for r in rows])


# ---------------- SPA ----------------

WEB = ROOT / "live" / "web" / "dist"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
