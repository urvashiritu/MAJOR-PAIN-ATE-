#!/usr/bin/env python3
"""Retrain IF + LGB with scale-invariant features on LANL slice data.

Computes the same 10 features the live system uses, then trains both models.
Features use fixed time windows (3600s/300s) instead of cumulative counts.

Usage:
    cd lanl-anomaly && source ../venv/bin/activate && python src/03_retrain_v2.py
"""
import math
import os
import sys
import time
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

T0 = time.time()


def elapsed():
    s = int(time.time() - T0)
    m, s = divmod(s, 60)
    return f"[{m:02d}:{s:02d}]"


def get_rss_mb():
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except Exception:
        pass
    return 0


def header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_feature_stats(df):
    print(f"\n  Feature statistics (mean +/- std):")
    for feat in FEATURES:
        col = df[feat]
        mean = col.mean()
        std = col.std()
        extra = ""
        if feat == "dst_first":
            extra = f"  ({mean*100:.1f}% first-time dest)"
        elif feat == "src_first":
            extra = f"  ({mean*100:.1f}% first-time src)"
        elif feat == "fail_rate_1h":
            extra = f"  ({(col > 0).sum()} events with failures)"
        elif feat == "burst_ratio":
            extra = f"  ({(col > 0.5).sum()} bursty events)"
        elif feat == "dst_diversity_1h":
            extra = f"  (max={col.max():.0f})"
        elif feat == "src_diversity_1h":
            extra = f"  (max={col.max():.0f})"
        print(f"    {feat:<18s} {mean:>10.4f} +/- {std:<10.4f}{extra}")


def compute_features(con):
    """Compute all 10 scale-invariant features over the full slice."""
    pi = math.pi

    print(f"{elapsed()} Loading raw data...")
    print(f"{elapsed()}   Reading slice.parquet...")
    row_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{SLICE}')").fetchone()[0]
    print(f"{elapsed()}   -> {row_count:,} rows")
    print(f"{elapsed()}   Reading redteam.parquet...")
    red_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{REDTEAM}')").fetchone()[0]
    print(f"{elapsed()}   -> {red_count} red team events")
    print(f"{elapsed()}   Memory: {get_rss_mb():.0f} MB")

    print(f"\n{elapsed()} Phase 1: Building windowed CTE (this is the slow part)...")
    print(f"{elapsed()}   7 window functions over {row_count:,} rows")
    print(f"{elapsed()}   Progress = waiting for DuckDB...")

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

    t_start = time.time()
    df = con.execute(sql).fetchdf()
    t_sql = time.time() - t_start

    print(f"{elapsed()}   -> Done in {t_sql:.1f}s")
    print(f"{elapsed()}   -> {len(df):,} rows x {len(FEATURES)} features")
    print(f"{elapsed()}   Memory: {get_rss_mb():.0f} MB")

    n_red = int(df["is_red"].sum())
    print(f"\n{elapsed()} Phase 2: Label distribution")
    print(f"{elapsed()}   Normal:  {len(df) - n_red:,} ({(1 - n_red/len(df))*100:.4f}%)")
    print(f"{elapsed()}   Red:     {n_red} ({n_red/len(df)*100:.6f}%)")

    print_feature_stats(df)

    return df


