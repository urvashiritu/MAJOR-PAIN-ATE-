"""Precompute LGB scores to parquet (run once).

Uses the same mega-SQL as exp2.py training. DuckDB computes all features
except pairs_last_100 (computed in Python). Then predict + write parquet.
"""
import os
import sys
import time
import gc
import joblib
import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from db import FEATURE_COLS, SCORES_PARQUET

LANL_DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw', 'lanl', 'lanl.duckdb')

SCORING_SQL = """
WITH user_totals AS (
    SELECT src_user, COUNT(*) AS total FROM feat GROUP BY src_user
),
pair_counts AS (
    SELECT src_user, src_computer, dst_computer, COUNT(*) AS pair_events
    FROM feat GROUP BY src_user, src_computer, dst_computer
),
hour_dist AS (
    SELECT src_user, hour, COUNT(*) AS cnt,
        CUME_DIST() OVER (PARTITION BY src_user ORDER BY COUNT(*) ASC) AS cume
    FROM feat WHERE is_red = FALSE
    GROUP BY src_user, hour
),
rare_hours AS (
    SELECT src_user, hour FROM hour_dist WHERE cume <= 0.2
),
pair_intervals AS (
    SELECT *,
        CAST(time - LAG(time) OVER (
            PARTITION BY src_user, src_computer, dst_computer
            ORDER BY time, dst_user, auth_type, logon_type, orientation, result
        ) AS DOUBLE) AS pair_interval
    FROM feat
),
pair_with_avg AS (
    SELECT *,
        AVG(pair_interval) OVER (
            PARTITION BY src_user, src_computer, dst_computer
        ) AS user_avg_pair_interval
    FROM pair_intervals
),
user_iat_raw AS (
    SELECT *,
        CAST(time - LAG(time) OVER (
            PARTITION BY src_user
            ORDER BY time, dst_user, src_computer, dst_computer,
                     auth_type, logon_type, orientation, result
        ) AS DOUBLE) AS time_since_last
    FROM pair_with_avg
),
user_iat_rolling AS (
    SELECT *,
        AVG(time_since_last) OVER (
            PARTITION BY src_user
            ORDER BY time, dst_user, src_computer, dst_computer,
                     auth_type, logon_type, orientation, result
            ROWS BETWEEN 100 PRECEDING AND 1 PRECEDING
        ) AS iat_mean,
        STDDEV_SAMP(time_since_last) OVER (
            PARTITION BY src_user
            ORDER BY time, dst_user, src_computer, dst_computer,
                     auth_type, logon_type, orientation, result
            ROWS BETWEEN 100 PRECEDING AND 1 PRECEDING
        ) AS iat_std
    FROM user_iat_raw
),
user_velocity AS (
    SELECT *,
        COUNT(*) OVER (
            PARTITION BY src_user ORDER BY time
            RANGE BETWEEN 3600 PRECEDING AND CURRENT ROW
        ) AS auth_count_1h,
        COUNT(*) OVER (
            PARTITION BY src_user ORDER BY time
            RANGE BETWEEN 86400 PRECEDING AND CURRENT ROW
        ) AS auth_count_24h
    FROM user_iat_rolling
),
machine_pop AS (
    SELECT dst_computer, COUNT(DISTINCT src_user) AS machine_popularity
    FROM feat GROUP BY dst_computer
)
SELECT
    uv.dst_first, uv.src_first,
    CAST(uv.hour_events AS DOUBLE) / CAST(uv.user_events AS DOUBLE) AS hour_ratio,
    CAST(uv.dst_prior_events AS BIGINT) AS dst_prior_events,
    CAST(uv.fail_1h AS BIGINT) AS fail_1h,
    CAST(uv.vel_1h AS BIGINT) AS vel_1h,
    SIN(CAST(uv.hour AS DOUBLE) / 24.0 * 2.0 * 3.141592653589793) AS hour_sin,
    COS(CAST(uv.hour AS DOUBLE) / 24.0 * 2.0 * 3.141592653589793) AS hour_cos,
    CASE WHEN uv.is_ntlm THEN 1.0 ELSE 0.0 END AS is_ntlm,
    CASE WHEN ROW_NUMBER() OVER (PARTITION BY uv.src_user, uv.src_computer, uv.dst_computer
        ORDER BY uv.time, uv.dst_user, uv.auth_type, uv.logon_type, uv.orientation, uv.result) = 1
        THEN 1.0 ELSE 0.0 END AS pair_first,
    CASE WHEN ROW_NUMBER() OVER (PARTITION BY uv.src_computer, uv.dst_computer
        ORDER BY uv.time, uv.src_user, uv.dst_user, uv.auth_type, uv.logon_type, uv.orientation, uv.result) = 1
        THEN 1.0 ELSE 0.0 END AS src_dst_pair_first,
    CAST(uv.fail_1h AS DOUBLE) / (CAST(uv.vel_1h AS DOUBLE) + 1.0) AS fail_rate,
    CASE WHEN uv.dst_first = 1 AND uv.is_ntlm THEN 1.0 ELSE 0.0 END AS dst_first_x_ntlm,
    LOG(CAST(ROW_NUMBER() OVER (PARTITION BY uv.src_user, uv.src_computer, uv.dst_computer
        ORDER BY uv.time, uv.dst_user, uv.auth_type, uv.logon_type, uv.orientation, uv.result) AS DOUBLE) + 1) AS log_pair_rank,
    CAST(pc.pair_events AS DOUBLE) / ut.total AS pair_freq_ratio,
    CASE WHEN rh.src_user IS NOT NULL THEN 1.0 ELSE 0.0 END AS is_rare_hour,
    0.0 AS pairs_last_100,
    COALESCE((uv.time_since_last - uv.iat_mean) / (uv.iat_std + 1e-6), 0.0) AS iat_zscore,
    CAST(uv.auth_count_1h AS DOUBLE) / (CAST(uv.auth_count_24h AS DOUBLE) + 1.0) AS velocity_ratio,
    mp.machine_popularity,
    uv.lstm_ae_recon_error,
    uv.time,
    uv.hour,
    uv.src_user,
    uv.dst_user,
    uv.src_computer,
    uv.dst_computer,
    uv.is_red
FROM user_velocity uv
JOIN user_totals ut ON uv.src_user = ut.src_user
JOIN pair_counts pc ON uv.src_user = pc.src_user
    AND uv.src_computer = pc.src_computer
    AND uv.dst_computer = pc.dst_computer
JOIN machine_pop mp ON uv.dst_computer = mp.dst_computer
LEFT JOIN rare_hours rh ON uv.src_user = rh.src_user AND uv.hour = rh.hour
ORDER BY uv.time, uv.src_user, uv.dst_user, uv.src_computer, uv.dst_computer,
         uv.auth_type, uv.logon_type, uv.orientation, uv.result
"""


