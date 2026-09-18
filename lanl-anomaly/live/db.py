"""DuckDB connection + feature SQL + parquet caching."""
import os
import duckdb
import numpy as np

LANL_DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw', 'lanl', 'lanl.duckdb')
SCORES_PARQUET = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'lanl_scores.parquet')

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
    uv.time,
    uv.hour,
    uv.src_user,
    uv.dst_user,
    uv.src_computer,
    uv.dst_computer,
    uv.auth_type,
    uv.logon_type,
    uv.orientation,
    uv.result,
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

META_COLS = ['time', 'hour', 'src_user', 'dst_user', 'src_computer',
             'dst_computer', 'auth_type', 'logon_type', 'orientation', 'result', 'is_red']


def get_connection():
    """Return a DuckDB connection with lanl.duckdb attached."""
    con = duckdb.connect(':memory:')
    con.execute("SET memory_limit = '8GB'")
    con.execute("SET threads = 1")
    con.execute("SET preserve_insertion_order = false")
    con.execute("SET temp_directory = '/tmp/duckdb_spill'")
    os.makedirs('/tmp/duckdb_spill', exist_ok=True)
    con.execute(f"ATTACH '{os.path.abspath(LANL_DB)}' AS lanl (READ_ONLY)")
    return con


def build_features_table(con):
    """Create features table in DuckDB (takes ~5min with threads=1)."""
    con.execute("DROP TABLE IF EXISTS features")
    con.execute("CREATE TABLE features AS " + FEATURE_SQL)
    return con.execute("SELECT COUNT(*) FROM features").fetchone()[0]


def has_scores():
    """Check if precomputed scores parquet exists."""
    return os.path.exists(SCORES_PARQUET)


def get_scores_df(con):
    """Load precomputed scores from parquet."""
    return con.execute(f"SELECT * FROM read_parquet('{SCORES_PARQUET}')").fetchdf()
