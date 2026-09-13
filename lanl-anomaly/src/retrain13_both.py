#!/usr/bin/env python3
"""LANL 13-feature dual-model training: IF + LightGBM.

Correct split: GroupShuffleSplit on src_user (no leakage).
13 features: original 9 + pair_first, src_dst_pair_first, fail_rate, dst_first_x_ntlm.

LGB params: spw=3, num_leaves=63, n_estimators=500, min_child=100, alpha=0.5, lambda=5.0
IF params:  n_estimators=200, max_samples=256, normals-only, contamination=1e-7

Inner split carves validation slice for threshold selection (no test leakage).
C17693 evaluated as held-out test AFTER training.

Output:
  models/lanl_lgb_13feat.joblib
  models/lanl_if_13feat.joblib
  reports/retrain13_report.json
"""
import argparse
import gc
import json
import os
import time
import warnings
from pathlib import Path

import duckdb
import joblib
import lightgbm as lgb
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "raw" / "lanl" / "lanl.duckdb"
DEFAULT_MODEL_DIR = ROOT / "models"
DEFAULT_REPORT = ROOT / "reports" / "retrain13_report.json"

SEED = 42
HOLDOUT_ATTACKER = "C17693"

FEATURES_13 = [
    'dst_first', 'src_first', 'hour_ratio', 'dst_prior_events',
    'fail_1h', 'vel_1h', 'hour_sin', 'hour_cos', 'is_ntlm',
    'pair_first', 'src_dst_pair_first', 'fail_rate', 'dst_first_x_ntlm',
]

IF_LOG_FEATURES = ["dst_prior_events", "fail_1h", "vel_1h"]


def mem_msg(tag):
    if not HAS_PSUTIL:
        return f"[{tag}]"
    vm = psutil.virtual_memory()
    rss = psutil.Process(os.getpid()).memory_info().rss / (1024**3)
    avail = vm.available / (1024**3)
    return f"[{tag}] RAM {vm.percent:.0f}% avail {avail:.1f}G rss {rss:.1f}G"


def vprint(msg, verbose=True):
    if verbose:
        print(msg, flush=True)


def metrics_at(y_true, scores, threshold):
    pred = scores >= threshold
    tp = int(np.sum(pred & y_true))
    fp = int(np.sum(pred & ~y_true))
    fn = int(np.sum(~pred & y_true))
    tn = int(np.sum(~pred & ~y_true))
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision, "recall": recall, "f1": f1, "fpr": fpr}