def train_if(X_train, y_train):
    """Train Isolation Forest with verbose progress."""
    n_red = int(y_train.sum())
    contamination = min(n_red / len(y_train), 0.01)

    print(f"\n{elapsed()} [IF] Isolation Forest")
    print(f"{elapsed()}   contamination: {contamination:.6f}")
    print(f"{elapsed()}   log1p on: {', '.join(LOG_FEATURES)}")

    model = IsolationForest(
        n_estimators=200, max_samples=256,
        contamination=contamination, n_jobs=1, random_state=42,
    )

    X_log = X_train.copy()
    feat_idx = {name: i for i, name in enumerate(FEATURES)}
    for name in LOG_FEATURES:
        X_log[:, feat_idx[name]] = np.log1p(X_log[:, feat_idx[name]])

    print(f"{elapsed()}   StandardScaler fit_transform...")
    t0 = time.time()
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_log)
    print(f"{elapsed()}   -> done ({time.time()-t0:.1f}s)")

    print(f"{elapsed()}   Fitting 200 trees (max_samples=256)...")
    t0 = time.time()
    model.fit(X_scaled)
    t_fit = time.time() - t0
    print(f"{elapsed()}   -> Done in {t_fit:.1f}s")

    raw_scores = -model.score_samples(X_scaled)
    score_min = float(raw_scores.min())
    score_max = float(raw_scores.max())
    print(f"{elapsed()}   Training raw scores: [{score_min:.4f}, {score_max:.4f}]")
    print(f"{elapsed()}   Memory: {get_rss_mb():.0f} MB")

    return model, scaler, score_min, score_max


def train_lgb(X_train, y_train):
    """Train LightGBM with verbose progress."""
    n_red = int(y_train.sum())
    n_normal = len(y_train) - n_red
    spw = n_normal / max(n_red, 1)

    print(f"\n{elapsed()} [LGB] LightGBM")
    print(f"{elapsed()}   scale_pos_weight: {spw:.0f}")

    try:
        import lightgbm as lgb
    except ImportError:
        print(f"{elapsed()}   lightgbm not installed — SKIPPING LGB")
        return None

    model = lgb.LGBMClassifier(
        n_estimators=200, num_leaves=31, learning_rate=0.05,
        scale_pos_weight=spw, n_jobs=-1, random_state=42, verbose=-1,
    )

    print(f"{elapsed()}   Fitting 200 trees (lr=0.05, leaves=31)...")
    t0 = time.time()
    model.fit(X_train, y_train)
    t_fit = time.time() - t0
    print(f"{elapsed()}   -> Done in {t_fit:.1f}s")

    probs = model.predict_proba(X_train)[:, 1]
    train_roc = roc_auc_score(y_train, probs)
    print(f"{elapsed()}   Train ROC-AUC: {train_roc:.4f}")

    # Feature importances
    importances = model.feature_importances_
    indices = np.argsort(importances)[::-1]
    print(f"\n{elapsed()}   Top features by importance (gain):")
    for rank, idx in enumerate(indices[:5], 1):
        print(f"{elapsed()}     {rank}. {FEATURES[idx]:<18s} gain={importances[idx]:.0f}")

    print(f"{elapsed()}   Memory: {get_rss_mb():.0f} MB")
    return model


def evaluate_models(if_model, if_scaler, score_min, score_max, lgb_model, X_test, y_test):
    """Full evaluation with threshold sweep."""
    print(f"\n{elapsed()} Phase 6: Evaluating on test set ({len(y_test):,} rows, {int(y_test.sum())} red)...")

    # IF scores
    X_test_log = X_test.copy()
    feat_idx = {name: i for i, name in enumerate(FEATURES)}
    for name in LOG_FEATURES:
        X_test_log[:, feat_idx[name]] = np.log1p(X_test_log[:, feat_idx[name]])
    X_test_scaled = if_scaler.transform(X_test_log)
    if_raw = -if_model.score_samples(X_test_scaled)
    if_norm = np.clip((if_raw - score_min) / (score_max - score_min), 0, 1)
    if_pred = 1.0 - if_norm
    if_roc = roc_auc_score(y_test, if_pred)

    print(f"{elapsed()}   IF:      ROC-AUC = {if_roc:.4f}")

    # LGB scores
    if lgb_model:
        lgb_probs = lgb_model.predict_proba(X_test)[:, 1]
        lgb_roc = roc_auc_score(y_test, lgb_probs)
        print(f"{elapsed()}   LGB:     ROC-AUC = {lgb_roc:.4f}")

        combined = 0.5 * lgb_probs + 0.5 * if_pred
        comb_roc = roc_auc_score(y_test, combined)
        print(f"{elapsed()}   Combined: ROC-AUC = {comb_roc:.4f}")

        # Threshold sweep
        print(f"\n{elapsed()}   Threshold sweep:")
        print(f"{'':18s} {'threshold':>10s}  {'recall':>8s}  {'FPR':>8s}  {'precision':>10s}")
        print(f"{'':18s} {'-'*10}  {'-'*8}  {'-'*8}  {'-'*10}")

        precision, recall, thresholds = precision_recall_curve(y_test, combined)
        for target in [0.70, 0.80, 0.90, 0.95, 1.0]:
            mask = recall >= target
            if mask.any():
                idx = np.where(mask)[0][0]
                # Calculate FPR at this threshold
                thresh = thresholds[idx] if idx < len(thresholds) else 0
                fp = int(((combined >= thresh) & (y_test == 0)).sum())
                tn = int(((combined < thresh) & (y_test == 0)).sum())
                fpr = fp / max(fp + tn, 1)
                print(f"{'':18s} {thresh:>10.3f}  {recall[idx]*100:>7.1f}%  {fpr*100:>7.1f}%  {precision[idx]:>10.6f}")

        return if_roc, lgb_roc, comb_roc, if_pred, lgb_probs

    return if_roc, None, None, if_pred, None


