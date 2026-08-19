#!/usr/bin/env python3
"""Full-data anomaly models + rank-average ensembles.

Every model trains on the SAME full training split of the 1M sample
(no per-model subsets) and scores the same test split. An ensemble
rank-averages the per-event scores so no single model's score scale
dominates.

Method:
  - per-user chronological 70/30 split (src/_shared.split_sql)
  - features standardized with a scaler fit on the full train split
  - contamination = the train split's own attack-IP share (computed, not hardcoded)
  - anomaly score = -decision_function (higher = more anomalous)
  - threshold tuned on the gold label (is_attack_ip AND login_success)
    under FPR <= 5% (src/_shared.tune_threshold)

Models (all on the full train split, no subsets):
  isolation_forest      IsolationForest
  local_outlier_factor  LocalOutlierFactor (novelty=True)
  one_class_svm         SGDOneClassSVM (scalable linear one-class SVM;
                        kernel OneClassSVM is O(n^2) and infeasible at this size)
  elliptic_envelope     EllipticEnvelope; skipped if its fit fails numerically

Ensembles (rank-average of per-event scores):
  ensemble_all      every model that trained
  ensemble_trimmed  only models with gold ROC-AUC > 0.5 (drops coin-flips)

Artifacts:
  reports/ensemble_full_comparison.csv
  reports/ensemble_full_report.json
  models/ensemble_full.joblib   (saved only if an ensemble beats the best
                                 single model within the FPR budget)

Usage:
  python src/07_ensemble_full.py
"""
import argparse
import json
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
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

from _shared import (SEED, FPR_BUDGET, FEATURE_COLS, split_sql, metrics_at,
                     tune_threshold)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEATURES = ROOT / "data" / "processed" / "features.parquet"
DEFAULT_COMPARISON = ROOT / "reports" / "ensemble_full_comparison.csv"
DEFAULT_REPORT = ROOT / "reports" / "ensemble_full_report.json"
DEFAULT_MODEL = ROOT / "models" / "ensemble_full.joblib"

BASE_COLS = ["row_id", "user_id", "ts", "is_attack_ip", "is_ato",
             "login_success", "hour"]
FEATURE_BASE = [c for c in FEATURE_COLS if c not in ("hour_sin", "hour_cos")]


