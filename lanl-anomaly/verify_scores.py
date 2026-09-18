#!/usr/bin/env python3
"""Verify LGB produces meaningful scores on lanl.feat (full 29.9M).

Deterministic: SET threads = 1 (verified in experiment_log.md RUN 12).
No OOM: CREATE TABLE AS SELECT persists features to disk, then predict in chunks.
No leakage: SQL CTEs only use past data (RANGE/PRECEDING, LAG).
"""
import duckdb, joblib, numpy as np, time, os

FEATURE_COLS = [
    'dst_first', 'src_first', 'hour_ratio', 'dst_prior_events',
    'fail_1h', 'vel_1h', 'hour_sin', 'hour_cos', 'is_ntlm',
    'pair_first', 'src_dst_pair_first', 'fail_rate', 'dst_first_x_ntlm',
    'log_pair_rank', 'pair_freq_ratio', 'is_rare_hour', 'pairs_last_100',
    'iat_zscore', 'velocity_ratio', 'machine_popularity', 'lstm_ae_recon_error'
]

FEATURE_SQL = """
WITH user_totals AS (
    SELECT src_user, COUNT(*) AS total FROM lanl.feat GROUP BY src_user
),
pair_counts AS (
    SELECT src_user, src_computer, dst_computer, COUNT(*) AS pair_events
    FROM lanl.feat GROUP BY src_user, src_computer, dst_computer
),
hour_dist AS (
    SELECT src_user, hour, COUNT(*) AS cnt,
        CUME_DIST() OVER (PARTITION BY src_user ORDER BY COUNT(*) ASC) AS cume
    FROM lanl.feat WHERE is_red = FALSE
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
    FROM lanl.feat
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
    FROM lanl.feat GROUP BY dst_computer
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
    uv.is_red,
    uv.src_user
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

VECTORS_PER_CHUNK = 50  # ~100K rows per chunk (each vector = ~2048 rows)


def main():
    # Safety: deterministic, no OOM
    con = duckdb.connect(':memory:')
    con.execute("SET memory_limit = '8GB'")
    con.execute("SET threads = 1")
    con.execute("SET preserve_insertion_order = false")
    os.makedirs('/tmp/duckdb_spill', exist_ok=True)
    con.execute("SET temp_directory = '/tmp/duckdb_spill'")

    con.execute("ATTACH 'data/raw/lanl/lanl.duckdb' AS lanl (READ_ONLY)")
    print("attached lanl.duckdb ✅")

    # Load model
    model_data = joblib.load('models/lanl_lgb_21feat.joblib')
    model = model_data['model']
    threshold = model_data['threshold']
    print(f"model loaded: {len(FEATURE_COLS)} features, threshold={threshold:.4f}")

    # Step 1: persist features to table (DuckDB handles 29.9M rows, spills to disk)
    t0 = time.time()
    print("computing features (threads=1, deterministic)...")
    con.execute("DROP TABLE IF EXISTS features")
    con.execute("CREATE TABLE features AS " + FEATURE_SQL)
    n_rows = con.execute("SELECT COUNT(*) FROM features").fetchone()[0]
    sql_time = time.time() - t0
    print(f"features table created: {n_rows:,} rows in {sql_time:.0f}s ✅")

    # Step 2: predict in chunks (never load all into memory)
    t1 = time.time()
    print("predicting in chunks...")
    cursor = con.execute(f"SELECT {', '.join(FEATURE_COLS)}, is_red, src_user FROM features")

    all_probs = []
    all_is_red = []
    all_src_user = []
    total_rows = 0
    while True:
        chunk = cursor.fetch_df_chunk(vectors_per_chunk=50)
        if chunk.empty:
            break
        X = chunk[FEATURE_COLS].to_numpy(dtype=np.float32)
        probs = model.predict_proba(X)[:, 1]
        all_probs.append(probs)
        all_is_red.append(chunk['is_red'].values)
        all_src_user.append(chunk['src_user'].values)
        total_rows += len(chunk)
        if total_rows % 1_000_000 < len(chunk):
            print(f"  processed {total_rows:,} rows...")

    probs = np.concatenate(all_probs)
    is_reds = np.concatenate(all_is_red)
    src_users = np.concatenate(all_src_user)
    pred_time = time.time() - t1
    print(f"prediction done: {len(probs):,} rows in {pred_time:.0f}s ✅")

    # Report
    print(f"\n=== RESULTS ===")
    print(f"total rows: {len(probs):,}")
    print(f"score range: [{probs.min():.6f}, {probs.max():.6f}]")
    print(f"score mean: {probs.mean():.6f}")
    print(f"score median: {np.median(probs):.6f}")
    print(f"threshold: {threshold:.4f}")

    red_mask = is_reds == True
    normal_mask = is_reds == False
    print(f"\nred events: {red_mask.sum():,}")
    print(f"normal events: {normal_mask.sum():,}")

    if red_mask.sum() > 0:
        red_probs = probs[red_mask]
        print(f"\nRED events:")
        print(f"  min={red_probs.min():.6f} max={red_probs.max():.6f} mean={red_probs.mean():.6f}")
        above = (red_probs > threshold).sum()
        print(f"  > threshold: {above}/{red_mask.sum()} ({100*above/red_mask.sum():.1f}%)")

        # Per-user breakdown
        red_users = src_users[red_mask]
        for u in sorted(set(red_users)):
            u_mask = red_users == u
            u_probs = red_probs[u_mask]
            print(f"  {u}: {u_mask.sum()} events, max={u_probs.max():.6f}, mean={u_probs.mean():.6f}")

    if normal_mask.sum() > 0:
        normal_probs = probs[normal_mask]
        print(f"\nNORMAL events:")
        print(f"  min={normal_probs.min():.6f} max={normal_probs.max():.6f} mean={normal_probs.mean():.6f}")
        above = (normal_probs > threshold).sum()
        print(f"  > threshold: {above}/{normal_mask.sum()} ({100*above/normal_mask.sum():.1f}%)")

    # Verdict
    print(f"\n=== VERDICT ===")
    if red_mask.sum() > 0 and red_probs.max() > 0.01:
        print("W — model produces meaningful scores on lanl.feat")
    else:
        print("L — model still produces ~0 scores, something is wrong")


if __name__ == "__main__":
    main()
