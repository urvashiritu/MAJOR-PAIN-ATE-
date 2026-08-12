#!/usr/bin/env python3
"""Phase 7b — live scoring.

One event in, a decision out. The scoring path is the *same SQL* the
offline pipeline used:

  feature_sql (src/02)  -> behavioral + seen-before features for the user
  score_sql   (src/04)  -> rule points, risk level, human-readable reasons
  HGB model   (src/06)  -> supervised probability on the 21 FEATURE_COLS

The new event is inserted into `events` first; the feature query runs over
the user's full history (new event included, so its window features —
LAG, seen-before, rapid_login_rate — are computed against the real past),
then the scores ride back onto the event row.

Decision policy (state assumption, demo defaults):
  - is_attack_ip (blocklist)          -> block, hard kill
  - rule_score >= high (65)           -> block
  - ml_score  >= tuned threshold      -> flag (challenge)
  - otherwise                          -> allow
"""
import importlib.util
from pathlib import Path

import duckdb
import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_shared = _load_module("_shared", ROOT / "src" / "_shared.py")
_feat = _load_module("feat", ROOT / "src" / "02_feature_engineering.py")
_rule = _load_module("rule", ROOT / "src" / "04_rule_baseline.py")

FEATURE_COLS = _shared.FEATURE_COLS
feature_sql = _feat.feature_sql
score_sql = _rule.score_sql
LEVEL_BOUNDS = _rule.LEVEL_BOUNDS

from db import refresh_profile  # noqa: E402

MODEL_PATH = ROOT / "models" / "supervised_hgb.joblib"

_model = None


def load_model(path: Path = MODEL_PATH) -> dict:
    global _model
    if _model is None:
        _model = joblib.load(path)
    return _model


def score_event(con: duckdb.DuckDBPyConnection, ev: dict) -> dict:
    """Score one login event against the user's stored history.

    `ev` must carry: user_id, ts, ip, country, device_type, os_family,
    browser_family, login_success, is_attack_ip, is_ato, is_private_ip,
    geo_unreliable, rtt_missing, ua_os_conflict, is_generator_bot, is_vlc, asn.
    Inserts the row, computes features + rules + ml score, writes the
    decision back, raises an alert when needed. Returns the scored row.
    """
    row_id = int(con.execute("SELECT COALESCE(MAX(row_id), 0) + 1 FROM events").fetchone()[0])
    con.execute("""
        INSERT INTO events (row_id, ts, user_id, ip, country, device_type,
            os_family, browser_family, login_success, is_attack_ip, is_ato,
            is_private_ip, geo_unreliable, rtt_missing, ua_os_conflict,
            is_generator_bot, is_vlc, asn)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (row_id, ev["ts"], ev["user_id"], ev.get("ip"), ev.get("country"),
          ev.get("device_type"), ev.get("os_family"), ev.get("browser_family"),
          ev["login_success"], ev.get("is_attack_ip"), ev.get("is_ato"),
          ev.get("is_private_ip"), ev.get("geo_unreliable"), ev.get("rtt_missing"),
          ev.get("ua_os_conflict"), ev.get("is_generator_bot"), ev.get("is_vlc"),
          ev.get("asn")))

    user_src = f"""
        (SELECT row_id, ts, user_id, ip, country, asn, device_type, os_family,
                browser_family, login_success, is_attack_ip, is_ato,
                is_private_ip, geo_unreliable, rtt_missing, ua_os_conflict,
                is_generator_bot, is_vlc
         FROM events WHERE user_id = {ev['user_id']})
    """
    feat = con.execute(f"""
        SELECT * FROM ({feature_sql(user_src)})
        WHERE row_id = {row_id}
    """).fetchdf().iloc[0]

    h = feat["hour"] / 24.0 * 2 * np.pi
    feat["hour_sin"] = np.sin(h)
    feat["hour_cos"] = np.cos(h)

    row = con.execute(f"""
        SELECT * FROM ({score_sql(f"({feature_sql(user_src)})")})
        WHERE row_id = {row_id}
    """).fetchdf().iloc[0]

    model = load_model()
    X = np.array([[float(feat[c]) for c in FEATURE_COLS]], dtype=float)
    ml_score = float(model["model"].predict_proba(X)[:, 1][0])
    threshold = float(model["threshold"])

    if bool(feat["is_attack_ip"]):
        decision, level, reason = "block", "critical", "blocklist ip"
    elif int(row["rule_score"]) >= LEVEL_BOUNDS["high"]:
        decision, level = "block", row["risk_level"]
    elif ml_score >= threshold:
        decision, level = "flag", row["risk_level"]
    else:
        decision, level = "allow", row["risk_level"]

    reasons = str(row["reasons"])
    con.execute("""
        UPDATE events SET rule_score = ?, ml_score = ?, risk_level = ?, reasons = ?, decision = ?
        WHERE row_id = ?
    """, (int(row["rule_score"]), ml_score, level, reasons, decision, row_id))

    if decision in ("block", "flag"):
        alert_id = int(con.execute("SELECT COALESCE(MAX(alert_id), 0) + 1 FROM alerts").fetchone()[0])
        con.execute("""
            INSERT INTO alerts (alert_id, event_id, user_id, ts, level,
                rule_score, ml_score, reasons, decision)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (alert_id, row_id, ev["user_id"], ev["ts"], level,
              int(row["rule_score"]), ml_score, reasons, decision))
    elif decision == "allow":
        refresh_profile(con, ev["user_id"])

    return {
        "row_id": row_id, "user_id": ev["user_id"], "ts": ev["ts"],
        "ip": ev.get("ip"), "country": ev.get("country"),
        "device_type": ev.get("device_type"), "os_family": ev.get("os_family"),
        "browser_family": ev.get("browser_family"),
        "login_success": bool(ev["login_success"]),
        "rule_score": int(row["rule_score"]), "ml_score": ml_score,
        "threshold": threshold, "risk_level": level,
        "reasons": reasons, "decision": decision,
    }