def tune_threshold(y_true, scores):
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    with np.errstate(invalid="ignore", divide="ignore"):
        f1 = 2 * precision * recall / (precision + recall)
    f1 = np.nan_to_num(f1, nan=0.0)
    best = int(np.argmax(f1[:-1]))
    return float(thresholds[best])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--verbose", action="store_true", default=True)
    ap.add_argument("--no-verbose", dest="verbose", action="store_false")
    args = ap.parse_args()
    args.model_dir.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    vprint(f"=== LANL 13-Feature Training === {mem_msg('init')}", args.verbose)

    # ── 1. Load data with 13 features ──
    con = duckdb.connect(str(args.db))
    con.execute("SET threads=4")
    con.execute("SET memory_limit='4GB'")

    t0 = time.time()
    vprint(f"loading features ... {mem_msg('pre-load')}", args.verbose)
    sql = """
    SELECT dst_first, src_first, hour_events, user_events,
           CAST(dst_prior_events AS BIGINT) AS dst_prior_events,
           CAST(fail_1h AS BIGINT) AS fail_1h,
           CAST(vel_1h AS BIGINT) AS vel_1h,
           hour, is_red, src_computer, src_user,
           CASE WHEN ROW_NUMBER() OVER (
               PARTITION BY src_user, src_computer, dst_computer
               ORDER BY time, dst_user, auth_type, logon_type, orientation, result
           ) = 1 THEN 1.0 ELSE 0.0 END AS pair_first,
           CASE WHEN ROW_NUMBER() OVER (
               PARTITION BY src_computer, dst_computer
               ORDER BY time, src_user, dst_user, auth_type, logon_type, orientation, result
           ) = 1 THEN 1.0 ELSE 0.0 END AS src_dst_pair_first,
           CAST(fail_1h AS DOUBLE) / (CAST(vel_1h AS DOUBLE) + 1.0) AS fail_rate,
           CASE WHEN dst_first = 1 AND is_ntlm THEN 1.0 ELSE 0.0 END AS dst_first_x_ntlm,
           is_ntlm
    FROM feat
    ORDER BY time, src_user, dst_user, src_computer, dst_computer,
             auth_type, logon_type, orientation, result
    """
    result = con.execute(sql).fetchnumpy()
    con.close()
    t_load = time.time() - t0
    vprint(f"  loaded {len(result['is_red']):,} rows in {t_load:.1f}s {mem_msg('post-load')}", args.verbose)

    # ── 2. Build numpy arrays ──
    t1 = time.time()
    feat_keys = ['dst_first', 'src_first', 'hour_events', 'user_events',
                 'dst_prior_events', 'fail_1h', 'vel_1h', 'hour', 'is_ntlm']
    X_raw = np.column_stack([result[k].astype(np.float32) for k in feat_keys])
    y = result['is_red'].astype(bool)
    src_users = result['src_user']
    n = len(y)
    n_reds = int(y.sum())
    vprint(f"  X_raw {X_raw.shape} {X_raw.dtype} {X_raw.nbytes/1e9:.2f}G | "
           f"{n_reds:,} reds / {n:,} total {time.time()-t1:.1f}s {mem_msg('numpy')}", args.verbose)

    # ── 3. Derive 13 features ──
    t1 = time.time()
    X_13 = np.empty((n, 13), dtype=np.float32)
    X_13[:, 0] = X_raw[:, 0]  # dst_first
    X_13[:, 1] = X_raw[:, 1]  # src_first
    ue = np.maximum(X_raw[:, 3], 1)
    X_13[:, 2] = X_raw[:, 2] / ue  # hour_ratio
    X_13[:, 3] = X_raw[:, 4]  # dst_prior_events
    X_13[:, 4] = X_raw[:, 5]  # fail_1h
    X_13[:, 5] = X_raw[:, 6]  # vel_1h
    h_rad = X_raw[:, 7] / 24.0 * 2 * np.pi
    X_13[:, 6] = np.sin(h_rad)  # hour_sin
    X_13[:, 7] = np.cos(h_rad)  # hour_cos
    X_13[:, 8] = X_raw[:, 8]   # is_ntlm
    X_13[:, 9] = result['pair_first'].astype(np.float32)
    X_13[:, 10] = result['src_dst_pair_first'].astype(np.float32)
    X_13[:, 11] = result['fail_rate'].astype(np.float32)
    X_13[:, 12] = result['dst_first_x_ntlm'].astype(np.float32)
    vprint(f"  derived 13 features {time.time()-t1:.1f}s {mem_msg('derive')}", args.verbose)

    del X_raw, h_rad, ue, result
    gc.collect()

    # ── 4. Log-transformed copy for IF ──
    X_log = X_13.copy()
    X_log[:, 3] = np.log1p(X_log[:, 3])
    X_log[:, 4] = np.log1p(X_log[:, 4])
    X_log[:, 5] = np.log1p(X_log[:, 5])
    vprint(f"  log-transformed for IF {mem_msg('log')}", args.verbose)

    # ── 5. Outer split: GroupShuffleSplit on src_user (no leakage) ──
    t1 = time.time()
    holdout_mask = src_users == HOLDOUT_ATTACKER
    vprint(f"  C17693 holdout: {holdout_mask.sum():,} events, "
           f"{y[holdout_mask].sum():,} reds {mem_msg('holdout')}", args.verbose)

    gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=SEED)
    for tr_idx, te_idx in gss.split(X_13, y, groups=src_users):
        pass
    y_train, y_test = y[tr_idx], y[te_idx]
    src_users_train = src_users[tr_idx]
    vprint(f"  outer split: train {len(tr_idx):,} ({y_train.sum():,} red) / "
           f"test {len(te_idx):,} ({y_test.sum():,} red) "
           f"{time.time()-t1:.1f}s {mem_msg('split')}", args.verbose)

    # ── 6. Inner split: validation slice for threshold tuning ──
    t1 = time.time()
    gss_val = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=99)
    for trtr_local, val_local in gss_val.split(X_log[tr_idx], y_train, groups=src_users_train):
        pass
    trtr_idx = tr_idx[trtr_local]
    val_idx = tr_idx[val_local]
    y_trtr = y[trtr_idx]
    y_val = y[val_idx]
    vprint(f"  inner split: train-train {len(trtr_idx):,} ({y_trtr.sum():,} red) / "
           f"train-val {len(val_idx):,} ({y_val.sum():,} red) "
           f"{time.time()-t1:.1f}s {mem_msg('inner')}", args.verbose)

    # ── 7. LightGBM (13feat, spw=3) ──
    t1 = time.time()
    vprint(f"training LightGBM (13feat, spw=3) ... {mem_msg('pre-lgb')}", args.verbose)

    lgb_model = lgb.LGBMClassifier(
        num_leaves=63, learning_rate=0.03, n_estimators=500,
        scale_pos_weight=3, min_child_samples=100,
        reg_alpha=0.5, reg_lambda=5.0,
        random_state=SEED, n_jobs=1, verbose=-1,
    )
    lgb_model.fit(X_13[trtr_idx], y_trtr)
    t_lgb = time.time() - t1
    vprint(f"  LGB fit done {t_lgb:.1f}s {mem_msg('lgb-fit')}", args.verbose)

    # Threshold from validation
    lgb_val_scores = lgb_model.predict_proba(X_13[val_idx])[:, 1]
    lgb_thresh = tune_threshold(y_val, lgb_val_scores)
    lgb_val_m = metrics_at(y_val, lgb_val_scores, lgb_thresh)
    vprint(f"  LGB val: thr={lgb_thresh:.6f} TP={lgb_val_m['tp']} FP={lgb_val_m['fp']} "
           f"F1={lgb_val_m['f1']:.4f}", args.verbose)

    # Score full test set
    lgb_test_scores = lgb_model.predict_proba(X_13[te_idx])[:, 1]
    lgb_test_m = metrics_at(y_test, lgb_test_scores, lgb_thresh)
    lgb_roc = float(roc_auc_score(y_test, lgb_test_scores))
    lgb_pr = float(average_precision_score(y_test, lgb_test_scores))
    vprint(f"  LGB test: ROC={lgb_roc:.4f} PR-AUC={lgb_pr:.4f} "
           f"TP={lgb_test_m['tp']} FP={lgb_test_m['fp']} F1={lgb_test_m['f1']:.4f} "
           f"FPR={lgb_test_m['fpr']:.4f}", args.verbose)

    # Feature importance
    vprint(f"\n  LGB feature importance:", args.verbose)
    for fn, imp in sorted(zip(FEATURES_13, lgb_model.feature_importances_), key=lambda x: -x[1]):
        vprint(f"    {fn:<25} {imp:>5}", args.verbose)

    # Prob distribution
    atk_p = lgb_test_scores[y_test]
    norm_p = lgb_test_scores[~y_test]
    vprint(f"\n  LGB prob distribution:", args.verbose)
    vprint(f"    Attacks: min={atk_p.min():.4f} p25={np.percentile(atk_p,25):.4f} "
           f"p50={np.median(atk_p):.4f} p75={np.percentile(atk_p,75):.4f} max={atk_p.max():.4f}",
           args.verbose)
    vprint(f"    Normal:  min={norm_p.min():.6f} p50={np.median(norm_p):.6f} "
           f"p75={np.percentile(norm_p,75):.6f} max={norm_p.max():.4f}", args.verbose)

    # ── 8. Isolation Forest (13feat, normal-only) ──
    t1 = time.time()
    vprint(f"\ntraining IF (13feat, normal-only) ... {mem_msg('pre-if')}", args.verbose)

    trtr_normal_mask = ~y_trtr
    X_trtr_norm = X_log[trtr_idx][trtr_normal_mask]

    scaler = StandardScaler()
    X_trtr_scaled = scaler.fit_transform(X_trtr_norm)

    if_model = IsolationForest(
        n_estimators=200, contamination=1e-7,
        max_samples=256, n_jobs=1, random_state=SEED,
    )
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        if_model.fit(X_trtr_scaled)
    t_if = time.time() - t1
    vprint(f"  IF fit done {t_if:.1f}s {mem_msg('if-fit')}", args.verbose)

    # Score validation for threshold (negate so higher=anomalous)
    if_val_raw = -if_model.score_samples(scaler.transform(X_log[val_idx]))
    if_min = float(np.percentile(-if_model.score_samples(X_trtr_scaled), 1))
    if_max = float(np.percentile(-if_model.score_samples(X_trtr_scaled), 99))
    if_range = if_max - if_min if if_max > if_min else 1.0
    if_val_scores = (if_val_raw - if_min) / if_range
    if_thresh = tune_threshold(y_val, if_val_scores)
    if_val_m = metrics_at(y_val, if_val_scores, if_thresh)
    vprint(f"  IF val: thr={if_thresh:.6f} TP={if_val_m['tp']} FP={if_val_m['fp']} "
           f"F1={if_val_m['f1']:.4f}", args.verbose)

    # Score full test set
    if_test_raw = -if_model.score_samples(scaler.transform(X_log[te_idx]))
    if_test_scores = (if_test_raw - if_min) / if_range
    if_test_m = metrics_at(y_test, if_test_scores, if_thresh)
    if_roc = float(roc_auc_score(y_test, if_test_scores))
    if_pr = float(average_precision_score(y_test, if_test_scores))
    vprint(f"  IF test: ROC={if_roc:.4f} PR-AUC={if_pr:.4f} "
           f"TP={if_test_m['tp']} FP={if_test_m['fp']} F1={if_test_m['f1']:.4f} "
           f"FPR={if_test_m['fpr']:.4f}", args.verbose)

    # ── 9. Combined score ──
    combined_test = 0.5 * lgb_test_scores + 0.5 * if_test_scores
    comb_thresh = tune_threshold(y_val, 0.5 * lgb_val_scores + 0.5 * if_val_scores)
    comb_test_m = metrics_at(y_test, combined_test, comb_thresh)
    comb_roc = float(roc_auc_score(y_test, combined_test))
    comb_pr = float(average_precision_score(y_test, combined_test))
    vprint(f"  COMBINED: ROC={comb_roc:.4f} PR-AUC={comb_pr:.4f} "
           f"TP={comb_test_m['tp']} FP={comb_test_m['fp']} F1={comb_test_m['f1']:.4f} "
           f"FPR={comb_test_m['fpr']:.4f}", args.verbose)

    # ── 10. Overlap analysis ──
    vprint(f"\n{'='*70}", args.verbose)
    vprint("OVERLAP ANALYSIS", args.verbose)
    vprint(f"{'='*70}", args.verbose)

    red_mask = y_test
    lgb_caught = lgb_test_scores[red_mask] >= lgb_thresh
    if_caught = if_test_scores[red_mask] >= if_thresh

    both = int((lgb_caught & if_caught).sum())
    lgb_only = int((lgb_caught & ~if_caught).sum())
    if_only = int((if_caught & ~lgb_caught).sum())
    neither = int((~lgb_caught & ~if_caught).sum())
    union = lgb_only + if_only + both
    n_test_reds = int(red_mask.sum())

    vprint(f"  LGB catches:  {int(lgb_caught.sum()):>3} / {n_test_reds}", args.verbose)
    vprint(f"  IF catches:   {int(if_caught.sum()):>3} / {n_test_reds}", args.verbose)
    vprint(f"  Both:         {both:>3}", args.verbose)
    vprint(f"  LGB only:     {lgb_only:>3}", args.verbose)
    vprint(f"  IF only:      {if_only:>3}", args.verbose)
    vprint(f"  Neither:      {neither:>3}", args.verbose)
    vprint(f"  Union:        {union:>3}", args.verbose)

    # ── 11. Holdout analysis (C17693) ──
    vprint(f"\n{'='*70}", args.verbose)
    vprint(f"HOLDOUT {HOLDOUT_ATTACKER}", args.verbose)
    vprint(f"{'='*70}", args.verbose)

    if holdout_mask.sum() > 0:
        holdout_y = y[holdout_mask]
        holdout_lgb = lgb_model.predict_proba(X_13[holdout_mask])[:, 1]
        holdout_if_raw = -if_model.score_samples(scaler.transform(X_log[holdout_mask]))
        holdout_if = (holdout_if_raw - if_min) / if_range
        holdout_comb = 0.5 * holdout_lgb + 0.5 * holdout_if

        holdout_lgb_roc = float(roc_auc_score(holdout_y, holdout_lgb)) if len(np.unique(holdout_y)) > 1 else 0.0
        holdout_if_roc = float(roc_auc_score(holdout_y, holdout_if)) if len(np.unique(holdout_y)) > 1 else 0.0
        holdout_comb_roc = float(roc_auc_score(holdout_y, holdout_comb)) if len(np.unique(holdout_y)) > 1 else 0.0
        holdout_lgb_pr = float(average_precision_score(holdout_y, holdout_lgb)) if holdout_y.any() else 0.0
        holdout_comb_pr = float(average_precision_score(holdout_y, holdout_comb)) if holdout_y.any() else 0.0

        vprint(f"  events: {holdout_mask.sum():,} ({holdout_y.sum():,} reds, "
               f"{holdout_y.mean()*100:.1f}% positive)", args.verbose)
        vprint(f"  LGB  ROC-AUC: {holdout_lgb_roc:.4f}  PR-AUC: {holdout_lgb_pr:.4f}", args.verbose)
        vprint(f"  IF   ROC-AUC: {holdout_if_roc:.4f}", args.verbose)
        vprint(f"  Comb ROC-AUC: {holdout_comb_roc:.4f}  PR-AUC: {holdout_comb_pr:.4f}", args.verbose)
    else:
        holdout_lgb_roc = holdout_if_roc = holdout_comb_roc = 0.0
        holdout_lgb_pr = holdout_comb_pr = 0.0
        vprint(f"  no events found", args.verbose)

    # ── 12. Save artifacts ──
    lgb_artifact = {
        "model": lgb_model,
        "roc_auc": lgb_roc,
        "threshold": lgb_thresh,
        "features": FEATURES_13,
        "scale_pos_weight": 3,
        "pr_auc": lgb_pr,
        "f1": lgb_test_m["f1"],
        "precision": lgb_test_m["precision"],
        "recall": lgb_test_m["recall"],
        "fpr": lgb_test_m["fpr"],
        "train_rows": len(trtr_idx),
        "val_rows": len(val_idx),
        "test_rows": len(te_idx),
    }
    if_artifact = {
        "model": if_model,
        "scaler": scaler,
        "score_min": float(if_min),
        "score_max": float(if_max),
        "roc_auc": if_roc,
        "threshold": if_thresh,
        "features": FEATURES_13,
        "log_features": IF_LOG_FEATURES,
        "pr_auc": if_pr,
        "f1": if_test_m["f1"],
        "precision": if_test_m["precision"],
        "recall": if_test_m["recall"],
        "fpr": if_test_m["fpr"],
        "train_rows": len(trtr_idx),
        "val_rows": len(val_idx),
        "test_rows": len(te_idx),
    }

    lgb_path = args.model_dir / "lanl_lgb_13feat.joblib"
    if_path = args.model_dir / "lanl_if_13feat.joblib"
    joblib.dump(lgb_artifact, lgb_path)
    joblib.dump(if_artifact, if_path)
    vprint(f"\n  saved {lgb_path} ({lgb_path.stat().st_size/1e6:.1f}MB)", args.verbose)
    vprint(f"  saved {if_path} ({if_path.stat().st_size/1e6:.1f}MB)", args.verbose)

    # ── 13. Report ──
    report = {
        "lightgbm": {
            "roc_auc": round(lgb_roc, 4),
            "pr_auc": round(lgb_pr, 4),
            "f1": round(lgb_test_m["f1"], 4),
            "precision": round(lgb_test_m["precision"], 4),
            "recall": round(lgb_test_m["recall"], 4),
            "fpr": round(lgb_test_m["fpr"], 4),
            "threshold": round(lgb_thresh, 6),
            "tp": lgb_test_m["tp"], "fp": lgb_test_m["fp"],
            "fn": lgb_test_m["fn"], "tn": lgb_test_m["tn"],
            "scale_pos_weight": 3,
            "feature_importance": {fn: int(imp) for fn, imp in
                                   sorted(zip(FEATURES_13, lgb_model.feature_importances_),
                                          key=lambda x: -x[1])},
        },
        "isolation_forest": {
            "roc_auc": round(if_roc, 4),
            "pr_auc": round(if_pr, 4),
            "f1": round(if_test_m["f1"], 4),
            "precision": round(if_test_m["precision"], 4),
            "recall": round(if_test_m["recall"], 4),
            "fpr": round(if_test_m["fpr"], 4),
            "threshold": round(if_thresh, 6),
            "tp": if_test_m["tp"], "fp": if_test_m["fp"],
            "fn": if_test_m["fn"], "tn": if_test_m["tn"],
        },
        "combined": {
            "roc_auc": round(comb_roc, 4),
            "pr_auc": round(comb_pr, 4),
            "f1": round(comb_test_m["f1"], 4),
            "precision": round(comb_test_m["precision"], 4),
            "recall": round(comb_test_m["recall"], 4),
            "fpr": round(comb_test_m["fpr"], 4),
            "threshold": round(comb_thresh, 6),
            "tp": comb_test_m["tp"], "fp": comb_test_m["fp"],
        },
        "overlap": {
            "lgb_caught": int(lgb_caught.sum()),
            "if_caught": int(if_caught.sum()),
            "both": both,
            "lgb_only": lgb_only,
            "if_only": if_only,
            "neither": neither,
            "union": union,
            "n_test_reds": n_test_reds,
        },
        "holdout": {
            "attacker": HOLDOUT_ATTACKER,
            "events": int(holdout_mask.sum()),
            "reds": int(y[holdout_mask].sum()),
            "lgb_roc_auc": round(holdout_lgb_roc, 4),
            "if_roc_auc": round(holdout_if_roc, 4),
            "combined_roc_auc": round(holdout_comb_roc, 4),
            "lgb_pr_auc": round(holdout_lgb_pr, 4),
            "combined_pr_auc": round(holdout_comb_pr, 4),
        },
        "config": {
            "total_rows": n,
            "split": "GroupShuffleSplit on src_user, random_state=42",
            "inner_split": "GroupShuffleSplit on src_user, random_state=99, test_size=0.3",
            "features": 13,
            "lgb_params": {
                "num_leaves": 63, "learning_rate": 0.03, "n_estimators": 500,
                "scale_pos_weight": 3, "min_child_samples": 100,
                "reg_alpha": 0.5, "reg_lambda": 5.0,
            },
            "if_params": {
                "n_estimators": 200, "max_samples": 256,
                "contamination": 1e-7, "normal_only": True,
            },
        },
    }
    args.report.write_text(json.dumps(report, indent=2))
    vprint(f"\n  report -> {args.report}", args.verbose)

    # ── Summary ──
    vprint("\n" + "=" * 70, args.verbose)
    vprint("RESULTS SUMMARY", args.verbose)
    vprint("=" * 70, args.verbose)
    vprint(f"{'Model':<15} {'ROC-AUC':>8} {'PR-AUC':>8} {'F1':>8} {'Prec':>8} {'Rec':>8} {'FPR':>8}", args.verbose)
    vprint("-" * 70, args.verbose)
    vprint(f"{'LGB':<15} {lgb_roc:>8.4f} {lgb_pr:>8.4f} {lgb_test_m['f1']:>8.4f} "
           f"{lgb_test_m['precision']:>8.4f} {lgb_test_m['recall']:>8.4f} {lgb_test_m['fpr']:>8.4f}", args.verbose)
    vprint(f"{'IF':<15} {if_roc:>8.4f} {if_pr:>8.4f} {if_test_m['f1']:>8.4f} "
           f"{if_test_m['precision']:>8.4f} {if_test_m['recall']:>8.4f} {if_test_m['fpr']:>8.4f}", args.verbose)
    vprint(f"{'Combined':<15} {comb_roc:>8.4f} {comb_pr:>8.4f} {comb_test_m['f1']:>8.4f} "
           f"{comb_test_m['precision']:>8.4f} {comb_test_m['recall']:>8.4f} {comb_test_m['fpr']:>8.4f}", args.verbose)
    vprint("-" * 70, args.verbose)
    vprint(f"HOLDOUT {HOLDOUT_ATTACKER}:", args.verbose)
    vprint(f"  LGB ROC-AUC: {holdout_lgb_roc:.4f}  IF ROC-AUC: {holdout_if_roc:.4f}  "
           f"Combined ROC-AUC: {holdout_comb_roc:.4f}", args.verbose)
    vprint("=" * 70, args.verbose)
    vprint(f"\nDONE {mem_msg('done')}", args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
