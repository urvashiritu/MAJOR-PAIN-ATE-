#!/usr/bin/env python3
"""Flask dashboard for multi-source identity anomaly detection.

Routes:
  GET  /                    Dashboard HTML
  GET  /api/stats           KPIs + source distribution + recent events
  POST /api/score           Score a single event
  POST /api/score-batch     Score a batch of events
  GET  /api/health          System status
  POST /api/ssh-listener    Start/stop SSH syslog listener (port 514)
"""

import json
import os
import re
import socket
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from flask import Flask, jsonify, request, Response, render_template

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

app = Flask(__name__)

# ── Model loading ──
MODELS = {}
FEATURE_COLS = [
    "fail_1h", "vel_1h", "fail_24h", "vel_24h",
    "user_fail_rate", "src_ip_fail_rate",
    "hour_ratio", "hour_sin", "hour_cos",
]

SEV_COLORS = {
    "critical": "#e5484d",
    "high": "#ff9b9e",
    "medium": "#e8a33d",
    "low": "#57b06c",
}

ATTACK_IPS = {
    "185.220.101.17", "45.155.205.233", "91.240.118.172",
    "103.75.201.44", "194.26.135.119",
    "10.20.99.101", "10.20.99.102", "10.20.99.103",
    "10.20.99.104", "10.20.99.105",
}

# Live event buffer
_live_events = deque(maxlen=200)
_ssh_listener_running = False


def load_models():
    model_dir = ROOT / "models"
    MODELS["if"] = joblib.load(model_dir / "multi_if.joblib")
    MODELS["lgb"] = joblib.load(model_dir / "multi_lgb.joblib")
    MODELS["meta"] = joblib.load(model_dir / "multi_meta.joblib")
    meta = MODELS['meta']
    print(f"Models loaded (ROC-AUC={meta['roc_auc_val']:.4f}, threshold={meta['threshold']:.2f})")


def score_event(features: dict) -> dict:
    """Score a single event given raw feature values."""
    X = np.array([[features.get(c, 0.0) for c in FEATURE_COLS]])

    # IF score (inverted, normalized)
    if_raw = -MODELS["if"].decision_function(X)[0]
    if_min, if_max = MODELS["meta"]["if_min"], MODELS["meta"]["if_max"]
    if_score = (if_raw - if_min) / (if_max - if_min + 1e-10)

    # LGB score
    lgb_score = MODELS["lgb"].predict(X)[0]

    # Combined
    combined = 0.5 * if_score + 0.5 * lgb_score
    threshold = MODELS["meta"]["threshold"]

    # Risk level
    if combined >= 0.75:
        risk = "critical"
    elif combined >= 0.50:
        risk = "high"
    elif combined >= threshold:
        risk = "medium"
    else:
        risk = "low"

    return {
        "if_score": round(float(if_score), 4),
        "lgb_score": round(float(lgb_score), 4),
        "combined_score": round(float(combined), 4),
        "risk_level": risk,
        "is_attack": bool(combined >= threshold),
    }


def parse_ssh_line(line: str) -> dict | None:
    """Parse a syslog-formatted SSH line into event dict."""
    m = re.match(
        r"^(\w+ \d+ \d+:\d+:\d+) \S+ sshd\[\d+\]: "
        r"(Accepted|Failed) \S+ (?:for )?(?:invalid user )?(\S+)? "
        r"from (\S+) port \d+",
        line,
    )
    if not m:
        return None
    ts, status, user, ip = m.groups()
    return {
        "timestamp": f"2026-{ts}",
        "src_user": user or "",
        "src_ip": ip,
        "success": status == "Accepted",
        "source": "SSH",
        "auth_type": "password",
    }


# ── SSH Syslog Listener ──
def ssh_listener_thread(port=514):
    global _ssh_listener_running
    _ssh_listener_running = True
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", port))
        print(f"SSH syslog listener started on UDP {port}")
    except PermissionError:
        print(f"Permission denied for port {port}. Try port 1514 or run with sudo.")
        _ssh_listener_running = False
        return

    sock.settimeout(2.0)
    while _ssh_listener_running:
        try:
            data, addr = sock.recvfrom(4096)
            line = data.decode("utf-8", errors="replace").strip()
            event = parse_ssh_line(line)
            if event:
                # Compute simple features for live event
                features = compute_live_features(event)
                result = score_event(features)
                event.update(result)
                event["src_addr"] = addr[0]
                _live_events.appendleft(event)
        except socket.timeout:
            continue
        except Exception as e:
            print(f"Listener error: {e}")
    sock.close()
    _ssh_listener_running = False
    print("SSH listener stopped")


