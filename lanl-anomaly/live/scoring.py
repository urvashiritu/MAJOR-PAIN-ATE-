#!/usr/bin/env python3
"""LANL live scoring — LightGBM 20-feature model (Config E).

One event in, a decision out. The scoring path:
  1. Compute 20 LANL features from user's stored history
  2. LightGBM anomaly score (the decision model)
  3. Per-user habit deviation signals (displayed for reasoning, not scored)

Decision policy:
  - lgb_score >= BLOCK_THRESHOLD (default 0.50) -> block
  - lgb_score >= FLAG_THRESHOLD  (default 0.30) -> flag
  - otherwise                                   -> allow

Features (20 — matches exp2.py Config E):
  dst_first, src_first, hour_ratio, dst_prior_events, fail_1h,
  vel_1h, hour_sin, hour_cos, is_ntlm, pair_first,
  src_dst_pair_first, fail_rate, dst_first_x_ntlm, log_pair_rank,
  pair_freq_ratio, is_rare_hour, pairs_last_100,
  iat_zscore, velocity_ratio, machine_popularity
"""
import math
import os
import time
from pathlib import Path

import duckdb
import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

LGB_MODEL_PATH = ROOT / "models" / "lanl_lgb_20feat.joblib"

BLOCK_THRESHOLD = float(os.environ.get("DEMO_BLOCK_AT", "0.50"))
FLAG_THRESHOLD = float(os.environ.get("DEMO_FLAG_AT", "0.30"))

LANL_FEATURES = [
    "dst_first", "src_first", "hour_ratio", "dst_prior_events",
    "fail_1h", "vel_1h", "hour_sin", "hour_cos", "is_ntlm",
    "pair_first", "src_dst_pair_first", "fail_rate", "dst_first_x_ntlm",
    "log_pair_rank", "pair_freq_ratio", "is_rare_hour", "pairs_last_100",
    "iat_zscore", "velocity_ratio", "machine_popularity",
]

# Training distribution bounds (p01-p99 from feat.parquet)
FEATURE_CLIP = {
    "dst_prior_events": (0, 600000),
    "vel_1h": (0, 10000),
    "fail_1h": (0, 3.0),
}

_lgb_model = None
_models_loaded = False

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
    global _lgb_model, _models_loaded
    if _models_loaded:
        return True
    if not LGB_MODEL_PATH.exists():
        print(f"FATAL: LGB model not found: {LGB_MODEL_PATH}")
        return False
    try:
        art = joblib.load(LGB_MODEL_PATH)
        _lgb_model = art["model"]
        print(f"loaded LGB: roc_auc={art.get('roc_auc', '?')} features={len(art.get('features', []))}")
    except Exception as exc:
        print(f"FATAL: failed to load LGB model: {exc}")
        return False
    _models_loaded = True
    print(f"thresholds: block>={BLOCK_THRESHOLD} flag>={FLAG_THRESHOLD}")
    return True


