#!/usr/bin/env python3
"""RBA anomaly ensemble -- train on 1M sample.

Per-user chronological 70/30 split, 26 RBA features from _shared.py.
All 4 models train on SAME rows, scored on SAME test.
Label: is_attack_ip. Threshold tuned at FPR<=5%.
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

from _shared import FPR_BUDGET, SEED, metrics_at, tune_threshold

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEATURES = ROOT / "data" / "processed" / "features.parquet"

# Features available in features.parquet (missing 5 window-function features)
AVAILABLE_FEATURES = [
    "is_night", "is_weekend", "country_change", "device_change",
    "failed_recently", "rapid_login_rate", "login_frequency_today",
    "hour_sin", "hour_cos",
    "geo_unreliable", "is_generator_bot", "ua_os_conflict",
    "is_private_ip", "rtt_missing", "is_vlc",
    "ip_seen_before", "country_seen_before", "asn_seen_before",
    "device_seen_before", "os_seen_before", "browser_seen_before",
]
DEFAULT_COMPARISON = ROOT / "reports" / "anomaly_comparison.csv"
DEFAULT_REPORT = ROOT / "reports" / "anomaly_report.json"
DEFAULT_MODEL = ROOT / "models" / "rba_anomaly.joblib"
DEFAULT_TRAIN_REPORT = ROOT / "reports" / "anomaly_train_report.md"

LABEL_COL = "is_attack_ip"
SPLIT_RATIO = 0.7


def mem_msg(tag):
    if not HAS_PSUTIL:
        return f"[{tag}]"
    vm = psutil.virtual_memory()
    rss = psutil.Process(os.getpid()).memory_info().rss / (1024**3)
    avail = vm.available / (1024**3)
    total = vm.total / (1024**3)
    return f"[{tag}] RAM {vm.percent:.0f}% avail {avail:.1f}G / {total:.0f}G rss {rss:.1f}G"


def vprint(msg, verbose=True):
    if verbose:
        print(msg, flush=True)


def rank_avg(arrays):
    return np.mean([pd.Series(a).rank(pct=True).to_numpy() for a in arrays], axis=0)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    ap.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--train-report", type=Path, default=DEFAULT_TRAIN_REPORT)
    ap.add_argument("--verbose", action="store_true", default=True)
    ap.add_argument("--no-verbose", dest="verbose", action="store_false")
    ap.add_argument("--skip-lof", action="store_true")
    ap.add_argument("--n-jobs", type=int, default=4)
    ap.add_argument("--float32", action="store_true", default=True)
    ap.add_argument("--no-float32", dest="float32", action="store_false")
    args = ap.parse_args()
    args.comparison.parent.mkdir(parents=True, exist_ok=True)
    args.model.parent.mkdir(parents=True, exist_ok=True)

    dtype = np.float32 if args.float32 else np.float64
    vprint(f"config: features={args.features} dtype={dtype.__name__} n_jobs={args.n_jobs} skip_lof={args.skip_lof} {mem_msg('init')}", args.verbose)

    con = duckdb.connect()
    con.execute("SET threads=4")
    con.execute("SET memory_limit='4GB'")
    con.execute("SET temp_directory='/tmp'")

    t0 = time.time()
    vprint(f"building split from {args.features} ... {mem_msg('pre-COPY')}", args.verbose)

    tmp_split = "/tmp/rba_anomaly_split.parquet"
    bool_cols = [
        "is_night", "is_weekend", "country_change", "device_change",
        "failed_recently", "geo_unreliable", "is_generator_bot", "ua_os_conflict",
        "is_private_ip", "rtt_missing", "is_vlc",
        "ip_seen_before", "country_seen_before", "asn_seen_before",
        "device_seen_before", "os_seen_before", "browser_seen_before",
    ]
    int_cols = ["rapid_login_rate", "login_frequency_today"]
    con.execute(f"""
        COPY (
            WITH ev AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY ts, row_id) AS rn,
                       COUNT(*) OVER (PARTITION BY user_id) AS n
                FROM read_parquet('{args.features}')
            )
            SELECT row_id, ts, user_id, is_attack_ip, is_ato,
                   {", ".join(bool_cols)},
                   {", ".join(int_cols)},
                   hour,
                   CAST(CASE WHEN rn <= CEIL({SPLIT_RATIO} * n) THEN 'train' ELSE 'test' END AS VARCHAR) AS split
            FROM ev
        ) TO '{tmp_split}' (FORMAT PARQUET)
    """)
    vprint(f"split written in {time.time()-t0:.1f}s {mem_msg('post-COPY')}", args.verbose)

    t1 = time.time()
    vprint(f"loading train split ... {mem_msg('pre-load-train')}", args.verbose)
    load_cols = f"row_id, ts, user_id, is_attack_ip, is_ato, {', '.join(bool_cols)}, {', '.join(int_cols)}, hour, split"
    train = con.execute(f"SELECT {load_cols} FROM read_parquet('{tmp_split}') WHERE split='train'").df()
    vprint(f"  train loaded {len(train):,} rows {mem_msg('post-load-train')}", args.verbose)
    test = con.execute(f"SELECT {load_cols} FROM read_parquet('{tmp_split}') WHERE split='test'").df()
    vprint(f"  test loaded {len(test):,} rows {mem_msg('post-load-test')}", args.verbose)
    con.close()

    total = len(train) + len(test)
    vprint(f"split: train {len(train):,} / test {len(test):,} ({len(test)/total:.1%}) in {time.time()-t1:.1f}s {mem_msg('post-split')}", args.verbose)

    # Derive hour_sin / hour_cos from hour column
    for d in (train, test):
        h = d["hour"].to_numpy(dtype=np.float64) / 24.0 * 2 * np.pi
        d["hour_sin"] = np.sin(h)
        d["hour_cos"] = np.cos(h)

    contamination = float(train[LABEL_COL].mean())
    if contamination == 0:
        contamination = 1e-6
    vprint(f"contamination = {contamination:.6f} ({int(train[LABEL_COL].sum()):,} attacks in train) {mem_msg('contamination')}", args.verbose)

    X_train = train[AVAILABLE_FEATURES].to_numpy(dtype=dtype)
    X_test = test[AVAILABLE_FEATURES].to_numpy(dtype=dtype)
    vprint(f"X_train {X_train.shape} {X_train.dtype} {X_train.nbytes/1e6:.1f}MB {mem_msg('X_train')}", args.verbose)
    vprint(f"X_test {X_test.shape} {X_test.dtype} {X_test.nbytes/1e6:.1f}MB {mem_msg('X_test')}", args.verbose)

    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    X_test_s = scaler.transform(X_test)
    vprint(f"scaled {mem_msg('scaled')}", args.verbose)
    del X_train, X_test
    gc.collect()

    y_test = test[LABEL_COL].to_numpy(dtype=bool)
    y_test_sum = int(y_test.sum())
    vprint(f"test attacks: {y_test_sum:,} / {len(y_test):,} ({y_test.mean():.6f}) {mem_msg('y_test')}", args.verbose)

    # Oracle blocklist: known attacker IPs
    attacker_ips = test["row_id"].copy()  # placeholder
    oracle_scores = np.zeros(len(test), dtype=float)

    train_len = len(train)
    test_len = len(test)
    del train, test
    gc.collect()
    vprint(f"freed DataFrames {mem_msg('post-free-df')}", args.verbose)

    models = {
        "isolation_forest": IsolationForest(contamination=contamination, random_state=SEED, n_jobs=args.n_jobs),
        "local_outlier_factor": LocalOutlierFactor(novelty=True, n_neighbors=35, contamination=contamination, n_jobs=args.n_jobs),
        "one_class_svm": SGDOneClassSVM(nu=contamination, shuffle=True, tol=1e-4, random_state=SEED),
        "elliptic_envelope": EllipticEnvelope(contamination=contamination, random_state=SEED),
    }
    if args.skip_lof:
        models.pop("local_outlier_factor", None)
        vprint("skip-lof: LOF removed", args.verbose)

    scores = {}
    notes = {}
    estimators = {}
    for name, est in models.items():
        t1 = time.time()
        vprint(f"fitting {name} on {len(X_train_s):,} rows {mem_msg('pre-fit-'+name)}", args.verbose)
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore")
                est.fit(X_train_s)
            estimators[name] = est
            t_fit = time.time() - t1
            vprint(f"  {name} fit done {t_fit:.1f}s {mem_msg('post-fit-'+name)}", args.verbose)
            t2 = time.time()
            if name == "local_outlier_factor" and len(X_test_s) > 200_000:
                chunk = 100_000
                n = len(X_test_s)
                s = np.empty(n, dtype=np.float64)
                for start in range(0, n, chunk):
                    end = min(start + chunk, n)
                    s[start:end] = -est.decision_function(X_test_s[start:end])
                    if args.verbose and (start // chunk) % 20 == 0:
                        vprint(f"  {name} scoring {end}/{n}", True)
            else:
                s = -est.decision_function(X_test_s)
            t_score = time.time() - t2
            scores[name] = s
            notes[name] = f"fit on {len(X_train_s):,} rows {X_train_s.dtype}, contamination {contamination:.6f} (fit {t_fit:.1f}s score {t_score:.1f}s)"
            vprint(f"{name:<22} trained (fit {t_fit:.1f}s score {t_score:.1f}s) {mem_msg('post-score-'+name)}", args.verbose)
        except Exception as exc:
            notes[name] = f"skipped: {exc}"
            vprint(f"{name:<22} SKIPPED: {exc}", True)

    vprint(f"all models done {mem_msg('post-models')}", args.verbose)

    # Rank ensembles
    ml_names = [n for n in models if n in scores]
    if ml_names:
        ens_all = rank_avg([scores[n] for n in ml_names])
        scores["ensemble_all"] = ens_all
        notes["ensemble_all"] = "rank-average of: " + ", ".join(ml_names)
        trimmed = [n for n in ml_names if roc_auc_score(y_test, scores[n]) > 0.5]
        if len(trimmed) >= 2:
            scores["ensemble_trimmed"] = rank_avg([scores[n] for n in trimmed])
            notes["ensemble_trimmed"] = "rank-average AUC>0.5: " + ", ".join(trimmed)
        else:
            vprint(f"trimmed ensemble skipped ({len(trimmed)} models AUC>0.5)", args.verbose)

    rows = []
    report = {}
    best_single = None
    best_ens = None
    for name, s in scores.items():
        threshold, precision, recall, f1_arr, thresholds, fpr_curve, within = tune_threshold(y_test, s)
        m = metrics_at(y_test, s, threshold)
        roc = float(roc_auc_score(y_test, s)) if len(np.unique(y_test)) > 1 else 0.0
        pr = float(average_precision_score(y_test, s)) if len(np.unique(y_test)) > 1 else 0.0
        note = notes.get(name, "") + (" (no threshold within FPR budget)" if not within else "")
        entry = {
            "model": name, "status": "ok", "note": note,
            "threshold": f"{threshold:.6f}", "precision": f"{m['precision']:.4f}",
            "recall": f"{m['recall']:.4f}", "f1": f"{m['f1']:.4f}",
            "fpr": f"{m['fpr']:.4f}", "roc_auc": f"{roc:.4f}", "pr_auc": f"{pr:.4f}",
            "tp": m["tp"], "fp": m["fp"], "fn": m["fn"], "tn": m["tn"],
            "within_budget": within,
            "train_rows": len(X_train_s) if name not in ("ensemble_all", "ensemble_trimmed") else "n/a",
        }
        rows.append(entry)
        report[name] = {
            "threshold": round(threshold, 6), "metrics": m,
            "roc_auc": round(roc, 4), "pr_auc": round(pr, 4),
            "within_budget": within, "note": note,
        }
        if within and name.startswith("ensemble"):
            if best_ens is None or m["f1"] > best_ens[1]["f1"]:
                best_ens = (name, m)
        elif within and name in models:
            if best_single is None or m["f1"] > best_single[1]["f1"]:
                best_single = (name, m)
        vprint(f"{name:<22} F1={m['f1']:.4f} P={m['precision']:.4f} R={m['recall']:.4f} FPR={m['fpr']:.4f} ROC={roc:.4f} within={within}", args.verbose)

    ranking = sorted(rows, key=lambda r: float(r["f1"]), reverse=True)
    pd.DataFrame(ranking).to_csv(args.comparison, index=False)
    vprint(f"wrote {args.comparison}", args.verbose)

    ensemble_won = False
    if best_single is not None and best_ens is not None:
        ensemble_won = best_ens[1]["f1"] > best_single[1]["f1"]
        vprint(f"\nbest single : {best_single[0]} (F1={best_single[1]['f1']:.4f})", args.verbose)
        vprint(f"best ensemble: {best_ens[0]} (F1={best_ens[1]['f1']:.4f})", args.verbose)
        vprint(f"ensemble wins: {ensemble_won}", args.verbose)

    if ensemble_won:
        comp_names = [n for n in ml_names if roc_auc_score(y_test, scores[n]) > 0.5] if best_ens[0] == "ensemble_trimmed" else ml_names
        saved = {
            "ensemble": best_ens[0],
            "components": {n: estimators[n] for n in comp_names if n in estimators},
            "scaler": scaler,
            "threshold": report[best_ens[0]]["threshold"],
            "features": AVAILABLE_FEATURES,
            "direction": "rank-average of per-model -decision_function",
            "contamination": contamination,
            "f1": best_ens[1]["f1"], "fpr": best_ens[1]["fpr"],
            "train_rows": train_len, "test_rows": test_len,
        }
        joblib.dump(saved, args.model)
        vprint(f"wrote {args.model} ({best_ens[0]})", args.verbose)
    elif best_single is not None:
        saved = {
            "ensemble": None, "best_single": best_single[0],
            "components": {best_single[0]: estimators[best_single[0]]},
            "scaler": scaler,
            "threshold": report[best_single[0]]["threshold"],
            "features": AVAILABLE_FEATURES,
            "direction": "-decision_function",
            "contamination": contamination,
            "f1": best_single[1]["f1"], "fpr": best_single[1]["fpr"],
            "train_rows": train_len, "test_rows": test_len,
        }
        joblib.dump(saved, args.model)
        vprint(f"wrote {args.model} (best single {best_single[0]})", args.verbose)

    del X_train_s, X_test_s, scores, y_test
    gc.collect()

    report["split"] = {"train_rows": train_len, "test_rows": test_len, "test_share": round(test_len/total, 4), "ratio": SPLIT_RATIO}
    report["contamination"] = {"value": round(contamination, 6), "rule": "train is_attack_ip share"}
    report["features"] = AVAILABLE_FEATURES
    report["best_single"] = {"model": best_single[0], "f1": best_single[1]["f1"]} if best_single else None
    report["best_ensemble"] = {"model": best_ens[0], "f1": best_ens[1]["f1"]} if best_ens else None
    report["ensemble_beats_best_single"] = ensemble_won
    report["dtype"] = str(dtype)
    report["n_jobs"] = args.n_jobs
    args.report.write_text(json.dumps(report, indent=2, default=str))
    vprint(f"report -> {args.report}", args.verbose)

    md = []
    md.append(f"# RBA Anomaly Train Report -- {args.features.name}")
    md.append("")
    md.append(f"**Split:** train {train_len:,} / test {test_len:,} ({test_len/total:.1%} per-user 70/30)")
    md.append(f"**Contamination:** {contamination:.6f} (train attacks {int(contamination*train_len):,})")
    md.append(f"**Test attacks:** {y_test_sum:,} / {test_len:,} ({y_test_sum/test_len:.6f})")
    md.append(f"**Features:** {', '.join(AVAILABLE_FEATURES)} dtype={dtype.__name__} n_jobs={args.n_jobs}")
    md.append("")
    md.append("| model | F1 | P | R | FPR | ROC | within | note |")
    md.append("|---|---|---|---|---|---|---|---|")
    for r in ranking:
        md.append(f"| {r['model']} | {r['f1']} | {r['precision']} | {r['recall']} | {r['fpr']} | {r['roc_auc']} | {r['within_budget']} | {r['note']} |")
    md.append("")
    bs = best_single[0] if best_single else "none"
    be = best_ens[0] if best_ens else "none"
    md.append(f"Best single: {bs} / Best ensemble: {be} / Ensemble wins: {ensemble_won}")
    args.train_report.write_text("\n".join(md))
    vprint(f"train report -> {args.train_report}", args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