def rank_avg(arrays: list) -> np.ndarray:
    return np.mean([pd.Series(a).rank(pct=True).to_numpy() for a in arrays], axis=0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    ap.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    args = ap.parse_args()

    args.comparison.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(":memory:")
    con.execute("SET threads=8")

    cols = ", ".join(BASE_COLS + FEATURE_BASE)
    t0 = time.time()
    print(f"loading features from {args.features} ...", flush=True)
    df = con.execute(f"SELECT {cols} FROM read_parquet('{args.features}')").df()
    h = df["hour"].to_numpy() / 24.0 * 2 * np.pi
    df["hour_sin"] = np.sin(h)
    df["hour_cos"] = np.cos(h)
    print(f"loaded {len(df):,} rows ({time.time() - t0:.1f}s)", flush=True)

    split = con.execute(split_sql(args.features)).df()
    df = df.merge(split, on="row_id", how="left")
    if df["split"].isna().any():
        raise SystemExit("split did not cover every row_id")
    train = df[df["split"] == "train"].reset_index(drop=True)
    test = df[df["split"] == "test"].reset_index(drop=True)
    if len(set(train["row_id"]) & set(test["row_id"])):
        raise SystemExit("train/test row_id overlap")
    print(f"split: train {len(train):,} / test {len(test):,} ({len(test)/len(df):.1%})")

    contamination = float(train["is_attack_ip"].mean())
    print(f"contamination = train attack share = {contamination:.4f}")

    X_train = train[FEATURE_COLS].to_numpy()
    X_test = test[FEATURE_COLS].to_numpy()
    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    X_test_s = scaler.transform(X_test)

    y_gold = (test["is_attack_ip"] & test["login_success"]).to_numpy(dtype=bool)
    y_attack = test["is_attack_ip"].to_numpy(dtype=bool)
    y_ato = test["is_ato"].to_numpy(dtype=bool)
    y_legit = (~test["is_attack_ip"] & ~test["is_ato"]).to_numpy(dtype=bool)
    print(f"gold: {y_gold.sum():,} / attack: {y_attack.sum():,} / ATO: {y_ato.sum():,} in test")

    models = {
        "isolation_forest": IsolationForest(
            contamination=contamination, random_state=SEED, n_jobs=-1),
        "local_outlier_factor": LocalOutlierFactor(
            novelty=True, n_neighbors=35, contamination=contamination, n_jobs=-1),
        "one_class_svm": SGDOneClassSVM(
            nu=contamination, shuffle=True, tol=1e-4, random_state=SEED),
        "elliptic_envelope": EllipticEnvelope(
            contamination=contamination, random_state=SEED),
    }

    scores = {}
    notes = {}
    estimators = {}
    for name, estimator in models.items():
        t1 = time.time()
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=r"Determinant has increased")
                estimator.fit(X_train_s)
            estimators[name] = estimator
            t2 = time.time()
            scores[name] = -estimator.decision_function(X_test_s)
            notes[name] = (f"fit on full train {len(X_train):,} rows, contamination "
                           f"{contamination:.4f}")
            print(f"{name:<22} trained on {len(X_train):,} rows "
                  f"({time.time()-t1:.1f}s)", flush=True)
        except Exception as exc:
            notes[name] = f"skipped: {exc}"
            print(f"{name:<22} SKIPPED: {exc}", flush=True)

    if scores:
        all_names = [n for n in scores if n in models]
        ens_all = rank_avg([scores[n] for n in all_names])
        notes["ensemble_all"] = "rank-average of: " + ", ".join(all_names)
        scores["ensemble_all"] = ens_all
        trimmed = [n for n, s in scores.items()
                   if n in models and roc_auc_score(y_gold, s) > 0.5]
        if len(trimmed) >= 2:
            scores["ensemble_trimmed"] = rank_avg([scores[n] for n in trimmed])
            notes["ensemble_trimmed"] = ("rank-average of gold-AUC>0.5 models: "
                                         + ", ".join(trimmed))
        else:
            print(f"trimmed ensemble skipped ({len(trimmed)} models with gold-AUC>0.5)",
                  flush=True)

    rows = []
    report = {}
    best_single = None
    best_ens = None
    for name, s in scores.items():
        t2 = time.time()
        threshold, precision, recall, f1c, thresholds, fpr_curve, within = tune_threshold(y_gold, s)
        m_gold = metrics_at(y_gold, s, threshold)
        m_attack = metrics_at(y_attack, s, threshold)
        ato_detected = int(np.sum((s >= threshold) & y_ato))
        latency = (time.time() - t2) / len(test) * 1e6
        roc_g = float(roc_auc_score(y_gold, s))
        pr_g = float(average_precision_score(y_gold, s))
        roc_a = float(roc_auc_score(y_attack, s))
        pr_a = float(average_precision_score(y_attack, s))
        budget_note = " (no threshold within FPR budget)" if not within else ""
        note = notes[name] + budget_note
        entry = {
            "model": name,
            "status": "ok",
            "note": note,
            "threshold": f"{threshold:.6f}",
            "gold_precision": f"{m_gold['precision']:.4f}",
            "gold_recall": f"{m_gold['recall']:.4f}",
            "gold_f1": f"{m_gold['f1']:.4f}",
            "gold_fpr": f"{m_gold['fpr']:.4f}",
            "attack_recall": f"{m_attack['recall']:.4f}",
            "roc_auc_gold": f"{roc_g:.4f}",
            "pr_auc_gold": f"{pr_g:.4f}",
            "roc_auc_attack": f"{roc_a:.4f}",
            "pr_auc_attack": f"{pr_a:.4f}",
            "ato_detected": ato_detected,
            "ato_test_rows": int(y_ato.sum()),
            "latency_us": f"{latency:.1f}",
            "train_rows": len(X_train) if name not in ("ensemble_all", "ensemble_trimmed") else "n/a",
        }
        rows.append(entry)
        report[name] = {
            "tuned_threshold": round(threshold, 6),
            "gold": m_gold,
            "attack": m_attack,
            "roc_auc_gold": round(roc_g, 4),
            "pr_auc_gold": round(pr_g, 4),
            "roc_auc_attack": round(roc_a, 4),
            "pr_auc_attack": round(pr_a, 4),
            "within_fpr_budget": within,
            "ato_detected": ato_detected,
            "latency_us_per_event": round(latency, 2),
            "note": note,
        }
        if within and name.startswith("ensemble"):
            if best_ens is None or m_gold["f1"] > best_ens[1]["f1"]:
                best_ens = (name, m_gold)
        elif within and name in models:
            if best_single is None or m_gold["f1"] > best_single[1]["f1"]:
                best_single = (name, m_gold)
        print(f"{name:<22} gold F1={m_gold['f1']:.4f} P={m_gold['precision']:.4f} "
              f"R={m_gold['recall']:.4f} FPR={m_gold['fpr']:.4f} "
              f"ROC-AUC={roc_g:.4f} ATO {ato_detected}/{y_ato.sum()} "
              f"({time.time()-t2:.1f}s)", flush=True)

    ranking = sorted(rows, key=lambda r: float(r["gold_f1"]), reverse=True)
    pd.DataFrame(ranking).to_csv(args.comparison, index=False)
    print(f"wrote {args.comparison}")

    ensemble_won = False
    if best_single is not None and best_ens is not None:
        ensemble_won = best_ens[1]["f1"] > best_single[1]["f1"]
        print(f"\nbest single : {best_single[0]} (gold F1={best_single[1]['f1']:.4f})")
        print(f"best ensemble: {best_ens[0]} (gold F1={best_ens[1]['f1']:.4f})")
        print(f"ensemble beats best single: {ensemble_won}")

    if ensemble_won:
        if best_ens[0] == "ensemble_all":
            component_names = [n for n in scores if n in models]
        elif best_ens[0] == "ensemble_trimmed":
            component_names = [n for n in scores
                               if n in models and roc_auc_score(y_gold, scores[n]) > 0.5]
        else:
            component_names = []
        saved = {
            "ensemble": best_ens[0],
            "components": {n: estimators[n] for n in component_names},
            "scaler": scaler,
            "threshold": report[best_ens[0]]["tuned_threshold"],
            "features": FEATURE_COLS,
            "direction": "rank-average of per-model -decision_function",
            "gold_f1": best_ens[1]["f1"],
            "gold_fpr": best_ens[1]["fpr"],
        }
        args.model.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(saved, args.model)
        print(f"wrote {args.model} ({best_ens[0]}, gold F1={best_ens[1]['f1']:.4f})")

    report["split"] = {"train_rows": len(train), "test_rows": len(test),
                       "test_share": round(len(test) / len(df), 4)}
    report["contamination"] = {"value": round(contamination, 4),
                               "rule": "train attack-IP share (computed, not hardcoded)"}
    report["trained_on"] = f"full train split ({len(train):,} rows, attacks included) for every model"
    report["tuned_on"] = "gold (is_attack_ip AND login_success), FPR <= 5%"
    report["fpr_budget"] = FPR_BUDGET
    report["features"] = FEATURE_COLS
    report["best_single"] = ({"model": best_single[0], "gold_f1": best_single[1]["f1"]}
                             if best_single else None)
    report["best_ensemble"] = ({"model": best_ens[0], "gold_f1": best_ens[1]["f1"]}
                               if best_ens else None)
    report["ensemble_beats_best_single"] = ensemble_won
    args.report.write_text(json.dumps(report, indent=2, default=str))
    print(f"report -> {args.report}")

    con.close()
    print("done")


if __name__ == "__main__":
    raise SystemExit(main())