def compute_pairs_last_100(src_users, dst_computers, n):
    """Sliding window count of distinct dst_computers per user (last 100 events)."""
    t0 = time.time()
    pairs_last = np.zeros(n, dtype=np.float32)
    change_mask = np.zeros(n, dtype=bool)
    change_mask[0] = True
    change_mask[1:] = src_users[1:] != src_users[:-1]
    change_points = np.where(change_mask)[0]
    total_users = len(change_points)
    user_starts = change_points
    user_ends = np.append(change_points[1:], n)
    for i in range(total_users):
        s, e = user_starts[i], user_ends[i]
        u_dsts = dst_computers[s:e]
        n_u = e - s
        if n_u <= 100:
            for j in range(n_u):
                pairs_last[s + j] = len(set(u_dsts[max(0, j-99):j+1]))
        else:
            se = set()
            for j in range(n_u):
                se.add(u_dsts[j])
                if j >= 100:
                    se.discard(u_dsts[j - 100])
                pairs_last[s + j] = len(se)
        if (i + 1) % 200 == 0 or i + 1 == total_users:
            print(f"    {i+1}/{total_users} users")
    print(f"  pairs_last_100 in {time.time()-t0:.0f}s")
    return pairs_last


def precompute():
    t0 = time.time()

    print("STEP 1: run mega-SQL (DuckDB computes 20/21 features)")
    t1 = time.time()
    con = duckdb.connect(os.path.abspath(LANL_DB), read_only=True)
    result = con.execute(SCORING_SQL).fetchnumpy()
    con.close()
    gc.collect()

    n = len(result['time'])
    print(f"  {n:,} rows in {time.time()-t1:.0f}s")

    print("STEP 2: compute pairs_last_100 (Python)")
    result['pairs_last_100'] = compute_pairs_last_100(
        result['src_user'], result['dst_computer'], n)

    print("STEP 3: build X matrix")
    X = np.column_stack([result[k].astype(np.float32) for k in FEATURE_COLS])
    print(f"  X.shape={X.shape}  RAM={X.nbytes/1e6:.0f}MB")

    print("STEP 4: load model")
    model_path = os.path.join(os.path.dirname(__file__), '..', 'models', 'lanl_lgb_21feat.joblib')
    model_data = joblib.load(model_path)
    model = model_data['model']
    threshold = model_data['threshold']
    print(f"  threshold={threshold:.4f}")

    print("STEP 5: predict")
    t2 = time.time()
    chunk_size = 1_000_000
    scores = np.empty(n, dtype=np.float32)
    for i in range(0, n, chunk_size):
        chunk = X[i:i+chunk_size]
        scores[i:i+chunk_size] = model.predict_proba(chunk)[:, 1].astype(np.float32)
        if (i // chunk_size) % 5 == 0:
            print(f"    {i+chunk_size:>10,}/{n:,}")
    print(f"  predicted in {time.time()-t2:.0f}s")
    del X
    gc.collect()

    print("STEP 6: write parquet")
    os.makedirs(os.path.dirname(SCORES_PARQUET), exist_ok=True)
    out_df = pd.DataFrame({
        'anomaly_score': scores,
        'decision': np.where(scores > threshold, 'BLOCK',
                     np.where(scores > threshold * 0.7, 'FLAG', 'ALLOW')),
        'time': result['time'],
        'hour': result['hour'],
        'src_user': result['src_user'],
        'dst_user': result['dst_user'],
        'src_computer': result['src_computer'],
        'dst_computer': result['dst_computer'],
        'is_red': result['is_red'],
        'threshold': threshold,
    })
    out_df.to_parquet(SCORES_PARQUET, index=False)
    del result, scores, out_df
    gc.collect()
    print(f"  saved {os.path.getsize(SCORES_PARQUET)/1e6:.0f}MB")

    print(f"TOTAL: {time.time()-t0:.0f}s")


if __name__ == '__main__':
    precompute()
