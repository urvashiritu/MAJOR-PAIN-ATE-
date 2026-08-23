#!/usr/bin/env python3
"""Supervised classification models for login anomaly detection.

Replaces the anomaly detection approach (IsolationForest, LOF, OCSVM, EE)
with supervised XGBoost and Random Forest that USE the attack labels.

Method:
  - per-user chronological 70/30 split (src/_shared.split_sql)
  - XGBoost with scale_pos_weight for extreme class imbalance (1:223k)
  - Random Forest as secondary model
  - threshold tuned on the gold label (is_attack_ip AND login_success)
    under FPR <= 5% (src/_shared.tune_threshold)
  - evaluation via PR-AUC (primary) and recall at fixed FPR (operational)

Artifacts:
  reports/model_comparison.csv
  reports/model_report.json
  models/xgboost_model.joblib   (saved if model beats rule engine baseline)

Usage:
  python src/07_ensemble_full.py
"""
import argparse
import json
import time
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

from _shared import (SEED, FPR_BUDGET, FEATURE_COLS, split_sql, metrics_at,
                     tune_threshold)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEATURES = ROOT / "data" / "processed" / "features.parquet"
DEFAULT_COMPARISON = ROOT / "reports" / "model_comparison.csv"
DEFAULT_REPORT = ROOT / "reports" / "model_report.json"
DEFAULT_MODEL = ROOT / "models" / "xgboost_model.joblib"

BASE_COLS = ["row_id", "user_id", "ts", "is_attack_ip", "is_ato",
             "login_success", "hour"]
FEATURE_BASE = [c for c in FEATURE_COLS if c not in ("hour_sin", "hour_cos")]


def build_xgboost(pos_weight: float):
    """Build XGBoost classifier with cost-sensitive learning."""
    import xgboost as xgb
    return xgb.XGBClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        scale_pos_weight=pos_weight,
        eval_metric="aucpr",
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=SEED,
        n_jobs=-1,
    )


def build_random_forest():
    """Build Random Forest with balanced class weights."""
    return RandomForestClassifier(
        n_estimators=500,
        max_depth=12,
        class_weight="balanced",
        min_samples_leaf=5,
        random_state=SEED,
        n_jobs=-1,
    )


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

    n_pos = int(train["is_attack_ip"].sum())
    n_neg = len(train) - n_pos
    pos_weight = n_neg / max(n_pos, 1)
    print(f"class imbalance: {n_pos:,} attacks / {n_neg:,} normal = 1:{pos_weight:,.0f}")

    models = {
        "xgboost": build_xgboost(pos_weight),
        "random_forest": build_random_forest(),
    }

    scores = {}
    estimators = {}
    for name, estimator in models.items():
        t1 = time.time()
        estimator.fit(X_train_s, train["is_attack_ip"].to_numpy(dtype=int))
        estimators[name] = estimator
        proba = estimator.predict_proba(X_test_s)[:, 1]
        scores[name] = proba
        print(f"{name:<22} trained on {len(X_train):,} rows "
              f"({time.time()-t1:.1f}s)", flush=True)

    rows = []
    report = {}
    best_model = None
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
        entry = {
            "model": name,
            "status": "ok",
            "threshold": f"{threshold:.6f}",
            "gold_precision": f"{m_gold['precision']:.4f}",
            "gold_recall": f"{m_gold['recall']:.4f}",
            "gold_f1": f"{m_gold['f1']:.4f}",
            "gold_fpr": f"{m_gold['fpr']:.4f}",
            "attack_recall": f"{m_attack['recall']:.4f}",
            "roc_auc_gold": f"{roc_g:.4f}",
            "pr_auc_gold": f"{pr_g:.4f}",
            "ato_detected": ato_detected,
            "ato_test_rows": int(y_ato.sum()),
            "latency_us": f"{latency:.1f}",
        }
        rows.append(entry)
        report[name] = {
            "tuned_threshold": round(threshold, 6),
            "gold": m_gold,
            "attack": m_attack,
            "roc_auc_gold": round(roc_g, 4),
            "pr_auc_gold": round(pr_g, 4),
            "within_fpr_budget": within,
            "ato_detected": ato_detected,
            "latency_us_per_event": round(latency, 2),
        }
        if within:
            if best_model is None or m_gold["f1"] > best_model[1]["f1"]:
                best_model = (name, m_gold)
        print(f"{name:<22} gold F1={m_gold['f1']:.4f} P={m_gold['precision']:.4f} "
              f"R={m_gold['recall']:.4f} FPR={m_gold['fpr']:.4f} "
              f"ROC-AUC={roc_g:.4f} PR-AUC={pr_g:.4f} "
              f"ATO {ato_detected}/{y_ato.sum()} "
              f"({time.time()-t2:.1f}s)", flush=True)

    ranking = sorted(rows, key=lambda r: float(r["gold_f1"]), reverse=True)
    pd.DataFrame(ranking).to_csv(args.comparison, index=False)
    print(f"wrote {args.comparison}")

    if best_model is not None:
        name, m = best_model
        saved = {
            "model_name": name,
            "model": estimators[name],
            "scaler": scaler,
            "threshold": report[name]["tuned_threshold"],
            "features": FEATURE_COLS,
            "gold_f1": m["f1"],
            "gold_fpr": m["fpr"],
            "pr_auc": report[name]["pr_auc_gold"],
        }
        args.model.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(saved, args.model)
        print(f"wrote {args.model} ({name}, gold F1={m['f1']:.4f}, PR-AUC={report[name]['pr_auc_gold']:.4f})")

    report["split"] = {"train_rows": len(train), "test_rows": len(test),
                       "test_share": round(len(test) / len(df), 4)}
    report["class_imbalance"] = {"pos": n_pos, "neg": n_neg, "ratio": f"1:{pos_weight:,.0f}"}
    report["trained_on"] = f"full train split ({len(train):,} rows)"
    report["tuned_on"] = "gold (is_attack_ip AND login_success), FPR <= 5%"
    report["fpr_budget"] = FPR_BUDGET
    report["features"] = FEATURE_COLS
    report["best_model"] = ({"model": best_model[0], "gold_f1": best_model[1]["f1"]}
                            if best_model else None)
    args.report.write_text(json.dumps(report, indent=2, default=str))
    print(f"report -> {args.report}")

    con.close()
    print("done")


if __name__ == "__main__":
    raise SystemExit(main())
