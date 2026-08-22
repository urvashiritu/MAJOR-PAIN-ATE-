#!/usr/bin/env python3
"""Retrain IF + LGB with scale-invariant features on LANL slice data.

Computes the same 10 features the live system uses, then trains both models.
Features use fixed time windows (3600s/300s) instead of cumulative counts.

Usage:
    python src/03_retrain_v2.py
"""
import math
import sys
from pathlib import Path

import duckdb
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score, precision_recall_curve, auc
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
SLICE = ROOT / "data" / "raw" / "lanl" / "slice.parquet"
REDTEAM = ROOT / "data" / "raw" / "lanl" / "redteam.parquet"
MODELS = ROOT / "models"
MODELS.mkdir(exist_ok=True)

FEATURES = [
    "dst_first", "src_first", "vel_1h", "fail_1h",
    "fail_rate_1h", "burst_ratio",
    "dst_diversity_1h", "src_diversity_1h",
    "hour_sin", "hour_cos",
]

LOG_FEATURES = ["vel_1h", "fail_1h", "dst_diversity_1h", "src_diversity_1h"]


def compute_features(con):
    print("Computing features over full slice...")
    pi = math.pi
    sql = f"""
    WITH base AS (
        SELECT *,
               (time % 86400) / 3600.0 AS hour_f,
               ROW_NUMBER() OVER (ORDER BY time) AS rn
        FROM read_parquet('{SLICE}')
    ),
    red AS (
        SELECT time, src_computer, dst_computer, user
        FROM read_parquet('{REDTEAM}')
    ),
    labeled AS (
        SELECT b.*,
            CASE WHEN r.user IS NOT NULL THEN 1 ELSE 0 END AS is_red
        FROM base b
        LEFT JOIN red r
            ON b.time = r.time
            AND b.src_computer = r.src_computer
            AND b.dst_computer = r.dst_computer
    ),
    windowed AS (
        SELECT *,
            CASE WHEN ROW_NUMBER() OVER (
                PARTITION BY src_user, dst_computer ORDER BY time, rn
            ) = 1 THEN 1 ELSE 0 END AS dst_first,
            CASE WHEN ROW_NUMBER() OVER (
                PARTITION BY src_user, src_computer ORDER BY time, rn
            ) = 1 THEN 1 ELSE 0 END AS src_first,
            COUNT(*) OVER (
                PARTITION BY src_user ORDER BY time
                RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING
            ) AS vel_1h,
            COALESCE(SUM(CASE WHEN result = 'Fail' THEN 1 ELSE 0 END) OVER (
                PARTITION BY src_user ORDER BY time
                RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING
            ), 0) AS fail_1h,
            COUNT(*) OVER (
                PARTITION BY src_user ORDER BY time
                RANGE BETWEEN 300 PRECEDING AND 1 PRECEDING
            ) AS vel_5m,
            COUNT(DISTINCT dst_computer) OVER (
                PARTITION BY src_user ORDER BY time
                RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING
            ) AS dst_diversity_1h,
            COUNT(DISTINCT src_computer) OVER (
                PARTITION BY src_user ORDER BY time
                RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING
            ) AS src_diversity_1h
        FROM labeled
    )
    SELECT
        rn, is_red,
        dst_first, src_first,
        COALESCE(vel_1h, 0) AS vel_1h,
        COALESCE(CAST(fail_1h AS DOUBLE), 0.0) AS fail_1h,
        CASE WHEN vel_1h > 0
            THEN COALESCE(CAST(fail_1h AS DOUBLE), 0.0) / CAST(vel_1h AS DOUBLE)
            ELSE 0.0
        END AS fail_rate_1h,
        CASE WHEN vel_1h > 0
            THEN CAST(COALESCE(vel_5m, 0) AS DOUBLE) / CAST(vel_1h AS DOUBLE)
            ELSE 0.0
        END AS burst_ratio,
        COALESCE(dst_diversity_1h, 1) AS dst_diversity_1h,
        COALESCE(src_diversity_1h, 1) AS src_diversity_1h,
        SIN(hour_f / 24.0 * 2 * {pi}) AS hour_sin,
        COS(hour_f / 24.0 * 2 * {pi}) AS hour_cos
    FROM windowed
    """
    print("Running feature SQL (this may take a few minutes)...")
    df = con.execute(sql).fetchdf()
    print(f"  {len(df)} rows, {df['is_red'].sum()} red events")
    return df