def lanl_feature_sql(user_src: str) -> str:
    """Compute 20 features matching exp2.py Config E.

    CTE chain avoids nested window functions (DuckDB-illegal):
      user_events -> with_cumulative -> user_iat_raw -> user_iat_rolling
      -> user_base (all cumulative features baked in)
      -> final SELECT (derived + cross-user features)
    """
    return f"""
    WITH user_events AS (
        SELECT *,
               (time % 86400) / 3600.0 AS hour_f,
               CASE WHEN auth_type = 'NTLM' THEN 1 ELSE 0 END AS is_ntlm
        FROM {user_src}
    ),
    with_cumulative AS (
        SELECT *,
            COUNT(*) OVER (
                PARTITION BY user_id, dst_computer
                ORDER BY time, row_id
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS dst_prior_events,
            COUNT(*) OVER (
                PARTITION BY user_id, src_computer
                ORDER BY time, row_id
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS src_prior_events,
            COUNT(*) OVER (
                PARTITION BY user_id
                ORDER BY time, row_id
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS user_events_so_far,
            COUNT(*) OVER (
                PARTITION BY user_id, (time % 86400) / 3600.0
                ORDER BY time, row_id
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS hour_events_so_far,
            COUNT(*) OVER (
                PARTITION BY user_id ORDER BY time
                RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING
            ) AS vel_1h,
            COALESCE(SUM(CASE WHEN result = 'Fail' THEN 1 ELSE 0 END) OVER (
                PARTITION BY user_id ORDER BY time
                RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING
            ), 0) AS fail_1h,
            CASE WHEN ROW_NUMBER() OVER (
                PARTITION BY user_id, src_computer, dst_computer
                ORDER BY time, dst_computer, auth_type, logon_type, orientation, result
            ) = 1 THEN 1.0 ELSE 0.0 END AS pair_first,
            CASE WHEN ROW_NUMBER() OVER (
                PARTITION BY src_computer, dst_computer
                ORDER BY time, user_id, auth_type, logon_type, orientation, result
            ) = 1 THEN 1.0 ELSE 0.0 END AS src_dst_pair_first
        FROM user_events
    ),
    user_iat_raw AS (
        SELECT *,
            CAST(time - LAG(time) OVER (
                PARTITION BY user_id
                ORDER BY time, row_id
            ) AS DOUBLE) AS time_since_last
        FROM with_cumulative
    ),
    user_iat_rolling AS (
        SELECT *,
            AVG(time_since_last) OVER (
                PARTITION BY user_id
                ORDER BY time, row_id
                ROWS BETWEEN 100 PRECEDING AND 1 PRECEDING
            ) AS iat_mean,
            STDDEV_SAMP(time_since_last) OVER (
                PARTITION BY user_id
                ORDER BY time, row_id
                ROWS BETWEEN 100 PRECEDING AND 1 PRECEDING
            ) AS iat_std
        FROM user_iat_raw
    ),
    user_base AS (
        SELECT *,
            CAST(vel_1h AS DOUBLE) / (CAST(user_events_so_far AS DOUBLE) + 1.0) AS hour_ratio,
            CAST(vel_1h AS DOUBLE) / (CAST(fail_1h AS DOUBLE) + 1.0) AS fail_rate_calc,
            CASE WHEN dst_prior_events = 0 THEN 1 ELSE 0 END AS dst_first,
            CASE WHEN src_prior_events = 0 THEN 1 ELSE 0 END AS src_first,
            CASE WHEN dst_prior_events = 0 AND auth_type = 'NTLM' THEN 1.0 ELSE 0.0 END AS dst_first_x_ntlm
        FROM user_iat_rolling
    ),
    user_with_pair AS (
        SELECT ub.*,
            COUNT(*) OVER (
                PARTITION BY user_id, src_computer, dst_computer
                ORDER BY time, row_id
            ) AS pair_events,
            ROW_NUMBER() OVER (
                PARTITION BY user_id, src_computer, dst_computer
                ORDER BY time, dst_computer, auth_type, logon_type, orientation, result
            ) AS pair_rank_num
        FROM user_base ub
    ),
    user_final AS (
        SELECT uwp.*,
            CAST(pair_events AS DOUBLE) / CAST(user_events_so_far AS DOUBLE) AS pair_freq_ratio,
            CAST(pair_rank_num AS DOUBLE) AS pair_rank_raw
        FROM user_with_pair uwp
    ),
    user_with_iat AS (
        SELECT *,
            COALESCE((time_since_last - iat_mean) / (iat_std + 1e-6), 0.0) AS iat_zscore
        FROM user_final
    ),
    user_with_counts AS (
        SELECT *,
            COUNT(*) OVER (
                PARTITION BY user_id ORDER BY time
                RANGE BETWEEN 3600 PRECEDING AND CURRENT ROW
            ) AS auth_count_1h,
            COUNT(*) OVER (
                PARTITION BY user_id ORDER BY time
                RANGE BETWEEN 86400 PRECEDING AND CURRENT ROW
            ) AS auth_count_24h
        FROM user_with_iat
    ),
    user_with_vel AS (
        SELECT *,
            CAST(auth_count_1h AS DOUBLE) / (CAST(auth_count_24h AS DOUBLE) + 1.0) AS velocity_ratio
        FROM user_with_counts
    ),
    machine_pop AS (
        SELECT dst_computer, COUNT(DISTINCT src_user) AS machine_popularity
        FROM feat GROUP BY dst_computer
    )
    SELECT
        row_id, time, user_id, src_computer, dst_computer,
        auth_type, logon_type, orientation, result, hour_f,

        dst_first,
        src_first,
        hour_ratio,
        dst_prior_events,
        CAST(fail_1h AS DOUBLE) AS fail_1h,
        vel_1h,
        SIN(hour_f / 24.0 * 2 * {math.pi}) AS hour_sin,
        COS(hour_f / 24.0 * 2 * {math.pi}) AS hour_cos,
        is_ntlm,
        pair_first,
        src_dst_pair_first,
        fail_rate_calc AS fail_rate,
        dst_first_x_ntlm,
        LOG(pair_rank_raw + 1) AS log_pair_rank,
        pair_freq_ratio,
        0.0 AS is_rare_hour,
        0.0 AS pairs_last_100,
        iat_zscore,
        velocity_ratio,
        mp.machine_popularity

    FROM user_with_vel uwv
    JOIN machine_pop mp ON uwv.dst_computer = mp.dst_computer
    """


