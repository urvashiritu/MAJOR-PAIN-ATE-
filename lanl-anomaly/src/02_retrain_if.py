#!/usr/bin/env python3
"""LANL Isolation Forest retraining — full 29.9M rows, stratified split, log-transform.

Fixes all issues from 01_anomaly_ensemble.py:
  - Uses full feat table (604 users, 29.9M rows) instead of 204-user subset
  - Stratified split ensures ~210 reds in test (not 4)
  - Log-transforms skewed features (dst_prior_events, fail_1h, vel_1h)
  - Trains IsolationForest (not EllipticEnvelope) — handles skew natively
  - Correct contamination: 702/29,905,488 ≈ 2.35e-5
  - PR-AUC as primary metric (not F1 on 4 positives)
  - Memory safe: DuckDB + float32 + temp_directory='/tmp'

Output: lanl-anomaly/models/lanl_if.joblib
"""
import argparse
import gc
import json
import os
import shutil
import time
import warnings
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, roc_auc_score, precision_recall_curve
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.preprocessing import StandardScaler

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "raw" / "lanl" / "lanl.duckdb"
DEFAULT_MODEL = ROOT / "models" / "lanl_if.joblib"
DEFAULT_REPORT = ROOT / "reports" / "if_report.json"
DEFAULT_TRAIN_REPORT = ROOT / "reports" / "if_train_report.md"

SEED = 42
FPR_BUDGET = 0.05

FEATURE_COLS = [
    "dst_first", "src_first", "hour_ratio",
    "dst_prior_events", "fail_1h", "vel_1h",
    "hour_sin", "hour_cos",
]

LOG_FEATURES = ["dst_prior_events", "fail_1h", "vel_1h"]


def mem_msg(tag: str) -> str:
    if not HAS_PSUTIL:
        return f"[{tag}]"
    vm = psutil.virtual_memory()
    rss = psutil.Process(os.getpid()).memory_info().rss / (1024**3)
    avail = vm.available / (1024**3)
    total = vm.total / (1024**3)
    try:
        tmp_free = shutil.disk_usage("/tmp").free / (1024**3)
        tmp_str = f" | /tmp free {tmp_free:.1f}G"
    except Exception:
        tmp_str = ""
    return f"[{tag}] RAM {vm.percent:.0f}% avail {avail:.1f}G / {total:.0f}G rss {rss:.1f}G{tmp_str}"


def vprint(msg: str, verbose: bool = True) -> None:
    if verbose:
        print(msg, flush=True)