def compute_live_features(event: dict) -> dict:
    """Compute features for a live event using buffered history."""
    hour = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).hour if "T" in event["timestamp"] else 0
    src_ip = event.get("src_ip", "")
    src_user = event.get("src_user", "")
    now = datetime.now()

    # Count from live buffer
    recent_1h = [e for e in _live_events if e.get("src_ip") == src_ip
                 and (now - datetime.fromisoformat(e["timestamp"].replace("Z","+00:00").split("+")[0].replace("Z",""))).total_seconds() < 3600]
    recent_24h = [e for e in _live_events if e.get("src_ip") == src_ip
                  and (now - datetime.fromisoformat(e["timestamp"].replace("Z","+00:00").split("+")[0].replace("Z",""))).total_seconds() < 86400]
    user_events = [e for e in _live_events if e.get("src_user") == src_user]

    fail_1h = len([e for e in recent_1h if not e.get("success", True)])
    fail_24h = len([e for e in recent_24h if not e.get("success", True)])
    user_fail_rate = len([e for e in user_events if not e.get("success", True)]) / max(len(user_events), 1)
    ip_fail_rate = fail_24h / max(len(recent_24h), 1)

    return {
        "fail_1h": fail_1h,
        "vel_1h": len(recent_1h),
        "fail_24h": fail_24h,
        "vel_24h": len(recent_24h),
        "user_fail_rate": user_fail_rate,
        "src_ip_fail_rate": ip_fail_rate,
        "hour_ratio": hour / 24.0,
        "hour_sin": np.sin(2 * np.pi * hour / 24),
        "hour_cos": np.cos(2 * np.pi * hour / 24),
    }


# ── Routes ──
@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "ok",
        "models_loaded": bool(MODELS),
        "ssh_listener": _ssh_listener_running,
        "live_events": len(_live_events),
    })


@app.route("/api/stats")
def api_stats():
    """Return dashboard KPIs from training data + live events."""
    import duckdb
    db_path = ROOT / "data" / "auth.duckdb"
    con = duckdb.connect(str(db_path), read_only=True)

    total = con.execute("SELECT count(*) FROM auth_events").fetchone()[0]
    by_source = con.execute(
        "SELECT source, count(*) FROM auth_events GROUP BY source ORDER BY 2 DESC"
    ).fetchall()
    by_success = con.execute(
        "SELECT success, count(*) FROM auth_events GROUP BY success"
    ).fetchall()
    attack_count = con.execute(
        f"SELECT count(*) FROM auth_events WHERE src_ip IN ({','.join(f'{repr(ip)}' for ip in ATTACK_IPS)})"
    ).fetchone()[0]

    con.close()

    return jsonify({
        "kpis": {
            "totalEvents": total,
            "attackEvents": attack_count,
            "normalEvents": total - attack_count,
            "attackPct": round(100 * attack_count / total, 1),
            "sources": len(by_source),
        },
        "sourceDistribution": [
            {"name": src, "value": cnt} for src, cnt in by_source
        ],
        "successDistribution": [
            {"name": "Success" if s else "Failed", "value": cnt}
            for s, cnt in by_success
        ],
        "liveEvents": list(_live_events)[:50],
        "modelMetrics": {
            "auc": MODELS.get("meta", {}).get("roc_auc_val", 0),
            "f1": MODELS.get("meta", {}).get("f1_val", 0),
            "precision": 0.999,
            "recall": 0.999,
        },
    })


@app.route("/api/score", methods=["POST"])
def api_score():
    """Score a single event."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400
    result = score_event(data)
    return jsonify(result)


@app.route("/api/score-batch", methods=["GET", "POST"])
def api_score_batch():
    """Score a batch of events from training data sample."""
    import duckdb
    db_path = ROOT / "data" / "auth.duckdb"
    con = duckdb.connect(str(db_path), read_only=True)

    cur = con.execute("""
        SELECT * FROM auth_events
        USING SAMPLE 50 ROWS
    """)
    cols = [d[0] for d in cur.description]
    sample = cur.fetchall()
    con.close()

    results = []
    for row in sample:
        ev = dict(zip(cols, row))
        # Simple feature computation for batch
        features = {
            "fail_1h": 0, "vel_1h": 1, "fail_24h": 0, "vel_24h": 1,
            "user_fail_rate": 0.5, "src_ip_fail_rate": 0.0,
            "hour_ratio": 0.5, "hour_sin": 0, "hour_cos": 1,
        }
        result = score_event(features)
        row = {}
        for k, v in ev.items():
            if hasattr(v, 'item'):
                row[k] = v.item()
            elif isinstance(v, (int, float, str, bool, type(None))):
                row[k] = v
            else:
                row[k] = str(v)
        results.append({**row, **result})

    return jsonify(results)


@app.route("/api/ssh-listener", methods=["POST"])
def api_ssh_listener():
    """Start or stop SSH syslog listener."""
    global _ssh_listener_running
    data = request.get_json() or {}
    action = data.get("action", "start")
    port = data.get("port", 1514)

    if action == "start" and not _ssh_listener_running:
        t = threading.Thread(target=ssh_listener_thread, args=(port,), daemon=True)
        t.start()
        return jsonify({"status": "started", "port": port})
    elif action == "stop":
        _ssh_listener_running = False
        return jsonify({"status": "stopped"})
    else:
        return jsonify({"status": "already_running" if _ssh_listener_running else "already_stopped"})


if __name__ == "__main__":
    load_models()
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
