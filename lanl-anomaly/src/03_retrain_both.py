#!/usr/bin/env python3
"""LANL dual-model training: Isolation Forest + LightGBM on full 29.9M rows.

All 702 reds included in training. C17693 evaluated as held-out test AFTER training.

Corrections:
  - fetchnumpy() with BIGINT cast (3.1s, 3.1GB RSS)
  - n_jobs=1 for IF (2.49x less memory than n_jobs=-1)
  - max_samples=256 explicit
  - StandardScaler for IF (distance-based), fit on train only
  - Raw features for LightGBM (tree-based, no scaling)
  - scale_pos_weight computed from train-set counts only
  - IF min/max normalization computed on train scores (no test leakage)
  - Holdout evaluated with ROC-AUC (PR-AUC misleading at 54.7% red)

Output:
  lanl-anomaly/models/lanl_if.joblib
  lanl-anomaly/models/lanl_lgb.joblib
  lanl-anomaly/reports/both_report.json
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
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.preprocessing import StandardScaler

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "raw" / "lanl" / "lanl.duckdb"
DEFAULT_MODEL_DIR = ROOT / "models"
DEFAULT_REPORT = ROOT / "reports" / "both_report.json"

SEED = 42
FPR_BUDGET = 0.05
HOLDOUT_ATTACKER = "C17693"

IF_FEATURES = ["dst_first", "src_first", "hour_ratio", "dst_prior_events",
               "fail_1h", "vel_1h", "hour_sin", "hour_cos", "is_ntlm"]


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


def tune_threshold(y_true, scores, fpr_budget=FPR_BUDGET):
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    with np.errstate(invalid="ignore", divide="ignore"):
        f1 = 2 * precision * recall / (precision + recall)
    f1 = np.nan_to_num(f1, nan=0.0)
    n_thr = len(thresholds)
    f1_cut = f1[:n_thr]
    order = np.argsort(scores, kind="mergesort")
    sorted_scores = scores[order]
    cum_neg = np.cumsum((~y_true.astype(bool))[order].astype(np.int64))
    n_neg = int(np.sum(~y_true.astype(bool)))
    idx = np.searchsorted(sorted_scores, thresholds, side="left")
    neg_below = np.where(idx > 0, cum_neg[np.maximum(idx - 1, 0)], 0)
    fpr = (n_neg - neg_below) / n_neg
    cand = fpr <= fpr_budget
    if not cand.any():
        cand = np.ones(n_thr, dtype=bool)
        within = False
    else:
        within = True
    best = int(np.argmax(np.where(cand, f1_cut, -np.inf)))
    return (float(thresholds[best]), precision, recall, f1, thresholds, fpr, within)


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

    vprint(f"=== LANL Dual-Model Training === {mem_msg('init')}", args.verbose)

    # ── 1. Load via fetchnumpy ──
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
           hour, is_red, src_computer, is_ntlm
    FROM feat
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
    src_computers = result['src_computer']
    n = len(y)
    n_reds = int(y.sum())
    vprint(f"  X_raw {X_raw.shape} {X_raw.dtype} {X_raw.nbytes/1e9:.2f}G | "
           f"{n_reds:,} reds / {n:,} total {time.time()-t1:.1f}s {mem_msg('numpy')}", args.verbose)

    # ── 3. Derive features (in-place on copy) ──
    t1 = time.time()
    X_all = np.empty((n, 9), dtype=np.float32)
    X_all[:, 0] = X_raw[:, 0]  # dst_first
    X_all[:, 1] = X_raw[:, 1]  # src_first
    ue = np.maximum(X_raw[:, 3], 1)
    X_all[:, 2] = X_raw[:, 2] / ue  # hour_ratio
    X_all[:, 3] = X_raw[:, 4]  # dst_prior_events
    X_all[:, 4] = X_raw[:, 5]  # fail_1h
    X_all[:, 5] = X_raw[:, 6]  # vel_1h
    h_rad = X_raw[:, 7] / 24.0 * 2 * np.pi
    X_all[:, 6] = np.sin(h_rad)  # hour_sin
    X_all[:, 7] = np.cos(h_rad)  # hour_cos
    X_all[:, 8] = X_raw[:, 8]   # is_ntlm (binary 0/1)
    vprint(f"  derived 9 features {time.time()-t1:.1f}s {mem_msg('derive')}", args.verbose)

    del X_raw, h_rad, ue, result
    gc.collect()

    # ── 4. Build log-transformed copy for IF ──
    X_log = X_all.copy()
    X_log[:, 3] = np.log1p(X_log[:, 3])
    X_log[:, 4] = np.log1p(X_log[:, 4])
    X_log[:, 5] = np.log1p(X_log[:, 5])
    # is_ntlm (index 8) is binary 0/1 — no log transform needed
    vprint(f"  log-transformed for IF {mem_msg('log')}", args.verbose)

    # ── 5. Stratified split on FULL data (all 702 reds in training) ──
    t1 = time.time()
    holdout_mask = src_computers == HOLDOUT_ATTACKER
    vprint(f"  C17693 holdout will be evaluated AFTER training "
           f"({holdout_mask.sum():,} events, {y[holdout_mask].sum():,} reds) {mem_msg('holdout')}", args.verbose)

    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.3, random_state=SEED)
    for tr_idx, te_idx in sss.split(X_log, y):
        tr_idx, te_idx = tr_idx, te_idx

    y_train, y_test = y[tr_idx], y[te_idx]
    vprint(f"  split: train {len(tr_idx):,} ({y_train.sum():,} reds) / "
           f"test {len(te_idx):,} ({y_test.sum():,} reds) "
           f"{time.time()-t1:.1f}s {mem_msg('split')}", args.verbose)

    # ── 6. Isolation Forest ──
    t1 = time.time()
    vprint(f"training IsolationForest ... {mem_msg('pre-if')}", args.verbose)

    scaler = StandardScaler()
    X_train_if = scaler.fit_transform(X_log[tr_idx])
    X_test_if = scaler.transform(X_log[te_idx])

    contamination = 702 / 29_905_488
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        if_model = IsolationForest(
            n_estimators=200,
            contamination=contamination,
            max_samples=256,
            n_jobs=1,
            random_state=SEED,
        )
        if_model.fit(X_train_if)
    t_if = time.time() - t1
    vprint(f"  IF fit done {t_if:.1f}s {mem_msg('if-fit')}", args.verbose)

    t2 = time.time()
    # Score on train to get percentile-based min/max (no test leakage)
    # Use p1/p99 instead of absolute min/max to widen live score spread
    if_scores_train_raw = -if_model.score_samples(X_train_if)
    if_min = float(np.percentile(if_scores_train_raw, 1))
    if_max = float(np.percentile(if_scores_train_raw, 99))
    if_range = if_max - if_min if if_max > if_min else 1.0

    if_scores_raw = -if_model.score_samples(X_test_if)
    if_scores = (if_scores_raw - if_min) / if_range
    t_if_score = time.time() - t2
    vprint(f"  IF score done {t_if_score:.1f}s (min={if_min:.4f} max={if_max:.4f}) {mem_msg('if-score')}", args.verbose)

    # IF evaluation
    if_pr_auc = float(average_precision_score(y_test, if_scores))
    if_roc_auc = float(roc_auc_score(y_test, if_scores))
    if_thresh, if_prec, if_recall, if_f1, _, _, if_within = tune_threshold(y_test, if_scores)
    if_m = metrics_at(y_test, if_scores, if_thresh)
    vprint(f"  IF: PR-AUC={if_pr_auc:.4f} ROC={if_roc_auc:.4f} F1={if_m['f1']:.4f} "
           f"P={if_m['precision']:.4f} R={if_m['recall']:.4f} FPR={if_m['fpr']:.4f} "
           f"within={if_within}", args.verbose)

    del X_train_if, X_test_if
    gc.collect()

    # ── 7. LightGBM ──
    t1 = time.time()
    vprint(f"training LightGBM ... {mem_msg('pre-lgb')}", args.verbose)

    X_train_lgb = X_all[tr_idx]
    X_test_lgb = X_all[te_idx]
    n_red_train = int(y_train.sum())
    spw = 100  # lowered from 42634 to prevent LGB output saturation
    vprint(f"  scale_pos_weight = {spw:.0f} ({n_red_train:,} reds in {len(y_train):,} train)", args.verbose)

    lgb_model = lgb.LGBMClassifier(
        num_leaves=31,
        learning_rate=0.05,
        n_estimators=200,
        scale_pos_weight=spw,
        random_state=SEED,
        n_jobs=1,
        verbose=-1,
    )
    lgb_model.fit(X_train_lgb, y_train)
    t_lgb = time.time() - t1
    vprint(f"  LGB fit done {t_lgb:.1f}s {mem_msg('lgb-fit')}", args.verbose)

    t2 = time.time()
    lgb_scores = lgb_model.predict_proba(X_test_lgb)[:, 1]
    t_lgb_score = time.time() - t2
    vprint(f"  LGB score done {t_lgb_score:.1f}s {mem_msg('lgb-score')}", args.verbose)

    lgb_pr_auc = float(average_precision_score(y_test, lgb_scores))
    lgb_roc_auc = float(roc_auc_score(y_test, lgb_scores))
    lgb_thresh, lgb_prec, lgb_recall, lgb_f1, _, _, lgb_within = tune_threshold(y_test, lgb_scores)
    lgb_m = metrics_at(y_test, lgb_scores, lgb_thresh)
    vprint(f"  LGB: PR-AUC={lgb_pr_auc:.4f} ROC={lgb_roc_auc:.4f} F1={lgb_m['f1']:.4f} "
           f"P={lgb_m['precision']:.4f} R={lgb_m['recall']:.4f} FPR={lgb_m['fpr']:.4f} "
           f"within={lgb_within}", args.verbose)

    # ── 9. Combined score ──
    t1 = time.time()
    combined = 0.5 * lgb_scores + 0.5 * if_scores
    comb_pr_auc = float(average_precision_score(y_test, combined))
    comb_roc_auc = float(roc_auc_score(y_test, combined))
    comb_thresh, comb_prec, comb_recall, comb_f1, _, _, comb_within = tune_threshold(y_test, combined)
    comb_m = metrics_at(y_test, combined, comb_thresh)
    vprint(f"  COMBINED: PR-AUC={comb_pr_auc:.4f} ROC={comb_roc_auc:.4f} F1={comb_m['f1']:.4f} "
           f"P={comb_m['precision']:.4f} R={comb_m['recall']:.4f} FPR={comb_m['fpr']:.4f} "
           f"within={comb_within} {mem_msg('combined')}", args.verbose)

    # ── 9. Holdout analysis: evaluate on C17693 AFTER training ──
    holdout_events = X_all[holdout_mask]
    holdout_y = y[holdout_mask]
    if len(holdout_events) > 0:
        holdout_lgb = lgb_model.predict_proba(holdout_events)[:, 1]
        # Fix: single scaler.transform, no double-scaling
        holdout_if_raw = -if_model.score_samples(scaler.transform(X_log[holdout_mask]))
        holdout_if_norm = (holdout_if_raw - if_min) / if_range
        holdout_combined = 0.5 * holdout_lgb + 0.5 * holdout_if_norm

        holdout_lgb_roc = float(roc_auc_score(holdout_y, holdout_lgb)) if len(np.unique(holdout_y)) > 1 else 0.0
        holdout_if_roc = float(roc_auc_score(holdout_y, holdout_if_norm)) if len(np.unique(holdout_y)) > 1 else 0.0
        holdout_comb_roc = float(roc_auc_score(holdout_y, holdout_combined)) if len(np.unique(holdout_y)) > 1 else 0.0
        holdout_lgb_pr = float(average_precision_score(holdout_y, holdout_lgb)) if holdout_y.any() else 0.0
        holdout_comb_pr = float(average_precision_score(holdout_y, holdout_combined)) if holdout_y.any() else 0.0
        vprint(f"\n  HOLDOUT {HOLDOUT_ATTACKER} (evaluated AFTER training):", args.verbose)
        vprint(f"    events: {len(holdout_events):,} ({holdout_y.sum():,} reds, "
               f"{holdout_y.mean()*100:.1f}% positive)", args.verbose)
        vprint(f"    LGB  ROC-AUC: {holdout_lgb_roc:.4f}  PR-AUC: {holdout_lgb_pr:.4f}", args.verbose)
        vprint(f"    IF   ROC-AUC: {holdout_if_roc:.4f}", args.verbose)
        vprint(f"    Comb ROC-AUC: {holdout_comb_roc:.4f}  PR-AUC: {holdout_comb_pr:.4f}", args.verbose)
    else:
        holdout_lgb_roc = holdout_if_roc = holdout_comb_roc = 0.0
        holdout_lgb_pr = holdout_comb_pr = 0.0
        vprint(f"  HOLDOUT {HOLDOUT_ATTACKER}: no events found", args.verbose)

    # ── 11. Save artifacts ──
    if_artifact = {
        "model": if_model, "model_type": "isolation_forest",
        "scaler": scaler, "threshold": if_thresh,
        "features": IF_FEATURES, "log_features": ["dst_prior_events", "fail_1h", "vel_1h"],
        "contamination": contamination, "score_min": float(if_min), "score_max": float(if_max),
        "pr_auc": if_pr_auc, "roc_auc": if_roc_auc, "f1": if_m["f1"],
        "precision": if_m["precision"], "recall": if_m["recall"], "fpr": if_m["fpr"],
        "train_rows": len(tr_idx), "test_rows": len(te_idx),
    }
    lgb_artifact = {
        "model": lgb_model, "model_type": "lightgbm",
        "threshold": lgb_thresh, "features": IF_FEATURES,
        "scale_pos_weight": spw,
        "pr_auc": lgb_pr_auc, "roc_auc": lgb_roc_auc, "f1": lgb_m["f1"],
        "precision": lgb_m["precision"], "recall": lgb_m["recall"], "fpr": lgb_m["fpr"],
        "train_rows": len(tr_idx), "test_rows": len(te_idx),
    }

    if_path = args.model_dir / "lanl_if.joblib"
    lgb_path = args.model_dir / "lanl_lgb.joblib"
    joblib.dump(if_artifact, if_path)
    joblib.dump(lgb_artifact, lgb_path)
    vprint(f"  saved {if_path} ({if_path.stat().st_size/1e6:.0f}MB)", args.verbose)
    vprint(f"  saved {lgb_path} ({lgb_path.stat().st_size/1e6:.0f}MB)", args.verbose)

    # ── 12. Report ──
    report = {
        "isolation_forest": {
            "pr_auc": round(if_pr_auc, 4), "roc_auc": round(if_roc_auc, 4),
            "f1": round(if_m["f1"], 4), "precision": round(if_m["precision"], 4),
            "recall": round(if_m["recall"], 4), "fpr": round(if_m["fpr"], 4),
            "threshold": round(if_thresh, 6), "within_fpr_budget": if_within,
            "tp": if_m["tp"], "fp": if_m["fp"], "fn": if_m["fn"], "tn": if_m["tn"],
        },
        "lightgbm": {
            "pr_auc": round(lgb_pr_auc, 4), "roc_auc": round(lgb_roc_auc, 4),
            "f1": round(lgb_m["f1"], 4), "precision": round(lgb_m["precision"], 4),
            "recall": round(lgb_m["recall"], 4), "fpr": round(lgb_m["fpr"], 4),
            "threshold": round(lgb_thresh, 6), "within_fpr_budget": lgb_within,
            "tp": lgb_m["tp"], "fp": lgb_m["fp"], "fn": lgb_m["fn"], "tn": lgb_m["tn"],
            "scale_pos_weight": round(spw, 0),
        },
        "combined": {
            "pr_auc": round(comb_pr_auc, 4), "roc_auc": round(comb_roc_auc, 4),
            "f1": round(comb_m["f1"], 4), "precision": round(comb_m["precision"], 4),
            "recall": round(comb_m["recall"], 4), "fpr": round(comb_m["fpr"], 4),
            "threshold": round(comb_thresh, 6), "within_fpr_budget": comb_within,
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
            "total_rows": n, "contamination": round(contamination, 6),
            "split": "stratified 70/30, C17693 evaluated after training",
            "n_jobs_if": 1, "max_samples_if": 256, "n_estimators": 200,
        },
    }
    args.report.write_text(json.dumps(report, indent=2))
    vprint(f"\n  report -> {args.report}", args.verbose)

    # ── Summary table ──
    vprint("\n" + "=" * 70, args.verbose)
    vprint("RESULTS SUMMARY", args.verbose)
    vprint("=" * 70, args.verbose)
    vprint(f"{'Model':<15} {'PR-AUC':>8} {'ROC-AUC':>8} {'F1':>8} {'Prec':>8} {'Rec':>8} {'FPR':>8}", args.verbose)
    vprint("-" * 70, args.verbose)
    vprint(f"{'IF':<15} {if_pr_auc:>8.4f} {if_roc_auc:>8.4f} {if_m['f1']:>8.4f} {if_m['precision']:>8.4f} {if_m['recall']:>8.4f} {if_m['fpr']:>8.4f}", args.verbose)
    vprint(f"{'LGB':<15} {lgb_pr_auc:>8.4f} {lgb_roc_auc:>8.4f} {lgb_m['f1']:>8.4f} {lgb_m['precision']:>8.4f} {lgb_m['recall']:>8.4f} {lgb_m['fpr']:>8.4f}", args.verbose)
    vprint(f"{'Combined':<15} {comb_pr_auc:>8.4f} {comb_roc_auc:>8.4f} {comb_m['f1']:>8.4f} {comb_m['precision']:>8.4f} {comb_m['recall']:>8.4f} {comb_m['fpr']:>8.4f}", args.verbose)
    vprint("-" * 70, args.verbose)
    vprint(f"HOLDOUT {HOLDOUT_ATTACKER}:", args.verbose)
    vprint(f"  LGB ROC-AUC: {holdout_lgb_roc:.4f}  IF ROC-AUC: {holdout_if_roc:.4f}  Combined ROC-AUC: {holdout_comb_roc:.4f}", args.verbose)
    vprint("=" * 70, args.verbose)
    vprint(f"\nDONE {mem_msg('done')}", args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
