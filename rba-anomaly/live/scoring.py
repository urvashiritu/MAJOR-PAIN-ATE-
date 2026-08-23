#!/usr/bin/env python3
"""Phase 7b — live scoring (rules + ML model).

One event in, a decision out. The scoring path combines:
  1. Rule engine (score_sql from src/04) — catches 79% of attacks
  2. Trained ML model (XGBoost from models/xgboost_model.joblib) — catches additional attacks

Decision policy:
  - is_attack_ip (blocklist)          -> block, hard kill
  - ml_score >= ml_threshold           -> flag (ML says suspicious)
  - rule_score >= critical (90)        -> block
  - rule_score >= flag (45)            -> flag
  - otherwise                          -> allow
"""
import importlib.util
import os
from pathlib import Path

import duckdb
import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

ML_MODEL_PATH = ROOT / "models" / "xgboost_model.joblib"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_shared = _load_module("_shared", ROOT / "src" / "_shared.py")
_feat = _load_module("feat", ROOT / "src" / "02_feature_engineering.py")
_rule = _load_module("rule", ROOT / "src" / "04_rule_baseline.py")

feature_sql = _feat.feature_sql
score_sql = _rule.score_sql
LEVEL_BOUNDS = _rule.LEVEL_BOUNDS
FEATURE_COLS = _shared.FEATURE_COLS

from db import refresh_profile  # noqa: E402

FLAG_AT = int(os.environ.get("DEMO_FLAG_AT", "45"))

_ml_model = None
_ml_threshold = None


def load_ml_model():
    """Load the trained ML model (lazy, cached)."""
    global _ml_model, _ml_threshold
    if _ml_model is not None:
        return True
    if not ML_MODEL_PATH.exists():
        return False
    try:
        artifact = joblib.load(ML_MODEL_PATH)
        _ml_model = artifact["model"]
        _ml_threshold = artifact["threshold"]
        print(f"loaded ML model: {artifact.get('model_name', 'unknown')} "
              f"(threshold={_ml_threshold:.4f}, gold_f1={artifact.get('gold_f1', 'n/a')})")
        return True
    except Exception as exc:
        print(f"WARNING: failed to load ML model: {exc}")
        return False


def ml_predict(feat_row: dict) -> float:
    """Predict ML score (probability of attack) from a feature row."""
    if _ml_model is None:
        return 0.0
    h = feat_row["hour"] / 24.0 * 2 * np.pi
    feat_row["hour_sin"] = np.sin(h)
    feat_row["hour_cos"] = np.cos(h)

    X = np.array([[feat_row.get(c, 0) for c in FEATURE_COLS]])
    X = np.nan_to_num(X, nan=0.0)
    proba = _ml_model.predict_proba(X)[:, 1][0]
    return float(proba)


def score_event(con: duckdb.DuckDBPyConnection, ev: dict) -> dict:
    """Score one login event against the user's stored history.

    Combines rule engine + trained ML model for final decision.
    """
    load_ml_model()

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

    ml_score = ml_predict(feat.to_dict())

    row = con.execute(f"""
        SELECT * FROM ({score_sql(f"({feature_sql(user_src)})")})
        WHERE row_id = {row_id}
    """).fetchdf().iloc[0]

    rule_reasons = str(row["reasons"])
    rule_score = int(row["rule_score"])

    if bool(feat["is_attack_ip"]):
        decision, level = "block", "critical"
        reasons = "blocklist ip"
    elif _ml_model is not None and ml_score >= _ml_threshold:
        decision, level = "flag", "high"
        reasons = f"ml suspicious ({ml_score:.3f})"
    elif rule_score >= LEVEL_BOUNDS["critical"]:
        decision, level = "block", row["risk_level"]
        reasons = rule_reasons
    elif rule_score >= FLAG_AT:
        decision, level = "flag", row["risk_level"]
        reasons = rule_reasons
    else:
        decision, level = "allow", row["risk_level"]
        reasons = rule_reasons

    con.execute("""
        UPDATE events SET rule_score = ?, ml_score = ?, risk_level = ?, reasons = ?, decision = ?
        WHERE row_id = ?
    """, (rule_score, round(ml_score, 6), level, reasons, decision, row_id))

    if decision in ("block", "flag"):
        alert_id = int(con.execute("SELECT COALESCE(MAX(alert_id), 0) + 1 FROM alerts").fetchone()[0])
        con.execute("""
            INSERT INTO alerts (alert_id, event_id, user_id, ts, level,
                rule_score, reasons, decision)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (alert_id, row_id, ev["user_id"], ev["ts"], level,
              rule_score, reasons, decision))
    elif decision == "allow":
        refresh_profile(con, ev["user_id"])

    return {
        "row_id": row_id, "user_id": ev["user_id"], "ts": ev["ts"],
        "ip": ev.get("ip"), "country": ev.get("country"),
        "device_type": ev.get("device_type"), "os_family": ev.get("os_family"),
        "browser_family": ev.get("browser_family"),
        "login_success": bool(ev["login_success"]),
        "rule_score": rule_score, "ml_score": round(ml_score, 6),
        "risk_level": level, "reasons": reasons, "decision": decision,
    }