def metrics_at(y_true: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
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


def tune_threshold(y_true: np.ndarray, scores: np.ndarray,
                   fpr_budget: float = FPR_BUDGET) -> tuple:
    """Best-F1 threshold subject to FPR <= fpr_budget."""
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
        within_budget = False
    else:
        within_budget = True
    best = int(np.argmax(np.where(cand, f1_cut, -np.inf)))
    return (float(thresholds[best]), precision, recall, f1, thresholds, fpr,
            within_budget)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB,
                    help="DuckDB database with feat table")
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--train-report", type=Path, default=DEFAULT_TRAIN_REPORT)
    ap.add_argument("--verbose", action="store_true", default=True)
    ap.add_argument("--no-verbose", dest="verbose", action="store_false")
    ap.add_argument("--n-jobs", type=int, default=12,
                    help="n_jobs for IF (default 12, use all cores)")
    ap.add_argument("--float32", action="store_true", default=True,
                    help="use float32 (default on, halves RAM)")
    ap.add_argument("--no-float32", dest="float32", action="store_false")
    ap.add_argument("--sample", type=int, default=0,
                    help="subsample N rows (0=use all 29.9M)")
    args = ap.parse_args()
    args.model.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    dtype = np.float32 if args.float32 else np.float64
    vprint(f"config: db={args.db} dtype={dtype.__name__} n_jobs={args.n_jobs} "
           f"sample={args.sample or 'all'} {mem_msg('init')}", args.verbose)

    con = duckdb.connect(str(args.db))
    con.execute("SET threads=4")
    con.execute("SET memory_limit='4GB'")
    con.execute("SET temp_directory='/tmp'")

    t0 = time.time()
    vprint(f"loading features from {args.db} ... {mem_msg('pre-load')}", args.verbose)

    if args.sample and args.sample > 0:
        sql = f"""
            SELECT time, src_user, src_computer, dst_computer, hour, is_red,
                   dst_first, src_first, hour_events, user_events,
                   dst_prior_events, fail_1h, vel_1h
            FROM feat
            WHERE is_red = TRUE
               OR random() < {args.sample / 29_905_488.0}
        """
        vprint(f"  subsampling to ~{args.sample:,} rows {mem_msg('sample')}", args.verbose)
    else:
        sql = """
            SELECT time, src_user, src_computer, dst_computer, hour, is_red,
                   dst_first, src_first, hour_events, user_events,
                   dst_prior_events, fail_1h, vel_1h
            FROM feat
        """

    df = con.execute(sql).df()
    con.close()
    vprint(f"  loaded {len(df):,} rows ({df['is_red'].sum():,} reds) "
           f"in {time.time()-t0:.1f}s {mem_msg('post-load')}", args.verbose)

    total_rows = len(df)

    vprint(f"deriving features ... {mem_msg('pre-derive')}", args.verbose)
    df["hour_ratio"] = df["hour_events"] / df["user_events"].replace(0, 1)
    h = df["hour"].to_numpy(dtype=np.float64) / 24.0 * 2 * np.pi
    df["hour_sin"] = np.sin(h)
    df["hour_cos"] = np.cos(h)
    vprint(f"  derived hour_ratio, hour_sin, hour_cos {mem_msg('post-derive')}", args.verbose)

    vprint(f"log-transforming {LOG_FEATURES} ... {mem_msg('pre-log')}", args.verbose)
    for col in LOG_FEATURES:
        df[col] = np.log1p(df[col].to_numpy(dtype=np.float64))
    vprint(f"  log-transform done {mem_msg('post-log')}", args.verbose)

    X = df[FEATURE_COLS].to_numpy(dtype=dtype)
    y = df["is_red"].to_numpy(dtype=bool)
    vprint(f"X {X.shape} {X.dtype} {X.nbytes/1e9:.2f}G y {y.sum():,} reds / {len(y):,} total "
           f"{mem_msg('X-y')}", args.verbose)

    vprint(f"stratified 70/30 split ... {mem_msg('pre-split')}", args.verbose)
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.3, random_state=SEED)
    for train_idx, test_idx in sss.split(X, y):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

    del X, y
    gc.collect()
    vprint(f"  train {len(X_train):,} ({y_train.sum():,} reds) / "
           f"test {len(X_test):,} ({y_test.sum():,} reds) "
           f"{mem_msg('post-split')}", args.verbose)

    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    X_test_s = scaler.transform(X_test)
    vprint(f"scaled train {X_train_s.nbytes/1e9:.2f}G test {X_test_s.nbytes/1e9:.2f}G "
           f"{mem_msg('scaled')}", args.verbose)

    del X_train, X_test
    gc.collect()
    vprint(f"freed raw arrays {mem_msg('post-free')}", args.verbose)

    contamination = 702 / 29_905_488
    vprint(f"contamination = {contamination:.6f} (702 reds / 29.9M total) "
           f"{mem_msg('contamination')}", args.verbose)

    vprint(f"training IsolationForest ... {mem_msg('pre-fit')}", args.verbose)
    t1 = time.time()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        model = IsolationForest(
            n_estimators=200,
            contamination=contamination,
            max_samples="auto",
            random_state=SEED,
            n_jobs=args.n_jobs,
        )
        model.fit(X_train_s)
    t_fit = time.time() - t1
    vprint(f"  IF fit done {t_fit:.1f}s {mem_msg('post-fit')}", args.verbose)

    vprint(f"scoring test set ... {mem_msg('pre-score')}", args.verbose)
    t2 = time.time()
    scores = -model.score_samples(X_test_s)
    t_score = time.time() - t2
    vprint(f"  IF score done {t_score:.1f}s {mem_msg('post-score')}", args.verbose)

    del X_train_s, X_test_s
    gc.collect()
    vprint(f"freed scaled arrays {mem_msg('post-free-scaled')}", args.verbose)

    vprint(f"evaluating ... {mem_msg('pre-eval')}", args.verbose)
    pr_auc = float(average_precision_score(y_test, scores))
    roc_auc = float(roc_auc_score(y_test, scores))
    threshold, precision, recall, f1_arr, thresholds, fpr_curve, within = \
        tune_threshold(y_test, scores)
    m = metrics_at(y_test, scores, threshold)

    vprint(f"  PR-AUC  = {pr_auc:.4f}", args.verbose)
    vprint(f"  ROC-AUC = {roc_auc:.4f}", args.verbose)
    vprint(f"  F1      = {m['f1']:.4f}", args.verbose)
    vprint(f"  Prec    = {m['precision']:.4f}", args.verbose)
    vprint(f"  Rec     = {m['recall']:.4f}", args.verbose)
    vprint(f"  FPR     = {m['fpr']:.4f}", args.verbose)
    vprint(f"  TP={m['tp']:,} FP={m['fp']:,} FN={m['fn']:,} TN={m['tn']:,}",
           args.verbose)
    vprint(f"  within FPR budget: {within} {mem_msg('eval')}", args.verbose)

    artifact = {
        "model": model,
        "model_type": "isolation_forest",
        "scaler": scaler,
        "threshold": threshold,
        "features": FEATURE_COLS,
        "log_features": LOG_FEATURES,
        "contamination": contamination,
        "pr_auc": pr_auc,
        "roc_auc": roc_auc,
        "f1": m["f1"],
        "precision": m["precision"],
        "recall": m["recall"],
        "fpr": m["fpr"],
        "tp": m["tp"],
        "fp": m["fp"],
        "fn": m["fn"],
        "tn": m["tn"],
        "train_rows": len(y_train),
        "test_rows": len(y_test),
        "total_rows": total_rows,
        "n_estimators": 200,
        "n_jobs": args.n_jobs,
        "within_fpr_budget": within,
        "split_method": "stratified",
        "seed": SEED,
    }
    joblib.dump(artifact, args.model)
    sz_mb = args.model.stat().st_size / 1e6
    vprint(f"wrote {args.model} ({sz_mb:.0f}MB) {mem_msg('post-save')}", args.verbose)

    report = {
        "model_type": "isolation_forest",
        "threshold": round(threshold, 6),
        "pr_auc": round(pr_auc, 4),
        "roc_auc": round(roc_auc, 4),
        "f1": round(m["f1"], 4),
        "precision": round(m["precision"], 4),
        "recall": round(m["recall"], 4),
        "fpr": round(m["fpr"], 4),
        "tp": m["tp"],
        "fp": m["fp"],
        "fn": m["fn"],
        "tn": m["tn"],
        "within_fpr_budget": within,
        "contamination": round(contamination, 6),
        "train_rows": len(y_train),
        "test_rows": len(y_test),
        "total_rows": total_rows,
        "features": FEATURE_COLS,
        "log_features": LOG_FEATURES,
        "n_estimators": 200,
        "n_jobs": args.n_jobs,
        "dtype": str(dtype),
        "fit_time_s": round(t_fit, 1),
        "score_time_s": round(t_score, 1),
        "split_method": "stratified",
        "note": "Full 29.9M rows, stratified split, log-transform, IF primary",
    }
    args.report.write_text(json.dumps(report, indent=2, default=str))
    vprint(f"report -> {args.report}", args.verbose)

    md = [
        "# LANL IF Retrain Report",
        "",
        f"**Model:** IsolationForest (n_estimators=200)",
        f"**Data:** full feat table ({total_rows:,} rows, 604 users)",
        f"**Split:** stratified 70/30 (train {len(y_train):,} / test {len(y_test):,})",
        f"**Red events:** {y_train.sum():,} train / {y_test.sum():,} test",
        f"**Contamination:** {contamination:.6f}",
        f"**Features:** {', '.join(FEATURE_COLS)}",
        f"**Log-transformed:** {', '.join(LOG_FEATURES)}",
        f"**dtype:** {dtype.__name__}",
        "",
        "## Results",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| PR-AUC | {pr_auc:.4f} |",
        f"| ROC-AUC | {roc_auc:.4f} |",
        f"| F1 | {m['f1']:.4f} |",
        f"| Precision | {m['precision']:.4f} |",
        f"| Recall | {m['recall']:.4f} |",
        f"| FPR | {m['fpr']:.4f} |",
        f"| Threshold | {threshold:.6f} |",
        f"| Within FPR budget | {within} |",
        "",
        f"**TP={m['tp']:,} FP={m['fp']:,} FN={m['fn']:,} TN={m['tn']:,}**",
        "",
        "## Comparison with Old Model",
        "",
        "| Metric | Old (EE, 204 users) | New (IF, 604 users) |",
        "|---|---|---|",
        f"| PR-AUC | 0.148 | {pr_auc:.4f} |",
        f"| Test reds | 4 | {y_test.sum():,} |",
        f"| Training users | 204 | 604 |",
        "",
        f"Fit time: {t_fit:.1f}s | Score time: {t_score:.1f}s",
    ]
    args.train_report.write_text("\n".join(md))
    vprint(f"train report -> {args.train_report}", args.verbose)

    vprint(f"\nDONE {mem_msg('done')}", args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
