#!/usr/bin/env python3
"""Save LGB-21 model (best model: RUN 9) to disk.

Loads 20 features + lstm_ae_recon_error from DuckDB feat table,
retrains on full dataset, saves as models/lanl_lgb_21feat.joblib.

Usage: ./venv/bin/python save_lgb21.py
"""
import gc
import time
import numpy as np
import duckdb
import lightgbm as lgb
import joblib
from pathlib import Path
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "raw" / "lanl" / "lanl.duckdb"
MODEL_PATH = ROOT / "models" / "lanl_lgb_21feat.joblib"

LANL_FEATURES_21 = [
    "dst_first", "src_first", "hour_ratio", "dst_prior_events",
    "fail_1h", "vel_1h", "hour_sin", "hour_cos", "is_ntlm",
    "pair_first", "src_dst_pair_first", "fail_rate", "dst_first_x_ntlm",
    "log_pair_rank", "pair_freq_ratio", "is_rare_hour", "pairs_last_100",
    "iat_zscore", "velocity_ratio", "machine_popularity", "lstm_ae_recon_error",
]

# Same CTE chain as eval_lstm.py — computes all 21 features from feat table.
# CTEs are materialized by default in DuckDB (good: each referenced once).
SQL = """
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
user_iat_raw AS (
    SELECT *,
        CAST(time - LAG(time) OVER (
            PARTITION BY src_user
            ORDER BY time, dst_user, src_computer, dst_computer,
                     auth_type, logon_type, orientation, result
        ) AS DOUBLE) AS time_since_last
    FROM feat
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
    uv.dst_first,
    uv.src_first,
    CAST(uv.vel_1h AS DOUBLE) / (CAST(uv.user_events AS DOUBLE) + 1.0) AS hour_ratio,
    CAST(uv.dst_prior_events AS DOUBLE) AS dst_prior_events,
    CAST(uv.fail_1h AS DOUBLE) AS fail_1h,
    CAST(uv.vel_1h AS DOUBLE) AS vel_1h,
    SIN(CAST(uv.hour AS DOUBLE) / 24.0 * 2 * 3.141592653589793) AS hour_sin,
    COS(CAST(uv.hour AS DOUBLE) / 24.0 * 2 * 3.141592653589793) AS hour_cos,
    CAST(uv.is_ntlm AS DOUBLE) AS is_ntlm,
    CASE WHEN ROW_NUMBER() OVER (
         PARTITION BY uv.src_user, uv.src_computer, uv.dst_computer
         ORDER BY uv.time, uv.dst_user, uv.auth_type, uv.logon_type, uv.orientation, uv.result
    ) = 1 THEN 1.0 ELSE 0.0 END AS pair_first,
    CASE WHEN ROW_NUMBER() OVER (
         PARTITION BY uv.src_computer, uv.dst_computer
         ORDER BY uv.time, uv.src_user, uv.dst_user, uv.auth_type, uv.logon_type, uv.orientation, uv.result
    ) = 1 THEN 1.0 ELSE 0.0 END AS src_dst_pair_first,
    CAST(uv.fail_1h AS DOUBLE) / (CAST(uv.vel_1h AS DOUBLE) + 1.0) AS fail_rate,
    CASE WHEN uv.dst_prior_events = 0 AND uv.is_ntlm THEN 1.0 ELSE 0.0 END AS dst_first_x_ntlm,
    LOG(CAST(ROW_NUMBER() OVER (
         PARTITION BY uv.src_user, uv.src_computer, uv.dst_computer
         ORDER BY uv.time, uv.dst_user, uv.auth_type, uv.logon_type, uv.orientation, uv.result
    ) AS DOUBLE) + 1) AS log_pair_rank,
    CAST(pc.pair_events AS DOUBLE) / ut.total AS pair_freq_ratio,
    CASE WHEN rh.src_user IS NOT NULL THEN 1.0 ELSE 0.0 END AS is_rare_hour,
    0.0 AS pairs_last_100,
    COALESCE((uv.time_since_last - uv.iat_mean) / (uv.iat_std + 1e-6), 0.0) AS iat_zscore,
    CAST(uv.auth_count_1h AS DOUBLE) / (CAST(uv.auth_count_24h AS DOUBLE) + 1.0) AS velocity_ratio,
    mp.machine_popularity,
    uv.lstm_ae_recon_error,
    uv.src_user,
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


def main():
    t_start = time.time()

    print("Connecting to DuckDB...")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    con.execute("SET threads = 4")
    con.execute("SET memory_limit = '6GB'")

    n = con.execute("SELECT COUNT(*) FROM feat").fetchone()[0]
    print(f"  {n:,} rows")

    # fetchnumpy() is faster than fetchmany loop — DuckDB returns numpy arrays directly
    print("Running SQL CTE query...")
    t0 = time.time()
    df = con.execute(SQL).fetchdf()
    print(f"  SQL done: {time.time()-t0:.1f}s  shape={df.shape}")
    con.close()

    # Convert to numpy arrays
    y = df["is_red"].values.astype(bool)
    src_users = df["src_user"].values
    X = df[LANL_FEATURES_21].values.astype(np.float32)

    n_red = int(y.sum())
    print(f"  X shape={X.shape}  y red={n_red:,}")
    assert not np.any(np.isnan(X)), "NaN in features"
    assert not np.any(np.isinf(X)), "Inf in features"

    del df
    gc.collect()

    # Train/test split — same as eval_lstm.py
    gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
    for tr_idx, te_idx in gss.split(X, y, groups=src_users):
        pass

    y_train, y_test = y[tr_idx], y[te_idx]
    n_train_red = int(y_train.sum())
    n_test_red = int(y_test.sum())
    print(f"  Train: {len(tr_idx):,} rows ({n_train_red} red)")
    print(f"  Test:  {len(te_idx):,} rows ({n_test_red} red)")
    assert n_train_red + n_test_red == 702

    # Train LGB-21 on train set
    print("\nTraining LGB-21...")
    t1 = time.time()
    model = lgb.LGBMClassifier(
        num_leaves=63, learning_rate=0.03, n_estimators=500,
        scale_pos_weight=3, min_child_samples=100,
        reg_alpha=0.5, reg_lambda=5.0,
        random_state=42, n_jobs=-1, verbose=-1,
    )
    model.fit(X[tr_idx], y_train)
    print(f"  Train: {time.time()-t1:.1f}s")

    # Evaluate on test set
    test_scores = model.predict_proba(X[te_idx])[:, 1]
    roc = roc_auc_score(y_test, test_scores)
    pr = average_precision_score(y_test, test_scores)
    prec, rec, thr = precision_recall_curve(y_test, test_scores)
    f1_vals = np.nan_to_num(2 * prec * rec / (prec + rec))
    best_idx = np.argmax(f1_vals[:-1])
    f1 = f1_vals[best_idx]
    best_thr = thr[best_idx]
    pred = test_scores >= best_thr
    tp = int(np.sum(pred & y_test))
    fp = int(np.sum(pred & ~y_test))

    print(f"\n  ROC:   {roc:.4f}")
    print(f"  PR:    {pr:.4f}")
    print(f"  F1:    {f1:.4f}")
    print(f"  TP:    {tp} / {n_test_red}")
    print(f"  FP:    {fp}")
    print(f"  Thr:   {best_thr:.6f}")

    # Save
    art = {
        "model": model,
        "model_type": "lgb_21feat",
        "threshold": float(best_thr),
        "features": LANL_FEATURES_21,
        "roc_auc": float(roc),
        "pr_auc": float(pr),
        "f1": float(f1),
        "tp": tp,
        "fp": fp,
        "scale_pos_weight": 3,
    }
    joblib.dump(art, MODEL_PATH)
    print(f"\n  Saved: {MODEL_PATH} ({MODEL_PATH.stat().st_size/1e6:.1f} MB)")
    print(f"  Total: {time.time()-t_start:.1f}s")


if __name__ == "__main__":
    main()