def train_if(X_train, y_train):
    print("\n--- Isolation Forest ---")
    n_red = int(y_train.sum())
    contamination = min(n_red / len(y_train), 0.01)
    print(f"  contamination: {contamination:.6f}")

    model = IsolationForest(
        n_estimators=200, max_samples=256,
        contamination=contamination, n_jobs=1, random_state=42,
    )
    X_log = X_train.copy()
    feat_idx = {name: i for i, name in enumerate(FEATURES)}
    for name in LOG_FEATURES:
        X_log[:, feat_idx[name]] = np.log1p(X_log[:, feat_idx[name]])

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_log)
    print("  Fitting...")
    model.fit(X_scaled)

    raw_scores = -model.score_samples(X_scaled)
    score_min = float(raw_scores.min())
    score_max = float(raw_scores.max())
    print(f"  raw scores: min={score_min:.4f} max={score_max:.4f}")
    return model, scaler, score_min, score_max


def train_lgb(X_train, y_train):
    print("\n--- LightGBM ---")
    n_red = int(y_train.sum())
    n_normal = len(y_train) - n_red
    spw = n_normal / max(n_red, 1)
    print(f"  scale_pos_weight: {spw:.0f}")

    try:
        import lightgbm as lgb
    except ImportError:
        print("  lightgbm not installed, skipping LGB")
        return None

    model = lgb.LGBMClassifier(
        n_estimators=200, num_leaves=31, learning_rate=0.05,
        scale_pos_weight=spw, n_jobs=-1, random_state=42, verbose=-1,
    )
    print("  Fitting...")
    model.fit(X_train, y_train)

    probs = model.predict_proba(X_train)[:, 1]
    print(f"  train ROC-AUC: {roc_auc_score(y_train, probs):.4f}")
    return model


def main():
    con = duckdb.connect()
    df = compute_features(con)

    X = df[FEATURES].values.astype(np.float32)
    y = df["is_red"].values.astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=42,
    )
    print(f"\nSplit: {len(X_train)} train ({y_train.sum()} red), "
          f"{len(X_test)} test ({y_test.sum()} red)")

    # Train IF
    if_model, if_scaler, score_min, score_max = train_if(X_train, y_train)

    # Evaluate IF
    X_test_log = X_test.copy()
    feat_idx = {name: i for i, name in enumerate(FEATURES)}
    for name in LOG_FEATURES:
        X_test_log[:, feat_idx[name]] = np.log1p(X_test_log[:, feat_idx[name]])
    X_test_scaled = if_scaler.transform(X_test_log)
    if_raw = -if_model.score_samples(X_test_scaled)
    if_norm = np.clip((if_raw - score_min) / (score_max - score_min), 0, 1)
    if_pred = 1.0 - if_norm
    if_roc = roc_auc_score(y_test, if_pred)
    print(f"\n  IF test ROC-AUC: {if_roc:.4f}")

    # Train LGB
    lgb_model = train_lgb(X_train, y_train)

    # Save IF
    if_art = {
        "model": if_model, "scaler": if_scaler,
        "features": FEATURES, "log_features": LOG_FEATURES,
        "score_min": score_min, "score_max": score_max,
        "roc_auc": if_roc,
        "train_rows": len(X_train), "test_rows": len(X_test),
    }
    if_path = MODELS / "lanl_if_v2.joblib"
    joblib.dump(if_art, if_path)
    print(f"\nSaved IF: {if_path}")

    # Save LGB
    if lgb_model:
        lgb_probs = lgb_model.predict_proba(X_test)[:, 1]
        lgb_roc = roc_auc_score(y_test, lgb_probs)
        print(f"  LGB test ROC-AUC: {lgb_roc:.4f}")

        combined = 0.5 * lgb_probs + 0.5 * if_pred
        comb_roc = roc_auc_score(y_test, combined)
        print(f"  Combined test ROC-AUC: {comb_roc:.4f}")

        lgb_art = {
            "model": lgb_model, "features": FEATURES,
            "roc_auc": lgb_roc,
            "train_rows": len(X_train), "test_rows": len(X_test),
        }
        lgb_path = MODELS / "lanl_lgb_v2.joblib"
        joblib.dump(lgb_art, lgb_path)
        print(f"Saved LGB: {lgb_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
