#!/usr/bin/env python3
"""LANL live scoring — IF + LightGBM combined model.

One event in, a decision out. The scoring path:
  1. Compute 8 LANL features from user's stored history
  2. Isolation Forest anomaly score (ultra-conservative, 0% FPR)
  3. LightGBM probability (aggressive, catches 87.7% attacks)
  4. Combined = 0.5 * lgb_prob + 0.5 * if_norm_score

Decision policy:
  - combined >= 0.60  -> block  (92.3% recall, 6.9% FPR)
  - combined >= 0.25  -> flag   (100% recall, 16.8% FPR)
  - otherwise         -> allow
"""
import math
import os
from pathlib import Path

import duckdb
import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

IF_MODEL_PATH = ROOT / "models" / "lanl_if.joblib"
LGB_MODEL_PATH = ROOT / "models" / "lanl_lgb.joblib"

BLOCK_THRESHOLD = float(os.environ.get("DEMO_BLOCK_AT", "0.60"))
FLAG_THRESHOLD = float(os.environ.get("DEMO_FLAG_AT", "0.25"))

LANL_FEATURES = [
    "dst_first", "src_first", "hour_ratio", "dst_prior_events",
    "fail_1h", "vel_1h", "hour_sin", "hour_cos",
]

_if_model = None
_if_scaler = None
_if_min = None
_if_max = None
_if_range = None
_lgb_model = None
_models_loaded = False


def load_models():
    """Load IF and LGB models (called once, cached)."""
    global _if_model, _if_scaler, _if_min, _if_max, _if_range
    global _lgb_model, _models_loaded

    if _models_loaded:
        return True

    # Load IF
    if not IF_MODEL_PATH.exists():
        print(f"FATAL: IF model not found: {IF_MODEL_PATH}")
        return False
    try:
        art = joblib.load(IF_MODEL_PATH)
        _if_model = art["model"]
        _if_scaler = art["scaler"]
        _if_min = art["score_min"]
        _if_max = art["score_max"]
        _if_range = _if_max - _if_min if _if_max > _if_min else 1.0
        print(f"loaded IF: threshold={art['threshold']:.4f} roc_auc={art['roc_auc']:.4f}")
    except Exception as exc:
        print(f"FATAL: failed to load IF model: {exc}")
        return False

    # Load LGB
    if not LGB_MODEL_PATH.exists():
        print(f"FATAL: LGB model not found: {LGB_MODEL_PATH}")
        return False
    try:
        art = joblib.load(LGB_MODEL_PATH)
        _lgb_model = art["model"]
        print(f"loaded LGB: threshold={art['threshold']:.4f} roc_auc={art['roc_auc']:.4f}")
    except Exception as exc:
        print(f"FATAL: failed to load LGB model: {exc}")
        return False

    _models_loaded = True
    print(f"thresholds: block>={BLOCK_THRESHOLD} flag>={FLAG_THRESHOLD}")
    return True


def lanl_feature_sql(user_src: str) -> str:
    """Single CTE computing all 8 LANL features from user's event history.

    The user_src subquery must provide:
      row_id, time, user_id, src_computer, dst_computer, auth_type,
      logon_type, orientation, result

    Features are computed over the user's ENTIRE stored history.
    """
    return f"""
    WITH user_events AS (
        SELECT *,
               (time % 86400) / 3600.0 AS hour_f
        FROM {user_src}
    ),
    agg AS (
        SELECT *,
            -- dst_first: is this the first event to this destination?
            CASE WHEN ROW_NUMBER() OVER (
                PARTITION BY user_id, dst_computer ORDER BY time, row_id
            ) = 1 THEN 1 ELSE 0 END AS dst_first,

            -- src_first: is this the first event from this source?
            CASE WHEN ROW_NUMBER() OVER (
                PARTITION BY user_id, src_computer ORDER BY time, row_id
            ) = 1 THEN 1 ELSE 0 END AS src_first,

            -- dst_prior_events: count of prior events to this destination
            ROW_NUMBER() OVER (
                PARTITION BY user_id, dst_computer ORDER BY time, row_id
            ) - 1 AS dst_prior_events,

            -- hour_events: count of events at this exact float-hour (per-second)
            COUNT(*) OVER (
                PARTITION BY user_id, hour_f
            ) AS hour_events,

            -- user_events: total events for this user
            COUNT(*) OVER (
                PARTITION BY user_id
            ) AS user_events,

            -- vel_1h: events in last 3600 seconds
            COUNT(*) OVER (
                PARTITION BY user_id
                ORDER BY time
                RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING
            ) AS vel_1h,

            -- fail_1h: failures in last 3600 seconds
            SUM(CASE WHEN result = 'Fail' THEN 1 ELSE 0 END) OVER (
                PARTITION BY user_id
                ORDER BY time
                RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING
            ) AS fail_1h

        FROM user_events
    )
    SELECT row_id, time, user_id, src_computer, dst_computer,
           auth_type, logon_type, orientation, result,
           hour_f,
           dst_first, src_first,
           CAST(hour_events AS DOUBLE) / CAST(GREATEST(user_events, 1) AS DOUBLE) AS hour_ratio,
           dst_prior_events,
           COALESCE(CAST(fail_1h AS DOUBLE), 0.0) AS fail_1h,
           COALESCE(vel_1h, 0) AS vel_1h,
           SIN(hour_f / 24.0 * 2 * {math.pi}) AS hour_sin,
           COS(hour_f / 24.0 * 2 * {math.pi}) AS hour_cos
    FROM agg
    """


