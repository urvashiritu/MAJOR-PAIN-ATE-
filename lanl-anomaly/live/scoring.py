#!/usr/bin/env python3
"""LANL live scoring — Isolation Forest + per-user habit deviation.

One event in, a decision out. The scoring path:
  1. Compute 8 LANL features from user's stored history
  2. Isolation Forest anomaly score (the primary detector)
  3. Habit-deviation points vs THIS user's baseline
     (first-ever destination/source outside their usual set,
      velocity above floor, repeated auth failures)
     fused as: combined = if_score + 0.10 * min(dev_points, 3)

LightGBM is loaded and its score is DISPLAYED for transparency, but it is
NOT part of the decision: it was trained on full-scale users (~52k events
per destination) and saturates at 1.0 on demo-scale histories.

Decision policy:
  - combined >= BLOCK_THRESHOLD (default 0.80) -> block
  - combined >= FLAG_THRESHOLD  (default 0.70) -> flag
  - otherwise                                   -> allow

Features (8 — matches the original training pipeline):
  dst_first          binary   first-ever event to this destination
  src_first          binary   first-ever event from this source
  hour_ratio         float    hour_events / max(user_events, 1)
  dst_prior_events   int      cumulative prior visits to this destination
  fail_1h            float    failures in last 3600 seconds
  vel_1h             int      events in last 3600 seconds
  hour_sin           float    sin(hour / 24 * 2pi)
  hour_cos           float    cos(hour / 24 * 2pi)
"""
import math
import os
import time
from pathlib import Path

import duckdb
import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

IF_MODEL_PATH = ROOT / "models" / "lanl_if.joblib"
LGB_MODEL_PATH = ROOT / "models" / "lanl_lgb.joblib"

# Measured 2026-08-23 against the scenario sweep (live/measure_scores.py):
#   quiet logins p50 0.34-0.39 (max 0.54) | bursts 0.57-0.66 |
#   new-machine 0.73-0.74 +dev | 3-strikes wrong-password -> BLOCK
BLOCK_THRESHOLD = float(os.environ.get("DEMO_BLOCK_AT", "0.75"))
FLAG_THRESHOLD = float(os.environ.get("DEMO_FLAG_AT", "0.65"))

LANL_FEATURES = [
    "dst_first", "src_first", "hour_ratio", "dst_prior_events",
    "fail_1h", "vel_1h", "hour_sin", "hour_cos",
]

IF_LOG_FEATURES = ["dst_prior_events", "fail_1h", "vel_1h"]

# Training distribution bounds (p01-p99 from feat.parquet)
# Clip features to these ranges so scoring matches training distribution
FEATURE_CLIP = {
    "hour_ratio": (0.0, 0.001),
    "dst_prior_events": (0, 600000),
    "vel_1h": (0, 10000),
    "fail_1h": (0, 3.0),
}

_if_model = None
_if_scaler = None
_if_min = None
_if_max = None
_if_range = None
_lgb_model = None
_models_loaded = False

# Per-user habit baseline refresh cadence (profiles learn from ALLOW only)
_PROFILE_TTL_S = 60.0
_last_profile_refresh: dict = {}


def _load_profile(con: duckdb.DuckDBPyConnection, user_id: int):
    row = con.execute("""
        SELECT typical_src_computers, typical_dst_computers,
               avg_events_per_hour, total_events
        FROM user_profile WHERE user_id = ?
    """, [user_id]).fetchone()
    if row is None:
        return None
    return {
        "typical_src": {c for c in (row[0] or "").split(",") if c and c != "?"},
        "typical_dst": {c for c in (row[1] or "").split(",") if c and c != "?"},
        "avg_per_hour": float(row[2] or 0.0),
        "total_events": int(row[3] or 0),
    }


