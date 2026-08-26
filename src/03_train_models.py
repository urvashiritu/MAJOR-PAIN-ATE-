#!/usr/bin/env python3
"""Train IF + LightGBM with honest evaluation.

Key fixes over previous version:
1. Hold out 1 entire attack IP for generalization test
2. Time-based train/test split (no temporal leakage)
3. PR-AUC as primary metric (ROC-AUC is misleading at 8% attack rate)
4. Baseline comparison: fail_1h > 8 threshold vs full model
5. Feature importance analysis
"""

import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    roc_auc_score, average_precision_score, f1_score,
    precision_score, recall_score, classification_report,
    confusion_matrix, precision_recall_curve,
)
import lightgbm as lgb

FEAT_PATH = Path("outputs/features_lanl.parquet")
MODEL_DIR = Path("models")

FEATURE_COLS = [
    "fail_1h", "vel_1h", "fail_24h", "vel_24h",
    "user_fail_rate", "src_ip_fail_rate",
    "hour_ratio", "hour_sin", "hour_cos",
]

# Hold out this IP for generalization test
HOLDOUT_IP = "10.20.99.103"  # lateral movement (hardest to detect)


def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(FEAT_PATH)
    print(f"Loaded {len(df)} rows, {df['is_attack'].sum()} attacks ({100*df['is_attack'].mean():.1f}%)")

    # ── Split: hold out 1 attack IP entirely ──
    holdout_mask = df["src_ip"] == HOLDOUT_IP
    df_holdout = df[holdout_mask].copy()
    df_train_full = df[~holdout_mask].copy()
    print(f"\nHoldout IP: {HOLDOUT_IP}")
    print(f"  Holdout events: {len(df_holdout)} ({df_holdout['is_attack'].sum()} attacks)")
    print(f"  Train+val events: {len(df_train_full)} ({df_train_full['is_attack'].sum()} attacks)")

    # ── Time-based split on train_full: July 1-20 train, July 21-31 test ──
    # Use epoch_sec to split at day 20 boundary
    day_20_epoch = pd.Timestamp("2026-07-21").timestamp()
    time_train = df_train_full["ts"] < pd.Timestamp("2026-07-21")
    df_val = df_train_full[~time_train].copy()
    df_train = df_train_full[time_train].copy()

    print(f"\nTime-based split:")
    print(f"  Train (Jul 1-20):  {len(df_train)} rows, {df_train['is_attack'].sum()} attacks ({100*df_train['is_attack'].mean():.1f}%)")
    print(f"  Val (Jul 21-31):   {len(df_val)} rows, {df_val['is_attack'].sum()} attacks ({100*df_val['is_attack'].mean():.1f}%)")
    print(f"  Holdout ({HOLDOUT_IP}): {len(df_holdout)} rows, {df_holdout['is_attack'].sum()} attacks")

    X_train = df_train[FEATURE_COLS].values
    y_train = df_train["is_attack"].values
    X_val = df_val[FEATURE_COLS].values
    y_val = df_val["is_attack"].values
    X_holdout = df_holdout[FEATURE_COLS].values
    y_holdout = df_holdout["is_attack"].values

    # ── Baseline: fail_1h > 8 threshold ──
    print("\n" + "="*60)
    print("BASELINE: fail_1h > 8 threshold")
    print("="*60)
    for thresh in [5, 8, 10]:
        pred_val = (df_val["fail_1h"] > thresh).astype(int)
        pred_hold = (df_holdout["fail_1h"] > thresh).astype(int)
        p, r, f1 = precision_score(y_val, pred_val), recall_score(y_val, pred_val), f1_score(y_val, pred_val)
        pr_auc = average_precision_score(y_val, pred_val)
        print(f"  threshold={thresh}: Val F1={f1:.4f} P={p:.4f} R={r:.4f} PR-AUC={pr_auc:.4f}")
        p, r, f1 = precision_score(y_holdout, pred_hold), recall_score(y_holdout, pred_hold), f1_score(y_holdout, pred_hold)
        pr_auc = average_precision_score(y_holdout, pred_hold)
        print(f"             Holdout F1={f1:.4f} P={p:.4f} R={r:.4f} PR-AUC={pr_auc:.4f}")

    # ── Isolation Forest ──
    print("\n" + "="*60)
    print("Training Isolation Forest ...")
    print("="*60)
    if_model = IsolationForest(
        n_estimators=200,
        contamination=0.08,
        max_samples="auto",
        random_state=42,
        n_jobs=-1,
    )
    if_model.fit(X_train)

    if_val_raw = -if_model.decision_function(X_val)
    if_hold_raw = -if_model.decision_function(X_holdout)
    if_min, if_max = if_val_raw.min(), if_val_raw.max()
    if_val = (if_val_raw - if_min) / (if_max - if_min + 1e-10)
    if_hold = (if_hold_raw - if_min) / (if_max - if_min + 1e-10)

    print(f"  IF ROC-AUC (val):     {roc_auc_score(y_val, if_val):.4f}")
    print(f"  IF PR-AUC (val):      {average_precision_score(y_val, if_val):.4f}")
    print(f"  IF ROC-AUC (holdout): {roc_auc_score(y_holdout, if_hold):.4f}")
    print(f"  IF PR-AUC (holdout):  {average_precision_score(y_holdout, if_hold):.4f}")

    # ── LightGBM ──
    print("\n" + "="*60)
    print("Training LightGBM ...")
    print("="*60)
    lgb_train = lgb.Dataset(X_train, label=y_train, feature_name=FEATURE_COLS)
    lgb_val = lgb.Dataset(X_val, label=y_val, feature_name=FEATURE_COLS, reference=lgb_train)

    params = {
        "objective": "binary",
        "metric": "auc",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "max_depth": 8,
        "min_child_samples": 20,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "scale_pos_weight": (y_train == 0).sum() / max((y_train == 1).sum(), 1),
        "verbose": -1,
        "seed": 42,
    }

    lgb_model = lgb.train(
        params, lgb_train,
        num_boost_round=500,
        valid_sets=[lgb_val],
        callbacks=[lgb.log_evaluation(100)],
    )

    lgb_val_pred = lgb_model.predict(X_val)
    lgb_hold_pred = lgb_model.predict(X_holdout)

    print(f"  LGB ROC-AUC (val):     {roc_auc_score(y_val, lgb_val_pred):.4f}")
    print(f"  LGB PR-AUC (val):      {average_precision_score(y_val, lgb_val_pred):.4f}")
    print(f"  LGB ROC-AUC (holdout): {roc_auc_score(y_holdout, lgb_hold_pred):.4f}")
    print(f"  LGB PR-AUC (holdout):  {average_precision_score(y_holdout, lgb_hold_pred):.4f}")

    # ── Combined score ──
    print("\n" + "="*60)
    print("COMBINED: 0.5*IF + 0.5*LGB")
    print("="*60)
    combined_val = 0.5 * if_val + 0.5 * lgb_val_pred
    combined_hold = 0.5 * if_hold + 0.5 * lgb_hold_pred

    roc_val = roc_auc_score(y_val, combined_val)
    pr_val = average_precision_score(y_val, combined_val)
    roc_hold = roc_auc_score(y_holdout, combined_hold)
    pr_hold = average_precision_score(y_holdout, combined_hold)

    print(f"  Val ROC-AUC:     {roc_val:.4f}")
    print(f"  Val PR-AUC:      {pr_val:.4f}")
    print(f"  Holdout ROC-AUC: {roc_hold:.4f}")
    print(f"  Holdout PR-AUC:  {pr_hold:.4f}")

    # Find optimal threshold on validation set
    best_f1, best_thresh = 0, 0
    for t in np.arange(0.1, 0.9, 0.01):
        preds = (combined_val >= t).astype(int)
        f1 = f1_score(y_val, preds)
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = t

    print(f"\n  Best threshold (val): {best_thresh:.2f} (F1={best_f1:.4f})")

    # Evaluate on all three sets
    for name, X, y_true, combined in [("Val", X_val, y_val, combined_val),
                                       ("Holdout", X_holdout, y_holdout, combined_hold)]:
        y_pred = (combined >= best_thresh).astype(int)
        p = precision_score(y_true, y_pred)
        r = recall_score(y_true, y_pred)
        f1 = f1_score(y_true, y_pred)
        print(f"\n  {name} @ threshold={best_thresh:.2f}:")
        print(f"    F1={f1:.4f}  Precision={p:.4f}  Recall={r:.4f}")
        print(f"    Confusion: {confusion_matrix(y_true, y_pred).tolist()}")

    # ── Feature importance ──
    print("\n" + "="*60)
    print("FEATURE IMPORTANCE (LightGBM)")
    print("="*60)
    imp = lgb_model.feature_importance(importance_type="gain")
    imp_norm = imp / imp.sum()
    for fname, score in sorted(zip(FEATURE_COLS, imp_norm), key=lambda x: -x[1]):
        bar = "█" * int(score * 50)
        print(f"  {fname:20s}  {score:.3f}  {bar}")

    # ── Save models ──
    joblib.dump(if_model, MODEL_DIR / "multi_if.joblib")
    joblib.dump(lgb_model, MODEL_DIR / "multi_lgb.joblib")
    joblib.dump({
        "if_min": if_min, "if_max": if_max,
        "threshold": best_thresh,
        "features": FEATURE_COLS,
        "roc_auc_val": roc_val,
        "pr_auc_val": pr_val,
        "roc_auc_holdout": roc_hold,
        "pr_auc_holdout": pr_hold,
        "f1_val": best_f1,
        "holdout_ip": HOLDOUT_IP,
    }, MODEL_DIR / "multi_meta.joblib")

    print(f"\nSaved → {MODEL_DIR}/multi_if.joblib")
    print(f"Saved → {MODEL_DIR}/multi_lgb.joblib")
    print(f"Saved → {MODEL_DIR}/multi_meta.joblib")

    # ── Summary ──
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"  Val ROC-AUC:     {roc_val:.4f}  (was 0.9984)")
    print(f"  Val PR-AUC:      {pr_val:.4f}")
    print(f"  Holdout ROC-AUC: {roc_hold:.4f}")
    print(f"  Holdout PR-AUC:  {pr_hold:.4f}")
    print(f"  F1 (val):        {best_f1:.4f}")
    print(f"  Holdout IP:      {HOLDOUT_IP}")
    print(f"  Baseline (fail_1h>8): PR-AUC={average_precision_score(y_val, (df_val['fail_1h']>8).astype(int)):.4f}")


if __name__ == "__main__":
    main()