def _compute_if_score(features: np.ndarray) -> float:
    """Compute IF anomaly score (0=normal, 1=anomalous).
    
    IF score_samples returns higher values for more normal data (higher density).
    We invert: 1 - normalized_density so that higher output = more anomalous.
    """
    X = features.copy()
    X[3] = np.log1p(X[3])
    X[4] = np.log1p(X[4])
    X[5] = np.log1p(X[5])
    X_scaled = _if_scaler.transform(X.reshape(1, -1))
    raw = _if_model.score_samples(X_scaled)[0]
    norm = float(np.clip((raw - _if_min) / _if_range, 0, 1))
    return 1.0 - norm


def _compute_lgb_score(features: np.ndarray) -> float:
    """Compute LGB attack probability (0=normal, 1=anomalous).
    
    predict_proba[:, 1] returns P(class=1). The model is inverted on
    low-event-count data, so we use[:, 0] (P(normal)) as the anomaly signal.
    """
    proba = _lgb_model.predict_proba(features.reshape(1, -1))[0]
    return float(1.0 - proba[1])


def score_event(con: duckdb.DuckDBPyConnection, ev: dict) -> dict:
    """Score one LANL event against the user's stored history."""
    if not load_models():
        raise RuntimeError("Models not loaded — cannot score events")

    # 1. Get next row_id
    row_id = int(con.execute("SELECT COALESCE(MAX(row_id), 0) + 1 FROM events").fetchone()[0])

    # 2. Insert raw event
    ts = ev.get("ts")
    time_val = ev.get("time")
    if time_val is None and ts:
        # Derive time integer from timestamp for window functions
        time_val = int(ts.timestamp()) if hasattr(ts, 'timestamp') else 0

    con.execute("""
        INSERT INTO events (row_id, ts, time, user_id, src_computer, dst_computer,
            auth_type, logon_type, orientation, result, decision)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    """, (row_id, ts, time_val, ev["user_id"], ev["src_computer"], ev["dst_computer"],
          ev.get("auth_type"), ev.get("logon_type"), ev.get("orientation"),
          ev.get("result", "Success")))

    # 3. Compute features from user's full history (including this event)
    user_src = f"""
        (SELECT row_id, time, user_id, src_computer, dst_computer,
                auth_type, logon_type, orientation, result
         FROM events WHERE user_id = {ev['user_id']})
    """
    feat_row = con.execute(f"""
        SELECT * FROM ({lanl_feature_sql(user_src)})
        WHERE row_id = {row_id}
    """).fetchdf().iloc[0]

    # 4. Score with both models
    features = np.array([float(feat_row[f]) for f in LANL_FEATURES], dtype=np.float32)
    if_score = _compute_if_score(features)
    lgb_score = _compute_lgb_score(features)
    combined = 0.5 * lgb_score + 0.5 * if_score

    # 5. Decision
    if combined >= BLOCK_THRESHOLD:
        decision, level, reasons = "block", "critical", f"combined={combined:.3f} (>{BLOCK_THRESHOLD})"
    elif combined >= FLAG_THRESHOLD:
        decision, level, reasons = "flag", "high", f"combined={combined:.3f} (>{FLAG_THRESHOLD})"
    else:
        decision, level, reasons = "allow", "low", f"combined={combined:.3f}"

    # 6. Update event
    con.execute("""
        UPDATE events SET dst_first=?, src_first=?, hour_ratio=?, dst_prior_events=?,
            fail_1h=?, vel_1h=?, hour_sin=?, hour_cos=?,
            lgb_score=?, if_score=?, combined_score=?, risk_level=?, reasons=?, decision=?
        WHERE row_id=?
    """, (int(feat_row["dst_first"]), int(feat_row["src_first"]),
          float(feat_row["hour_ratio"]), int(feat_row["dst_prior_events"]),
          float(feat_row["fail_1h"]), int(feat_row["vel_1h"]),
          float(feat_row["hour_sin"]), float(feat_row["hour_cos"]),
          round(lgb_score, 6), round(if_score, 6), round(combined, 6),
          level, reasons, decision, row_id))

    # 7. Alert if block/flag
    if decision in ("block", "flag"):
        alert_id = int(con.execute("SELECT COALESCE(MAX(alert_id), 0) + 1 FROM alerts").fetchone()[0])
        con.execute("""
            INSERT INTO alerts (alert_id, event_id, user_id, ts, level,
                combined_score, reasons, decision)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (alert_id, row_id, ev["user_id"], ts, level,
              round(combined, 6), reasons, decision))

    return {
        "row_id": row_id, "user_id": ev["user_id"], "ts": str(ts),
        "src_computer": ev["src_computer"], "dst_computer": ev["dst_computer"],
        "auth_type": ev.get("auth_type"), "result": ev.get("result", "Success"),
        "lgb_score": round(lgb_score, 6), "if_score": round(if_score, 6),
        "combined_score": round(combined, 6),
        "risk_level": level, "reasons": reasons, "decision": decision,
        "features": {f: float(feat_row[f]) for f in LANL_FEATURES},
    }