def _deviation_signals(fd: dict, profile) -> tuple:
    """Per-user habit checks: does this event deviate from THIS user's norm?

    Returns (dev_points 0..3, human-readable reasons). Users with tiny or
    empty profiles are exempt (nothing to deviate from yet).
    """
    if profile is None or profile["total_events"] < 20:
        return 0, []
    points, reasons = 0, []
    if fd["dst_first"] and fd["dst_computer"] not in profile["typical_dst"]:
        points += 1
        reasons.append(f"first-ever destination {fd['dst_computer']} outside user's usual set")
    if fd["src_first"] and fd["src_computer"] not in profile["typical_src"]:
        points += 1
        reasons.append(f"first-ever source {fd['src_computer']} outside user's usual set")
    vel_floor = max(10.0 * profile["avg_per_hour"], 20.0)
    if fd["vel_1h"] > vel_floor:
        points += 1
        reasons.append(f"velocity {fd['vel_1h']}/h exceeds baseline floor {vel_floor:.0f}/h")
    if fd["fail_1h"] >= 2:
        points += 1
        reasons.append(f"{int(fd['fail_1h'])} authentication failures in the last hour")
    return points, reasons


def load_models():
    global _if_model, _if_scaler, _if_min, _if_max, _if_range
    global _lgb_model, _models_loaded

    if _models_loaded:
        return True

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
        print(f"loaded IF: roc_auc={art.get('roc_auc', '?')}")
    except Exception as exc:
        print(f"FATAL: failed to load IF model: {exc}")
        return False

    if not LGB_MODEL_PATH.exists():
        print(f"FATAL: LGB model not found: {LGB_MODEL_PATH}")
        return False
    try:
        art = joblib.load(LGB_MODEL_PATH)
        _lgb_model = art["model"]
        print(f"loaded LGB: roc_auc={art.get('roc_auc', '?')}")
    except Exception as exc:
        print(f"FATAL: failed to load LGB model: {exc}")
        return False

    _models_loaded = True
    print(f"thresholds: block>={BLOCK_THRESHOLD} flag>={FLAG_THRESHOLD}")
    return True


def lanl_feature_sql(user_src: str) -> str:
    """Compute 8 features matching the original training pipeline.

    Features computed from the user's event history:
      dst_first       1 if this is the first event to this destination
      src_first       1 if this is the first event from this source
      hour_ratio      probability mass at this hour for this user
      dst_prior_events cumulative count of prior visits to this destination
      fail_1h         failures in last 3600 seconds
      vel_1h          events in last 3600 seconds
      hour_sin        sin(hour / 24 * 2pi)
      hour_cos        cos(hour / 24 * 2pi)
    """
    return f"""
    WITH user_events AS (
        SELECT *,
               (time % 86400) / 3600.0 AS hour_f
        FROM {user_src}
    ),
    with_cumulative AS (
        SELECT *,
            -- cumulative destination count (prior visits to this dest by this user)
            COUNT(*) OVER (
                PARTITION BY user_id, dst_computer
                ORDER BY time, row_id
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS dst_prior_events,

            -- cumulative source count
            COUNT(*) OVER (
                PARTITION BY user_id, src_computer
                ORDER BY time, row_id
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS src_prior_events,

            -- total events per user up to this point
            COUNT(*) OVER (
                PARTITION BY user_id
                ORDER BY time, row_id
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS user_events_so_far,

            -- events at this hour for this user up to this point
            -- (partition by FLOAT hour to match training: src/lanl_features.sql:28)
            COUNT(*) OVER (
                PARTITION BY user_id, hour_f
                ORDER BY time, row_id
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS hour_events_so_far,

            -- events in last 3600 seconds (excluding current)
            COUNT(*) OVER (
                PARTITION BY user_id ORDER BY time
                RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING
            ) AS vel_1h,

            -- failures in last 3600 seconds
            COALESCE(SUM(CASE WHEN result = 'Fail' THEN 1 ELSE 0 END) OVER (
                PARTITION BY user_id ORDER BY time
                RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING
            ), 0) AS fail_1h

        FROM user_events
    )
    SELECT
        row_id, time, user_id, src_computer, dst_computer,
        auth_type, logon_type, orientation, result,
        hour_f,

        -- dst_first: 1 if no prior visits to this destination
        CASE WHEN COALESCE(dst_prior_events, 0) = 0 THEN 1 ELSE 0 END AS dst_first,

        -- src_first: 1 if no prior visits from this source
        CASE WHEN COALESCE(src_prior_events, 0) = 0 THEN 1 ELSE 0 END AS src_first,

        -- hour_ratio: events at this hour / total events for this user
        CASE WHEN user_events_so_far > 0
            THEN CAST(hour_events_so_far AS DOUBLE) / CAST(user_events_so_far AS DOUBLE)
            ELSE 0.0
        END AS hour_ratio,

        -- dst_prior_events: cumulative count (already computed above)
        COALESCE(dst_prior_events, 0) AS dst_prior_events,

        -- fail_1h: failures in last hour
        COALESCE(CAST(fail_1h AS DOUBLE), 0.0) AS fail_1h,

        -- vel_1h: events in last hour
        COALESCE(vel_1h, 0) AS vel_1h,

        -- hour_sin, hour_cos
        SIN(hour_f / 24.0 * 2 * {math.pi}) AS hour_sin,
        COS(hour_f / 24.0 * 2 * {math.pi}) AS hour_cos

    FROM with_cumulative
    """


