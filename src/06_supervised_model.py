#!/usr/bin/env python3
"""Supervised models on the gold label (Phase 6 extension, Aug 11).

Phase 6 (src/05_models_evaluation.py) trains unsupervised anomaly
detectors on clean rows only, and honestly reports that behavior cannot
predict an IP blocklist (best behavioral gold F1 = 0.110 vs the IP-prior
ceiling of 0.747).

This script answers the follow-up: what does a SUPERVISED model achieve
when it is allowed to train on the gold label itself?

  gold = is_attack_ip AND login_success  (successful login from a
         blocked IP) -- 153,352 rows in the sample (~15% of the sample).

Method (kept identical to Phase 6 so results are directly comparable):
  - same per-user chronological split (first ceil(0.7*n) events = train)
  - same 21 FEATURE_COLS (behavioral features only; no raw IP, no labels)
  - same threshold tuning on test gold under FPR <= 0.05
  - same metric set + replay table

Models:
  supervised_hgb   HistGradientBoostingClassifier, class_weight balanced
  supervised_lr    LogisticRegression on scaled features, balanced

Honest caveats (all consistent with Phase 6 methodology):
  - The split is per-user chronological, so test users also appear in
    train (later events). Results describe "later events of seen users",
    NOT new-user generalization.
  - The threshold is tuned on the test gold labels (same as Phase 6):
    consistent-but-optimistic.
  - ATO rows (14 in test) are expected to be largely missed by supervised
    models: gold (blocklist) and ATO (behavior) are different
    populations. The rules engine remains the ATO detection tool.

Artifacts:
  reports/supervised_evaluation.json
  reports/supervised_replay.csv
  models/supervised_hgb.joblib   (the winner: HGB + scaler + tuned threshold)

Usage:
  python src/06_supervised_model.py
"""
import argparse
import json
import time
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.preprocessing import StandardScaler

from _shared import (SEED, SPLIT_RATIO, FPR_BUDGET, FEATURE_COLS, load_data,
                     split_sql, metrics_at, tune_threshold, replay_rows)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEATURES = ROOT / "data" / "processed" / "features.parquet"