def _compute_lgb_score(features: np.ndarray) -> float:
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
    clipped = {}
    for i, fname in enumerate(LANL_FEATURES):
        if fname in FEATURE_CLIP:
            lo, hi = FEATURE_CLIP[fname]
            features[i] = np.clip(features[i], lo, hi)
        clipped[fname] = float(features[i])

    lgb_score = _compute_lgb_score(features)

    profile = _load_profile(con, ev["user_id"])
    fd = {
        "dst_computer": ev["dst_computer"], "src_computer": ev["src_computer"],
        "dst_first": int(feat_row["dst_first"]), "src_first": int(feat_row["src_first"]),
        "vel_1h": int(feat_row["vel_1h"]), "fail_1h": float(feat_row["fail_1h"]),
    }
    dev_points, dev_reasons = _deviation_signals(fd, profile)

    combined = lgb_score
    if combined >= BLOCK_THRESHOLD:
        decision, level = "block", "critical"
    elif combined >= FLAG_THRESHOLD:
        decision, level = "flag", "high"
    else:
        decision, level = "allow", "low"
    reasons = "; ".join(filter(None, [
        f"lgb={lgb_score:.3f}", f"dev={dev_points}",
        *dev_reasons,
    ]))

    con.execute("""
        UPDATE events SET dst_first=?, src_first=?, hour_ratio=?, dst_prior_events=?,
            fail_1h=?, vel_1h=?, hour_sin=?, hour_cos=?,
            is_ntlm=?, pair_first=?, src_dst_pair_first=?, fail_rate=?, dst_first_x_ntlm=?,
            log_pair_rank=?, pair_freq_ratio=?, is_rare_hour=?, pairs_last_100=?,
            iat_zscore=?, velocity_ratio=?, machine_popularity=?,
            lgb_score=?, combined_score=?, risk_level=?, reasons=?, decision=?,
            dev_points=?, dev_reasons=?
        WHERE row_id=?
    """, (int(feat_row["dst_first"]), int(feat_row["src_first"]),
          clipped["hour_ratio"], int(feat_row["dst_prior_events"]),
          clipped["fail_1h"], int(clipped["vel_1h"]),
          clipped["hour_sin"], clipped["hour_cos"],
          int(feat_row["is_ntlm"]), int(feat_row["pair_first"]),
          int(feat_row["src_dst_pair_first"]), clipped["fail_rate"],
          int(feat_row["dst_first_x_ntlm"]),
          clipped["log_pair_rank"], clipped["pair_freq_ratio"],
          clipped["is_rare_hour"], clipped["pairs_last_100"],
          clipped["iat_zscore"], clipped["velocity_ratio"], clipped["machine_popularity"],
          round(lgb_score, 6), round(combined, 6),
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
        now_s = time.time()
        if now_s - _last_profile_refresh.get(ev["user_id"], 0.0) > _PROFILE_TTL_S:
            import db as _db
            _db.refresh_profile(con, ev["user_id"])
            _last_profile_refresh[ev["user_id"]] = now_s

    return {
        "row_id": row_id, "user_id": ev["user_id"], "ts": str(ts),
        "src_computer": ev["src_computer"], "dst_computer": ev["dst_computer"],
        "auth_type": ev.get("auth_type"), "result": ev.get("result", "Success"),
        "lgb_score": round(lgb_score, 6),
        "combined_score": round(combined, 6),
        "dev_points": dev_points,
        "dev_reasons": "; ".join(dev_reasons),
        "risk_level": level, "reasons": reasons, "decision": decision,
        "features": {f: float(feat_row[f]) for f in LANL_FEATURES},
    }