def main():
    header("LANL Model Retrainer v2 — Scale-Invariant Features")
    print(f"{elapsed()} Root: {ROOT}")
    print(f"{elapsed()} Slice: {SLICE}")
    print(f"{elapsed()} Redteam: {REDTEAM}")
    print(f"{elapsed()} Models dir: {MODELS}")
    print(f"{elapsed()} Memory: {get_rss_mb():.0f} MB")

    con = duckdb.connect()

    # Phase 1-2: Feature engineering
    df = compute_features(con)

    X = df[FEATURES].values.astype(np.float32)
    y = df["is_red"].values.astype(int)

    # Phase 3: Split
    print(f"\n{elapsed()} Phase 3: Train/test split (70/30, stratified)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=42,
    )
    print(f"{elapsed()}   Train: {len(X_train):,} rows ({int(y_train.sum())} red)")
    print(f"{elapsed()}   Test:  {len(X_test):,} rows ({int(y_test.sum())} red)")

    # Phase 4-5: Training
    print(f"\n{elapsed()} Phase 4-5: Training models...")
    if_model, if_scaler, score_min, score_max = train_if(X_train, y_train)
    lgb_model = train_lgb(X_train, y_train)

    # Phase 6: Evaluation
    if_roc, lgb_roc, comb_roc, if_pred, lgb_probs = evaluate_models(
        if_model, if_scaler, score_min, score_max, lgb_model, X_test, y_test
    )

    # Save
    print(f"\n{elapsed()} Saving models...")
    if_art = {
        "model": if_model, "scaler": if_scaler,
        "features": FEATURES, "log_features": LOG_FEATURES,
        "score_min": score_min, "score_max": score_max,
        "roc_auc": if_roc,
        "train_rows": len(X_train), "test_rows": len(X_test),
    }
    if_path = MODELS / "lanl_if_v2.joblib"
    joblib.dump(if_art, if_path)
    if_size = os.path.getsize(if_path) / (1024 * 1024)
    print(f"{elapsed()}   IF:  {if_path}  ({if_size:.1f} MB)")

    if lgb_model:
        lgb_art = {
            "model": lgb_model, "features": FEATURES,
            "roc_auc": lgb_roc or 0,
            "train_rows": len(X_train), "test_rows": len(X_test),
        }
        lgb_path = MODELS / "lanl_lgb_v2.joblib"
        joblib.dump(lgb_art, lgb_path)
        lgb_size = os.path.getsize(lgb_path) / (1024 * 1024)
        print(f"{elapsed()}   LGB: {lgb_path}  ({lgb_size:.1f} MB)")

    total = time.time() - T0
    m, s = divmod(int(total), 60)
    print(f"\n{'='*60}")
    print(f"  DONE in {m}m {s}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