DEFAULT_SCORES = ROOT / "reports" / "rule_baseline_scores.parquet"
DEFAULT_PHASE6 = ROOT / "reports" / "model_evaluation.json"
DEFAULT_REPORT = ROOT / "reports" / "supervised_evaluation.json"
DEFAULT_REPLAY = ROOT / "reports" / "supervised_replay.csv"
DEFAULT_MODEL = ROOT / "models" / "supervised_hgb.joblib"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    ap.add_argument("--scores", type=Path, default=DEFAULT_SCORES)
    ap.add_argument("--phase6", type=Path, default=DEFAULT_PHASE6)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--replay", type=Path, default=DEFAULT_REPLAY)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    args = ap.parse_args()

    args.report.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(":memory:")
    con.execute("SET threads=8")

    t0 = time.time()
    print(f"loading features from {args.features} ...", flush=True)
    df = load_data(con, args.features, args.scores)
    print(f"loaded {len(df):,} rows ({time.time() - t0:.1f}s)", flush=True)

    split = con.execute(split_sql(args.features)).df()
    df = df.merge(split, on="row_id", how="left")
    if df["split"].isna().any():
        raise SystemExit("split did not cover every row_id")
    train = df[df["split"] == "train"].reset_index(drop=True)
    test = df[df["split"] == "test"].reset_index(drop=True)
    if len(set(train["row_id"]) & set(test["row_id"])):
        raise SystemExit("train/test row_id overlap")
    test_share = len(test) / len(df)
    print(f"split: train {len(train):,} / test {len(test):,} ({test_share:.1%})")

    X_train = train[FEATURE_COLS].to_numpy()
    X_test = test[FEATURE_COLS].to_numpy()
    y_train_gold = (train["is_attack_ip"] & train["login_success"]).to_numpy(dtype=bool)
    y_gold = (test["is_attack_ip"] & test["login_success"]).to_numpy(dtype=bool)
    y_attack = test["is_attack_ip"].to_numpy(dtype=bool)
    y_ato = test["is_ato"].to_numpy(dtype=bool)
    y_legit = (~test["is_attack_ip"] & ~test["is_ato"]).to_numpy(dtype=bool)
    print(f"gold share: train {y_train_gold.mean():.4f} / test {y_gold.mean():.4f}")

    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    X_test_s = scaler.transform(X_test)

    estimators = {
        "supervised_hgb": HistGradientBoostingClassifier(
            max_iter=200, learning_rate=0.1, max_leaf_nodes=31,
            class_weight="balanced", early_stopping=True,
            validation_fraction=0.1, n_iter_no_change=20,
            random_state=SEED),
        "supervised_lr": LogisticRegression(
            max_iter=1000, class_weight="balanced", random_state=SEED),
    }

    comparison = []
    replay_table = []
    report = {}
    saved_model = None

    for name, estimator in estimators.items():
        t1 = time.time()
        scaled = name == "supervised_lr"
        X_fit = X_train_s if scaled else X_train
        X_scored = X_test_s if scaled else X_test
        print(f"training {name:<16} on {len(X_fit):,} rows "
              f"(supervised, gold label, {len(FEATURE_COLS)} features) ...", flush=True)
        estimator.fit(X_fit, y_train_gold)
        t2 = time.time()
        scores = estimator.predict_proba(X_scored)[:, 1]
        latency_us = (time.time() - t2) / len(test) * 1e6
        note = (f"supervised on gold label ({len(X_fit):,} train rows), "
                f"class_weight=balanced, {'scaled' if scaled else 'trees'}")

        threshold, precision, recall, f1c, thresholds, fpr_curve, within_budget = tune_threshold(y_gold, scores)
        m_gold = metrics_at(y_gold, scores, threshold)
        m_attack = metrics_at(y_attack, scores, threshold)
        ato_pred = scores >= threshold
        ato_detected = int(np.sum(ato_pred & y_ato))
        ato_test = int(np.sum(y_ato))
        ato_users_test = set(test.loc[y_ato, "user_id"])
        ato_users_hit = set(test.loc[ato_pred & y_ato, "user_id"])
        k = max(1, ato_test)
        top_k = np.argsort(scores, kind="mergesort")[::-1][:k]
        recall_at_k = float(y_ato[top_k].mean())
        pr_auc_gold = float(average_precision_score(y_gold, scores))
        roc_auc_gold = float(roc_auc_score(y_gold, scores))
        budget_note = " (no threshold within FPR budget)" if not within_budget else ""
        note = f"{note}{budget_note}"

        comparison.append({"model": name, "status": "ok",
                           "note": note, "threshold": f"{threshold:.6f}",
                           "gold_precision": f"{m_gold['precision']:.4f}",
                           "gold_recall": f"{m_gold['recall']:.4f}",
                           "gold_f1": f"{m_gold['f1']:.4f}",
                           "gold_fpr": f"{m_gold['fpr']:.4f}",
                           "attack_recall": f"{m_attack['recall']:.4f}",
                           "pr_auc_gold": f"{pr_auc_gold:.4f}",
                           "roc_auc_gold": f"{roc_auc_gold:.4f}",
                           "ato_detected": ato_detected, "ato_test_rows": ato_test,
                           "ato_users_detected": len(ato_users_hit),
                           "ato_users_in_test": len(ato_users_test),
                           "recall_at_k": f"{recall_at_k:.4f}",
                           "latency_us": f"{latency_us:.1f}", "train_rows": len(X_fit)})
        replay_table += replay_rows(name, scores, y_gold, y_ato, y_legit)
        report[name] = {"tuned_threshold": round(threshold, 6),
                        "gold": m_gold, "attack": m_attack,
                        "pr_auc_gold": round(pr_auc_gold, 4),
                        "roc_auc_gold": round(roc_auc_gold, 4),
                        "within_fpr_budget": within_budget,
                        "ato_detected_rows": ato_detected, "ato_test_rows": ato_test,
                        "ato_users_detected": len(ato_users_hit),
                        "ato_users_in_test": len(ato_users_test),
                        "recall_at_k": round(recall_at_k, 4),
                        "latency_us_per_event": round(latency_us, 2), "note": note}
        if name == "supervised_hgb":
            saved_model = {"model": estimator, "scaler": scaler,
                           "threshold": float(threshold),
                           "features": FEATURE_COLS,
                           "direction": "predict_proba[:, 1] on gold (is_attack_ip AND login_success)",
                           "gold_f1": m_gold["f1"], "gold_fpr": m_gold["fpr"]}
        print(f"{name:<16} gold F1={m_gold['f1']:.4f} P={m_gold['precision']:.4f} "
              f"R={m_gold['recall']:.4f} FPR={m_gold['fpr']:.4f} "
              f"ROC-AUC={roc_auc_gold:.4f} ATO {ato_detected}/{ato_test} "
              f"recall@k={recall_at_k:.2f} ({time.time() - t1:.1f}s)", flush=True)

    pd.DataFrame(replay_table,
                 columns=["model", "challenge_rate", "gold_tpr", "ato_tpr", "legit_rechallenge"]).to_csv(
        args.replay, index=False)
    print(f"wrote {args.replay}")

    if saved_model is not None:
        args.model.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(saved_model, args.model)
        print(f"wrote {args.model} (supervised_hgb, gold F1={saved_model['gold_f1']:.4f})")

    phase6 = {}
    if args.phase6.exists():
        phase6 = json.loads(args.phase6.read_text())
    report["comparison"] = comparison
    report["split"] = {"train_rows": len(train), "test_rows": len(test),
                       "test_share": round(test_share, 4),
                       "rule": f"first ceil({SPLIT_RATIO}*n) by (ts, row_id)",
                       "caveat": "per-user chronological: test users also appear in train "
                                 "(later events); results are for later events of seen users, "
                                 "not new-user generalization"}
    report["tuned_on"] = (f"gold (is_attack_ip AND login_success), FPR <= {FPR_BUDGET} "
                          "(tuned on test gold, consistent-but-optimistic, same as Phase 6)")
    report["fpr_budget"] = FPR_BUDGET
    report["features"] = FEATURE_COLS
    report["phase6_reference"] = {
        "best_behavioral_gold_f1 (LOF)": phase6.get("best_behavioral_gold_f1", "n/a"),
        "ip_prior_gold_f1 (blocklist ceiling)": phase6.get("ip_prior_gold_f1", "n/a"),
    }
    report["ato_note"] = ("gold (blocklist) and ATO (behavior) are different populations; "
                          "the rules engine (reports/replay_analysis.csv, ~79% ATO at 10% "
                          "challenge) remains the ATO detection tool.")

    args.report.write_text(json.dumps(report, indent=2, default=str))
    print(f"report -> {args.report}")

    con.close()
    print("done")


if __name__ == "__main__":
    raise SystemExit(main())