def _compute_if_score(features: np.ndarray) -> float:
    """IF anomaly score: 0=normal, 1=anomalous.

    The model was trained on log1p-transformed features for:
      dst_prior_events (index 3), fail_1h (index 4), vel_1h (index 5)
    """
    X = features.copy()
    feat_idx = {name: i for i, name in enumerate(LANL_FEATURES)}
    for name in IF_LOG_FEATURES:
        X[feat_idx[name]] = np.log1p(X[feat_idx[name]])
    X_scaled = _if_scaler.transform(X.reshape(1, -1))
    raw = -_if_model.score_samples(X_scaled)[0]
    # score_samples returns negative; negate so higher = more anomalous
    # min/max were computed from negated scores during training
    norm = float(np.clip((raw - _if_min) / _if_range, 0, 1))
    # 0 = normal, 1 = anomalous (matches training: roc_auc(y, norm))
    return norm


def _compute_lgb_score(features: np.ndarray) -> float:
    """LGB anomaly score: 0=normal, 1=anomalous."""
    proba = _lgb_model.predict_proba(features.reshape(1, -1))[0]
    return float(proba[1])


def score_event(con: duckdb.DuckDBPyConnection, ev: dict) -> dict:
    """Score one LANL event against the user's stored history."""
    if not load_models():
        raise RuntimeError("Models not loaded")

    row_id = int(con.execute("SELECT COALESCE(MAX(row_id), 0) + 1 FROM events").fetchone()[0])

    ts = ev.get("ts")
    time_val = ev.get("time")
    if time_val is None and ts:
        time_val = int(ts.timestamp()) if hasattr(ts, "timestamp") else 0
    if time_val is None:
        time_val = int(time.time())
    time_val = int(time_val)

    # RANGE-based feature windows treat same-timestamp rows as peers and
    # exclude them from each other's windows — stagger collisions so rapid
    # bursts still see their predecessors.
    user_max = con.execute(
        "SELECT COALESCE(MAX(time), 0) FROM events WHERE user_id = ?",
        [ev["user_id"]],
    ).fetchone()[0]
    if time_val <= user_max:
        time_val = user_max + 1

    con.execute("""
        INSERT INTO events (row_id, ts, time, user_id, src_computer, dst_computer,
            auth_type, logon_type, orientation, result, decision)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    """, (row_id, ts, time_val, ev["user_id"], ev["src_computer"], ev["dst_computer"],
          ev.get("auth_type"), ev.get("logon_type"), ev.get("orientation"),
          ev.get("result", "Success")))

    user_src = f"""
        (SELECT row_id, time, user_id, src_computer, dst_computer,
                auth_type, logon_type, orientation, result
         FROM events WHERE user_id = {ev['user_id']})
    """
    feat_row = con.execute(f"""
        SELECT * FROM ({lanl_feature_sql(user_src)})
        WHERE row_id = {row_id}
    """).fetchdf().iloc[0]

    features = np.array([float(feat_row[f]) for f in LANL_FEATURES], dtype=np.float32)
    # Keep the clipped values for storage so what the dashboard shows is
    # exactly what the models scored.
    clipped = {}
    for i, fname in enumerate(LANL_FEATURES):
        if fname in FEATURE_CLIP:
            lo, hi = FEATURE_CLIP[fname]
            features[i] = np.clip(features[i], lo, hi)
        clipped[fname] = float(features[i])
    if_score = _compute_if_score(features)
    lgb_score = _compute_lgb_score(features)

    # Habit-deviation signal (per-user baseline), fused as a small booster:
    #   effective = if_score + 0.10 * min(dev_points, 3)   (max +0.30)
    profile = _load_profile(con, ev["user_id"])
    fd = {
        "dst_computer": ev["dst_computer"], "src_computer": ev["src_computer"],
        "dst_first": int(feat_row["dst_first"]), "src_first": int(feat_row["src_first"]),
        "vel_1h": int(feat_row["vel_1h"]), "fail_1h": float(feat_row["fail_1h"]),
    }
    dev_points, dev_reasons = _deviation_signals(fd, profile)
    combined = if_score + 0.10 * min(dev_points, 3)

    if combined >= BLOCK_THRESHOLD:
        decision, level = "block", "critical"
    elif combined >= FLAG_THRESHOLD:
        decision, level = "flag", "high"
    else:
        decision, level = "allow", "low"
    reasons = "; ".join(filter(None, [
        f"if={if_score:.3f}", f"dev={dev_points}",
        *dev_reasons,
    ]))

    con.execute("""
        UPDATE events SET dst_first=?, src_first=?, hour_ratio=?, dst_prior_events=?,
            fail_1h=?, vel_1h=?, hour_sin=?, hour_cos=?,
            lgb_score=?, if_score=?, combined_score=?, risk_level=?, reasons=?, decision=?,
            dev_points=?, dev_reasons=?
        WHERE row_id=?
    """, (int(feat_row["dst_first"]), int(feat_row["src_first"]),
          clipped["hour_ratio"], int(feat_row["dst_prior_events"]),
          clipped["fail_1h"], int(clipped["vel_1h"]),
          clipped["hour_sin"], clipped["hour_cos"],
          round(lgb_score, 6), round(if_score, 6), round(combined, 6),
          level, reasons, decision, dev_points, "; ".join(dev_reasons), row_id))

    if decision in ("block", "flag"):
        alert_id = int(con.execute("SELECT COALESCE(MAX(alert_id), 0) + 1 FROM alerts").fetchone()[0])
        con.execute("""
            INSERT INTO alerts (alert_id, event_id, user_id, ts, level,
                combined_score, reasons, decision)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (alert_id, row_id, ev["user_id"], ts, level,
              round(combined, 6), reasons, decision))
    elif decision == "allow":
        # Profiles learn from benign traffic only; refresh on a TTL cadence.
        now_s = time.time()
        if now_s - _last_profile_refresh.get(ev["user_id"], 0.0) > _PROFILE_TTL_S:
            import db as _db
            _db.refresh_profile(con, ev["user_id"])
            _last_profile_refresh[ev["user_id"]] = now_s

    return {
        "row_id": row_id, "user_id": ev["user_id"], "ts": str(ts),
        "src_computer": ev["src_computer"], "dst_computer": ev["dst_computer"],
        "auth_type": ev.get("auth_type"), "result": ev.get("result", "Success"),
        "lgb_score": round(lgb_score, 6), "if_score": round(if_score, 6),
        "combined_score": round(combined, 6),
        "dev_points": dev_points,
        "dev_reasons": "; ".join(dev_reasons),
        "risk_level": level, "reasons": reasons, "decision": decision,
        "features": {f: float(feat_row[f]) for f in LANL_FEATURES},
    }
