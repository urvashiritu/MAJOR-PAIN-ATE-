#!/usr/bin/env python3
"""LANL anomaly ensemble — full 20.9M train, equal for all models.

Mirrors src/07_ensemble_full.py exactly but for LANL feat.parquet:
  - per-user chronological 70/30 split: PARTITION BY src_user ORDER BY time, src_computer, dst_computer
  - 8 inputs: dst_first, src_first, hour_ratio, dst_prior_events, fail_1h, vel_1h, hour_sin, hour_cos
  - scaler fit on train only, contamination=train red rate, score=-decision_function
  - threshold tuned on is_red under FPR<=5% (src/_shared style)
  - rank-average ensembles, artifacts like 07_ensemble_full.

All 4 models train on the SAME 20.9M rows (equal), scored on SAME 9M test.
Verbose: psutil RSS + available RAM + /tmp free at each stage.
14G-safe: drop varchar, float32, n_jobs caps, chunked LOF scoring.
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
from sklearn.covariance import EllipticEnvelope
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import SGDOneClassSVM
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from _shared import FPR_BUDGET, SEED

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEATURES = ROOT / "data" / "raw" / "lanl" / "feat.parquet"
DEFAULT_COMPARISON = ROOT / "reports" / "lanl_ensemble_comparison.csv"
DEFAULT_REPORT = ROOT / "reports" / "lanl_ensemble_report.json"
DEFAULT_MODEL = ROOT / "models" / "lanl_ensemble.joblib"
DEFAULT_TRAIN_REPORT = ROOT / "reports" / "lanl_train_report.md"

SPLIT_RATIO = 0.7
FEATURE_BASE = ["dst_first", "src_first", "dst_prior_events", "fail_1h", "vel_1h"]
FEATURE_COLS = ["dst_first", "src_first", "hour_ratio", "dst_prior_events", "fail_1h", "vel_1h", "hour_sin", "hour_cos"]


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


def split_sql(features: Path) -> str:
    return f"""
    WITH ev AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY src_user ORDER BY time, src_computer, dst_computer) AS rn,
               COUNT(*) OVER (PARTITION BY src_user) AS n_events
        FROM read_parquet('{features}')
    )
    SELECT time, src_user, dst_computer, src_computer,
           CASE WHEN rn <= CEIL({SPLIT_RATIO} * n_events) THEN 'train' ELSE 'test' END AS split
    FROM ev
    """


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
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "recall": recall, "f1": f1, "fpr": fpr}


def tune_threshold(y_true: np.ndarray, scores: np.ndarray, fpr_budget: float = FPR_BUDGET) -> tuple:
    from sklearn.metrics import precision_recall_curve

    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    with np.errstate(invalid="ignore", divide="ignore"):
        f1 = 2 * precision * recall / (precision + recall)
    f1 = np.nan_to_num(f1, nan=0.0)
    n_thr = len(thresholds)
    f1_cut = f1[:n_thr]
    order = np.argsort(scores, kind="mergesort")
    sorted_scores = scores[order]
    cum_neg = np.cumsum((~y_true.astype(bool))[order].astype(int))
    n_neg = int(np.sum(~y_true.astype(bool)))
    idx = np.searchsorted(sorted_scores, thresholds, side="left")
    neg_below = np.where(idx > 0, cum_neg[np.maximum(idx - 1, 0)], 0)
    fpr = (n_neg - neg_below) / n_neg if n_neg else np.zeros_like(thresholds, dtype=float)
    cand = fpr <= fpr_budget
    if not cand.any():
        cand = np.ones(n_thr, dtype=bool)
        within = False
    else:
        within = True
    best = int(np.argmax(np.where(cand, f1_cut, -np.inf)))
    return float(thresholds[best]), precision, recall, f1, thresholds, fpr, within


def rank_avg(arrays: list) -> np.ndarray:
    return np.mean([pd.Series(a).rank(pct=True).to_numpy() for a in arrays], axis=0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    ap.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--train-report", type=Path, default=DEFAULT_TRAIN_REPORT)
    ap.add_argument("--verbose", action="store_true", default=True, help="verbose psutil logging (default on)")
    ap.add_argument("--no-verbose", dest="verbose", action="store_false")
    ap.add_argument("--skip-lof", action="store_true", help="skip LOF (saves 42m on 20.9M)")
    ap.add_argument("--n-jobs", type=int, default=4, help="n_jobs for IF/LOF (default 4, not -1, to avoid 14G OOM)")
    ap.add_argument("--float32", action="store_true", default=True, help="use float32 (default on, halves RAM)")
    ap.add_argument("--no-float32", dest="float32", action="store_false")
    args = ap.parse_args()
    args.comparison.parent.mkdir(parents=True, exist_ok=True)

    dtype = np.float32 if args.float32 else np.float64
    vprint(f"config: features={args.features} dtype={dtype.__name__} n_jobs={args.n_jobs} skip_lof={args.skip_lof} {mem_msg('init')}", args.verbose)

    con = duckdb.connect()
    con.execute("SET threads=4")
    con.execute("SET memory_limit='4GB'")
    con.execute("SET temp_directory='/tmp'")

    t0 = time.time()
    vprint(f"building split + loading features from {args.features} (DuckDB-only, spill to /tmp) ... {mem_msg('pre-COPY')}", args.verbose)
    if args.verbose:
        try:
            free_gb = shutil.disk_usage("/tmp").free / (1024**3)
            vprint(f"  /tmp free {free_gb:.1f}G  df: {free_gb:.1f}G free", True)
        except Exception:
            pass
    tmp_split = "/tmp/lanl_split.parquet"
    # Verbose: choose column-pruned COPY to save ~7G strings (drop dst_user/auth_type/logon_type/orientation/result)
    con.execute(f"""
        COPY (
            WITH ev AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY src_user ORDER BY time, src_computer, dst_computer) AS rn,
                       COUNT(*) OVER (PARTITION BY src_user) AS n
                FROM read_parquet('{args.features}')
            )
            SELECT time, src_user, dst_user, src_computer, dst_computer, hour, is_red,
                   dst_first, src_first, hour_events, user_events, dst_prior_events, fail_1h, vel_1h,
                   CASE WHEN rn <= CEIL({SPLIT_RATIO} * n) THEN 'train' ELSE 'test' END AS split
            FROM ev
        ) TO '{tmp_split}' (FORMAT PARQUET)
    """)
    vprint(f"split written to {tmp_split} in {time.time()-t0:.1f}s {mem_msg('post-COPY')}", args.verbose)
    try:
        sz = Path(tmp_split).stat().st_size / (1024**2)
        vprint(f"  split parquet {sz:.0f} MB", args.verbose)
    except Exception:
        pass

    t1 = time.time()
    vprint(f"loading train split ... {mem_msg('pre-load-train')}", args.verbose)
    # Column-pruned load: only numeric + needed varchar (src_user for debug, src_computer for oracle)
    train_cols = "time, src_user, src_computer, dst_computer, hour, is_red, dst_first, src_first, hour_events, user_events, dst_prior_events, fail_1h, vel_1h"
    test_cols = train_cols
    train = con.execute(f"SELECT {train_cols} FROM read_parquet('{tmp_split}') WHERE split='train'").df()
    vprint(f"  train loaded {len(train):,} rows {mem_msg('post-load-train')}", args.verbose)
    test = con.execute(f"SELECT {test_cols} FROM read_parquet('{tmp_split}') WHERE split='test'").df()
    vprint(f"  test loaded {len(test):,} rows {mem_msg('post-load-test')}", args.verbose)
    con.close()
    total = len(train) + len(test)
    vprint(f"split: train {len(train):,} / test {len(test):,} ({len(test)/total:.1%}) in {time.time()-t1:.1f}s {mem_msg('post-split')}", args.verbose)

    for d in (train, test):
        d["hour_ratio"] = d["hour_events"] / d["user_events"].replace(0, 1)
        h = d["hour"].to_numpy(dtype=np.float64) / 24.0 * 2 * np.pi
        d["hour_sin"] = np.sin(h)
        d["hour_cos"] = np.cos(h)

    assert len(train) + len(test) == total, "split missing rows"

    sample_user = train["src_user"].iloc[0] if len(train) else "none"
    vprint(f"sample user {sample_user}: train check done {mem_msg('post-derived')}", args.verbose)

    contamination = float(train["is_red"].mean())
    if contamination == 0:
        contamination = 1e-6
    vprint(f"contamination = train is_red share = {contamination:.6f} ({train['is_red'].sum():,} reds in train) {mem_msg('contamination')}", args.verbose)

    X_train = train[FEATURE_COLS].to_numpy(dtype=dtype)
    vprint(f"X_train {X_train.shape} {X_train.dtype} {X_train.nbytes/1e9:.2f}G {mem_msg('X_train')}", args.verbose)
    X_test = test[FEATURE_COLS].to_numpy(dtype=dtype)
    vprint(f"X_test {X_test.shape} {X_test.dtype} {X_test.nbytes/1e9:.2f}G {mem_msg('X_test')}", args.verbose)
    # Free DataFrames early where possible: keep test for oracle column but drop heavy train strings? Keep test for now, will del after scaler
    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    X_test_s = scaler.transform(X_test)
    vprint(f"scaled X_train_s {X_train_s.nbytes/1e9:.2f}G X_test_s {X_test_s.nbytes/1e9:.2f}G {mem_msg('scaled')}", args.verbose)
    # Free raw X to save ~2.6G float64 before model fits
    del X_train, X_test
    gc.collect()
    vprint(f"freed raw X {mem_msg('post-free-X')}", args.verbose)

    y_test = test["is_red"].to_numpy(dtype=bool)
    y_test_sum = int(y_test.sum())
    vprint(f"test reds: {y_test_sum:,} / {len(y_test):,} ({y_test.mean():.6f}) {mem_msg('y_test')}", args.verbose)

    # Oracle blocklist baseline for context (attacker sources) - uses test src_computer still alive
    attacker_srcs = {"C17693", "C19932", "C22409", "C18025"}
    oracle_scores = test["src_computer"].isin(attacker_srcs).to_numpy(dtype=float)
    # Store lengths BEFORE deleting DataFrames
    train_len = len(train)
    test_len = len(test)
    # Now free train/test DataFrames fully to reclaim memory before heavy models
    del train, test
    gc.collect()
    vprint(f"freed train+test dfs {mem_msg('post-free-train')}", args.verbose)

    models = {
        "isolation_forest": IsolationForest(contamination=contamination, random_state=SEED, n_jobs=args.n_jobs),
        "local_outlier_factor": LocalOutlierFactor(novelty=True, n_neighbors=35, contamination=contamination, n_jobs=args.n_jobs),
        "one_class_svm": SGDOneClassSVM(nu=contamination, shuffle=True, tol=1e-4, random_state=SEED),
        "elliptic_envelope": EllipticEnvelope(contamination=contamination, random_state=SEED),
    }
    if args.skip_lof:
        models.pop("local_outlier_factor", None)
        vprint("skip-lof: LOF removed from run", args.verbose)

    scores = {}
    notes = {}
    estimators = {}
    for name, est in models.items():
        t1 = time.time()
        vprint(f"fitting {name} on {len(X_train_s):,} rows {mem_msg(f'pre-fit-{name}')}", args.verbose)
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore")
                est.fit(X_train_s)
            estimators[name] = est
            t_fit = time.time() - t1
            vprint(f"  {name} fit done {t_fit:.1f}s {mem_msg(f'post-fit-{name}')}", args.verbose)
            t2 = time.time()
            # Chunked scoring for LOF on large test to avoid 2.5G matrix
            if name == "local_outlier_factor" and len(X_test_s) > 200_000:
                chunk = 100_000
                n = len(X_test_s)
                s = np.empty(n, dtype=np.float64)
                for start in range(0, n, chunk):
                    end = min(start + chunk, n)
                    s[start:end] = -est.decision_function(X_test_s[start:end])
                    if args.verbose and (start // chunk) % 20 == 0:
                        vprint(f"  {name} scoring {end}/{n} {mem_msg(f'score-chunk-{name}')}", True)
            else:
                s = -est.decision_function(X_test_s)
            t_score = time.time() - t2
            scores[name] = s
            notes[name] = f"fit on full train {len(X_train_s):,} rows {X_train_s.dtype}, contamination {contamination:.6f} (fit {t_fit:.1f}s score {t_score:.1f}s n_jobs={args.n_jobs})"
            vprint(f"{name:<22} trained on {len(X_train_s):,} rows (fit {t_fit:.1f}s score {t_score:.1f}s) {mem_msg(f'post-score-{name}')}", args.verbose)
        except Exception as exc:
            notes[name] = f"skipped: {exc}"
            vprint(f"{name:<22} SKIPPED: {exc} {mem_msg(f'skip-{name}')}", True)

    # Free large scaled arrays before ensembles if needed? Keep for ensembles
    vprint(f"all models done {mem_msg('post-models')}", args.verbose)
    # Oracle as pseudo-model for comparison
    scores["oracle_attacker_src"] = oracle_scores
    notes["oracle_attacker_src"] = "oracle: src_computer in C17693/C19932/C22409/C18025 (post-hoc, not production)"
    # rank ensembles
    ml_names = [n for n in models if n in scores]
    if ml_names:
        ens_all = rank_avg([scores[n] for n in ml_names])
        scores["ensemble_all"] = ens_all
        notes["ensemble_all"] = "rank-average of: " + ", ".join(ml_names)
        # trimmed: only AUC>0.5
        trimmed = [n for n in ml_names if roc_auc_score(y_test, scores[n]) > 0.5]
        if len(trimmed) >= 2:
            scores["ensemble_trimmed"] = rank_avg([scores[n] for n in trimmed])
            notes["ensemble_trimmed"] = "rank-average of AUC>0.5: " + ", ".join(trimmed)
        else:
            vprint(f"trimmed ensemble skipped ({len(trimmed)} models with AUC>0.5) {mem_msg('trimmed-skip')}", args.verbose)

    rows = []
    report = {}
    best_single = None
    best_ens = None
    for name, s in scores.items():
        t2 = time.time()
        threshold, precision, recall, f1_arr, thresholds, fpr_curve, within = tune_threshold(y_test, s)
        m = metrics_at(y_test, s, threshold)
        roc = float(roc_auc_score(y_test, s)) if len(np.unique(y_test)) > 1 else 0.0
        pr = float(average_precision_score(y_test, s)) if len(np.unique(y_test)) > 1 else 0.0
        note = notes[name] + (" (no threshold within FPR budget)" if not within else "")
        entry = {
            "model": name,
            "status": "ok",
            "note": note,
            "threshold": f"{threshold:.6f}",
            "precision": f"{m['precision']:.4f}",
            "recall": f"{m['recall']:.4f}",
            "f1": f"{m['f1']:.4f}",
            "fpr": f"{m['fpr']:.4f}",
            "roc_auc": f"{roc:.4f}",
            "pr_auc": f"{pr:.4f}",
            "tp": m["tp"],
            "fp": m["fp"],
            "fn": m["fn"],
            "tn": m["tn"],
            "within_budget": within,
            "train_rows": len(X_train_s) if name not in ("ensemble_all", "ensemble_trimmed") else "n/a",
        }
        rows.append(entry)
        report[name] = {
            "threshold": round(threshold, 6),
            "metrics": m,
            "roc_auc": round(roc, 4),
            "pr_auc": round(pr, 4),
            "within_budget": within,
            "note": note,
        }
        if within and name.startswith("ensemble"):
            if best_ens is None or m["f1"] > best_ens[1]["f1"]:
                best_ens = (name, m)
        elif within and name in models:
            if best_single is None or m["f1"] > best_single[1]["f1"]:
                best_single = (name, m)
        vprint(f"{name:<22} F1={m['f1']:.4f} P={m['precision']:.4f} R={m['recall']:.4f} FPR={m['fpr']:.4f} ROC={roc:.4f} within={within} {mem_msg('metrics-'+name)}", args.verbose)

    ranking = sorted(rows, key=lambda r: float(r["f1"]), reverse=True)
    pd.DataFrame(ranking).to_csv(args.comparison, index=False)
    vprint(f"wrote {args.comparison} {mem_msg('post-csv')}", args.verbose)

    ensemble_won = False
    if best_single is not None and best_ens is not None:
        ensemble_won = best_ens[1]["f1"] > best_single[1]["f1"]
        vprint(f"\nbest single : {best_single[0]} (F1={best_single[1]['f1']:.4f})", args.verbose)
        vprint(f"best ensemble: {best_ens[0]} (F1={best_ens[1]['f1']:.4f})", args.verbose)
        vprint(f"ensemble beats best single: {ensemble_won} {mem_msg('ensemble-check')}", args.verbose)

    if ensemble_won:
        if best_ens[0] == "ensemble_all":
            comp_names = ml_names
        elif best_ens[0] == "ensemble_trimmed":
            comp_names = [n for n in ml_names if roc_auc_score(y_test, scores[n]) > 0.5]
        else:
            comp_names = []
        saved = {
            "ensemble": best_ens[0],
            "components": {n: estimators[n] for n in comp_names},
            "scaler": scaler,
            "threshold": report[best_ens[0]]["threshold"],
            "features": FEATURE_COLS,
            "feature_base": FEATURE_BASE,
            "direction": "rank-average of per-model -decision_function",
            "contamination": contamination,
            "n_neighbors": 35,
            "f1": best_ens[1]["f1"],
            "fpr": best_ens[1]["fpr"],
            "train_rows": train_len,
            "test_rows": test_len,
        }
        args.model.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(saved, args.model)
        vprint(f"wrote {args.model} ({best_ens[0]}, F1={best_ens[1]['f1']:.4f}) {mem_msg('post-model')}", args.verbose)
    else:
        if best_single is not None:
            saved = {
                "ensemble": None,
                "best_single": best_single[0],
                "components": {best_single[0]: estimators[best_single[0]]},
                "scaler": scaler,
                "threshold": report[best_single[0]]["threshold"],
                "features": FEATURE_COLS,
                "feature_base": FEATURE_BASE,
                "direction": "-decision_function",
                "contamination": contamination,
                "n_neighbors": 35 if best_single[0] == "local_outlier_factor" else None,
                "f1": best_single[1]["f1"],
                "fpr": best_single[1]["fpr"],
                "train_rows": train_len,
                "test_rows": test_len,
            }
            args.model.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(saved, args.model)
            vprint(f"wrote {args.model} (best single {best_single[0]}, F1={best_single[1]['f1']:.4f}) {mem_msg('post-model-single')}", args.verbose)

    # Keep some memory before report: del large arrays
    del X_train_s, X_test_s, scores, y_test
    gc.collect()
    report["split"] = {"train_rows": train_len, "test_rows": test_len, "test_share": round(test_len/total, 4) if total else 0, "ratio": SPLIT_RATIO}
    report["contamination"] = {"value": round(contamination, 6), "rule": "train is_red share (computed)"}
    report["trained_on"] = f"full train split ({train_len:,} rows, is_red included) for every model"
    report["tuned_on"] = "is_red, FPR <= 5%"
    report["fpr_budget"] = FPR_BUDGET
    report["features"] = FEATURE_COLS
    report["best_single"] = {"model": best_single[0], "f1": best_single[1]["f1"]} if best_single else None
    report["best_ensemble"] = {"model": best_ens[0], "f1": best_ens[1]["f1"]} if best_ens else None
    report["ensemble_beats_best_single"] = ensemble_won
    report["dtype"] = str(dtype)
    report["n_jobs"] = args.n_jobs
    args.report.write_text(json.dumps(report, indent=2, default=str))
    vprint(f"report -> {args.report} {mem_msg('post-report')}", args.verbose)

    md = []
    md.append(f"# LANL Train Report — {args.features.name}")
    md.append("")
    md.append(f"**Split:** train {train_len:,} / test {test_len:,} ({test_len/total:.1%} per-user 70/30)")
    md.append(f"**Contamination:** {contamination:.6f} (train reds {int(contamination*train_len):,})")
    md.append(f"**Test reds:** {y_test_sum:,} / {test_len:,} ({y_test_sum/test_len:.6f})")
    md.append(f"**Features:** {', '.join(FEATURE_COLS)} (hour_ratio/sin/cos derived in code) dtype={dtype.__name__} n_jobs={args.n_jobs}")
    md.append("")
    md.append("| model | F1 | P | R | FPR | ROC | within | note |")
    md.append("|---|---|---|---|---|---|---|---|")
    for r in ranking:
        md.append(f"| {r['model']} | {r['f1']} | {r['precision']} | {r['recall']} | {r['fpr']} | {r['roc_auc']} | {r['within_budget']} | {r['note']} |")
    md.append("")
    md.append(f"Best single: {best_single[0] if best_single else 'none'} / Best ensemble: {best_ens[0] if best_ens else 'none'} / Ensemble wins: {ensemble_won}")
    md.append("")
    args.train_report.write_text("\n".join(md))
    vprint(f"train report -> {args.train_report} {mem_msg('post-md')}", args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
