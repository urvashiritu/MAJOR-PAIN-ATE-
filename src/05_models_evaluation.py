#!/usr/bin/env python3
"""Anomaly models and evaluation (Phase 6, revised after validation).

Unsupervised anomaly detection trained on a CLEAN reference population
(attack-IP rows excluded from fitting — the roadmap's "normal or
less-contaminated behavior"), with attack-IP / ATO / gold labels used only
for external evaluation — never for training.

Split: per-user chronological. For each user the events are ordered by
(ts, row_id); the first ceil(0.7 * n) events form the training set, the
rest the test set (single-event users -> train). All models share the SAME
test event set.

Threshold tuning is targeted at the GOLD label (successful attack-IP:
is_attack_ip AND login_success) — is_attack_ip alone is an IP-reputation
label (deterministic per IP, per the RBA dataset design) and is not a
behavioral target. The tuned threshold maximizes F1 over the gold
precision-recall curve subject to a false-positive budget (FPR <= 5%), so
the operating point can never degenerate into flag-everything. A TPR-
calibrated replay (attacker-blocked % vs legit re-challenged % at score
cutoffs — the evaluation style of the RBA authors) is written separately.

Models:
  rule_baseline          scores from src/04_rule_baseline.py (no training)
  ip_reputation_baseline train-only per-IP attack share — an honest
                         blocklist-recall baseline, kept SEPARATE from the
                         behavioral models (never mixed into features)
  isolation_forest       clean train set
  local_outlier_factor   <= 300K clean rows (novelty=True)
  one_class_svm          <= 50K clean rows
  elliptic_envelope      <= 200K clean rows, only if the scaled training
                         features are roughly normal (|skew| <= 2), else skipped

Every sklearn model is scored as anomaly = -decision_function (higher = more
anomalous), so all models share one threshold direction.

Artifacts (PROJECT_ROADMAP.md Phase 6 completion criteria):
  models/final_model.joblib
  reports/model_comparison.csv
  reports/threshold_analysis.csv
  reports/confusion_matrix.png
  reports/replay_analysis.csv
  reports/model_evaluation.json

Usage:
  python src/05_models_evaluation.py
"""
import argparse
import json
import sys
import time
from pathlib import Path

import duckdb
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.covariance import EllipticEnvelope
from sklearn.ensemble import IsolationForest
from sklearn.metrics import precision_recall_curve, roc_auc_score, average_precision_score
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEATURES = ROOT / "data" / "processed" / "features.parquet"
DEFAULT_SCORES = ROOT / "reports" / "rule_baseline_scores.parquet"
DEFAULT_MODEL = ROOT / "models" / "final_model.joblib"
DEFAULT_COMPARISON = ROOT / "reports" / "model_comparison.csv"
DEFAULT_THRESHOLDS = ROOT / "reports" / "threshold_analysis.csv"
DEFAULT_CM_PNG = ROOT / "reports" / "confusion_matrix.png"
DEFAULT_REPLAY = ROOT / "reports" / "replay_analysis.csv"
DEFAULT_REPORT = ROOT / "reports" / "model_evaluation.json"

SEED = 42
SPLIT_RATIO = 0.7
MAX_THRESHOLD_ROWS = 5000
FIT_CONTAMINATION = 0.10
FEATURE_COLS = [
    "is_night", "is_weekend", "country_change", "device_change",
    "failed_recently", "rapid_login_rate", "login_frequency_today",
    "hour_sin", "hour_cos",
    "geo_unreliable", "is_generator_bot", "ua_os_conflict",
    "is_private_ip", "rtt_missing", "is_vlc",
    "ip_seen_before", "country_seen_before", "asn_seen_before",
    "device_seen_before", "os_seen_before", "browser_seen_before",
]
SUBSETS = {"local_outlier_factor": 300_000, "one_class_svm": 50_000,
           "elliptic_envelope": 200_000}
MAX_ABS_SKEW = 2.0
FPR_BUDGET = 0.05
CHALLENGE_RATES = [0.005, 0.01, 0.02, 0.05, 0.10, 0.20]


def load_data(con: duckdb.DuckDBPyConnection, features: Path, scores: Path) -> pd.DataFrame:
    df = con.execute(f"""
        SELECT row_id, user_id, ts, ip, is_attack_ip, is_ato, login_success,
               hour, is_night, is_weekend, country_change, device_change,
               failed_recently, rapid_login_rate, login_frequency_today,
               geo_unreliable, is_generator_bot, ua_os_conflict,
               is_private_ip, rtt_missing, is_vlc,
               ip_seen_before, country_seen_before, asn_seen_before,
               device_seen_before, os_seen_before, browser_seen_before
        FROM read_parquet('{features}')
    """).df()
    rule = con.execute(f"""
        SELECT row_id, rule_score FROM read_parquet('{scores}')
    """).df()
    df = df.merge(rule, on="row_id", how="left")
    if df["rule_score"].isna().any():
        raise SystemExit("rule_baseline_scores.parquet missing row_ids (re-run src/04_rule_baseline.py)")
    h = df["hour"].to_numpy() / 24.0 * 2 * np.pi
    df["hour_sin"] = np.sin(h)
    df["hour_cos"] = np.cos(h)
    return df


def split_sql(features: Path) -> str:
    return f"""
    WITH ev AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY ts, row_id) AS rn,
               COUNT(*) OVER (PARTITION BY user_id) AS n_events
        FROM read_parquet('{features}')
    )
    SELECT row_id,
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
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision, "recall": recall, "f1": f1, "fpr": fpr}


def tune_threshold(y_true: np.ndarray, scores: np.ndarray,
                   fpr_budget: float = FPR_BUDGET) -> tuple:
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


def threshold_rows(name: str, y_true: np.ndarray, scores: np.ndarray,
                   precision: np.ndarray, recall: np.ndarray, f1: np.ndarray,
                   thresholds: np.ndarray, fpr: np.ndarray) -> list:
    n = len(thresholds)
    if n > MAX_THRESHOLD_ROWS:
        idx = np.unique(np.linspace(0, n - 1, MAX_THRESHOLD_ROWS).astype(int))
    else:
        idx = np.arange(n)
    f1 = np.nan_to_num(f1, nan=0.0)
    rows = []
    for i in idx:
        t = float(thresholds[i])
        rows.append([name, f"{t:.6f}", f"{precision[i]:.6f}", f"{recall[i]:.6f}",
                     f"{f1[i]:.6f}", f"{fpr[i]:.6f}"])
    return rows


def replay_rows(name: str, scores: np.ndarray, y_gold: np.ndarray,
                y_ato: np.ndarray, y_legit: np.ndarray) -> list:
    """TPR-calibrated replay: at each challenge rate, what share of gold/ATO
    events are blocked and what share of legit events are re-challenged."""
    order = np.argsort(scores, kind="mergesort")[::-1]
    n = len(scores)
    rows = []
    for rate in CHALLENGE_RATES:
        k = max(1, int(np.ceil(rate * n)))
        blocked = np.zeros(n, dtype=bool)
        blocked[order[:k]] = True
        gold_tpr = float(blocked[y_gold].mean()) if y_gold.any() else 0.0
        ato_tpr = float(blocked[y_ato].mean()) if y_ato.any() else 0.0
        legit_rate = float(blocked[y_legit].mean()) if y_legit.any() else 0.0
        rows.append([name, f"{rate:.3f}", f"{gold_tpr:.4f}", f"{ato_tpr:.4f}",
                     f"{legit_rate:.4f}"])
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    ap.add_argument("--scores", type=Path, default=DEFAULT_SCORES)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    ap.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    ap.add_argument("--cm-png", type=Path, default=DEFAULT_CM_PNG)
    ap.add_argument("--replay", type=Path, default=DEFAULT_REPLAY)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = ap.parse_args()

    args.model.parent.mkdir(parents=True, exist_ok=True)
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

    full_attack_share = float(train["is_attack_ip"].mean())
    clean_train = train[~train["is_attack_ip"]]
    print(f"attack share: full {full_attack_share:.3f} | clean train {len(clean_train):,} rows")

    X_train = train[FEATURE_COLS].to_numpy()
    X_test = test[FEATURE_COLS].to_numpy()
    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    X_test_s = scaler.transform(X_test)

    y_gold = (test["is_attack_ip"] & test["login_success"]).to_numpy(dtype=bool)
    y_attack = test["is_attack_ip"].to_numpy(dtype=bool)
    y_ato = test["is_ato"].to_numpy(dtype=bool)
    y_legit = (~test["is_attack_ip"] & ~test["is_ato"]).to_numpy(dtype=bool)

    ip_prior = train.groupby("ip")["is_attack_ip"].mean()

    models = {
        "rule_baseline": ("rule", None),
        "ip_reputation_baseline": ("ip_prior", None),
        "isolation_forest": ("sklearn", IsolationForest(
            contamination=FIT_CONTAMINATION, random_state=SEED, n_jobs=-1)),
        "local_outlier_factor": ("sklearn", LocalOutlierFactor(
            novelty=True, n_neighbors=35, contamination=FIT_CONTAMINATION, n_jobs=-1)),
        "one_class_svm": ("sklearn", OneClassSVM(
            kernel="rbf", gamma="scale", nu=FIT_CONTAMINATION)),
        "elliptic_envelope": ("sklearn", EllipticEnvelope(
            contamination=FIT_CONTAMINATION, random_state=SEED)),
    }

    comparison = []
    threshold_table = []
    replay_table = []
    cm_data = {}
    report = {}

    for name, (kind, estimator) in models.items():
        t1 = time.time()
        if kind == "rule":
            scores = test["rule_score"].to_numpy(dtype=float)
            train_rows = "n/a"
            latency_us = 0.0
            note = "precomputed (src/04_rule_baseline.py)"
        elif kind == "ip_prior":
            t2 = time.time()
            scores = test["ip"].map(ip_prior).fillna(full_attack_share).to_numpy(dtype=float)
            latency_us = (time.time() - t2) / len(test) * 1e6
            train_rows = len(ip_prior)
            note = (f"train-only per-IP attack share; {len(ip_prior):,} IPs; "
                    f"cold-IP -> global share {full_attack_share:.3f} (blocklist-recall baseline)")
        else:
            if name == "elliptic_envelope":
                skews = np.abs(pd.DataFrame(X_train_s).skew()).to_numpy()
                if skews.max() > MAX_ABS_SKEW:
                    comparison.append({"model": name, "status": "skipped",
                                       "note": f"max |skew|={skews.max():.2f} > {MAX_ABS_SKEW} on scaled train",
                                       "threshold": "", "gold_precision": "", "gold_recall": "",
                                       "gold_f1": "", "gold_fpr": "", "attack_recall": "",
                                       "pr_auc_gold": "", "roc_auc_gold": "", "pr_auc_attack": "",
                                       "roc_auc_attack": "", "ato_detected": "", "ato_test_rows": "",
                                       "ato_users_detected": "", "ato_users_in_test": "",
                                       "recall_at_k": "", "latency_us": "", "train_rows": ""})
                    print(f"{name:<26} skipped (skewed features)", flush=True)
                    continue
            clean_idx = np.flatnonzero(~train["is_attack_ip"].to_numpy())
            if name == "isolation_forest":
                fit_idx = clean_idx
            else:
                subset_size = min(SUBSETS[name], len(clean_idx))
                rng = np.random.RandomState(SEED * 7 + list(models).index(name))
                fit_idx = rng.choice(clean_idx, size=subset_size, replace=False)
            X_fit = X_train_s[fit_idx]
            print(f"training {name:<26} on {len(fit_idx):,} clean rows "
                  f"(contam {FIT_CONTAMINATION}) ...", flush=True)
            estimator.fit(X_fit)
            train_rows = len(fit_idx)
            t2 = time.time()
            scores = -estimator.decision_function(X_test_s)
            latency_us = (time.time() - t2) / len(test) * 1e6
            note = (f"clean-fit {len(fit_idx):,} rows, contamination "
                    f"{FIT_CONTAMINATION} (flag-rate intent)")

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
        pr_auc_attack = float(average_precision_score(y_attack, scores))
        roc_auc_attack = float(roc_auc_score(y_attack, scores))
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
                           "pr_auc_attack": f"{pr_auc_attack:.4f}",
                           "roc_auc_attack": f"{roc_auc_attack:.4f}",
                           "ato_detected": ato_detected, "ato_test_rows": ato_test,
                           "ato_users_detected": len(ato_users_hit),
                           "ato_users_in_test": len(ato_users_test),
                           "recall_at_k": f"{recall_at_k:.4f}",
                           "latency_us": f"{latency_us:.1f}", "train_rows": train_rows})
        threshold_table += threshold_rows(name, y_gold, scores, precision, recall, f1c, thresholds, fpr_curve)
        replay_table += replay_rows(name, scores, y_gold, y_ato, y_legit)
        cm_data[name] = m_gold
        report[name] = {"tuned_threshold": round(threshold, 6),
                        "gold": m_gold, "attack": m_attack,
                        "pr_auc_gold": round(pr_auc_gold, 4), "roc_auc_gold": round(roc_auc_gold, 4),
                        "pr_auc_attack": round(pr_auc_attack, 4), "roc_auc_attack": round(roc_auc_attack, 4),
                        "within_fpr_budget": within_budget,
                        "ato_detected_rows": ato_detected, "ato_test_rows": ato_test,
                        "ato_users_detected": len(ato_users_hit), "ato_users_in_test": len(ato_users_test),
                        "recall_at_k": round(recall_at_k, 4),
                        "latency_us_per_event": round(latency_us, 2), "note": note}
        print(f"{name:<26} gold F1={m_gold['f1']:.4f} P={m_gold['precision']:.4f} "
              f"R={m_gold['recall']:.4f} FPR={m_gold['fpr']:.4f} "
              f"ROC-AUC={roc_auc_gold:.4f} ATO {ato_detected}/{ato_test} "
              f"recall@k={recall_at_k:.2f} ({time.time() - t1:.1f}s)", flush=True)

    cmp_df = pd.DataFrame(comparison)
    cmp_df.to_csv(args.comparison, index=False)
    pd.DataFrame(threshold_table,
                 columns=["model", "threshold", "precision", "recall", "f1", "fpr"]).to_csv(
        args.thresholds, index=False)
    pd.DataFrame(replay_table,
                 columns=["model", "challenge_rate", "gold_tpr", "ato_tpr", "legit_rechallenge"]).to_csv(
        args.replay, index=False)
    print(f"wrote {args.comparison}")
    print(f"wrote {args.thresholds}")
    print(f"wrote {args.replay}")

    plot_confusion_matrices(cm_data, args.cm_png)
    print(f"wrote {args.cm_png}")

    rule_f1 = float(cmp_df.loc[cmp_df["model"] == "rule_baseline", "gold_f1"].iloc[0])
    ip_prior_f1 = float(cmp_df.loc[cmp_df["model"] == "ip_reputation_baseline", "gold_f1"].iloc[0])
    ml = cmp_df[(~cmp_df["model"].isin(["rule_baseline", "ip_reputation_baseline"]))
                & (cmp_df["status"] == "ok")].copy()
    ml["gold_f1"] = ml["gold_f1"].astype(float)
    ml["gold_fpr"] = ml["gold_fpr"].astype(float)
    in_budget = ml["gold_fpr"] <= FPR_BUDGET
    if not in_budget.any():
        raise SystemExit("no model has a threshold within the FPR budget")
    best = ml[in_budget].sort_values(["gold_f1", "gold_fpr"], ascending=[False, True]).iloc[0]
    final = {"model_name": best["model"], "threshold": float(best["threshold"]),
             "fpr_budget": FPR_BUDGET, "features": FEATURE_COLS,
             "tuned_on": "gold (is_attack_ip AND login_success)",
             "direction": "anomaly_score = -decision_function (ip_reputation_baseline: prior probability)",
             "scaler": scaler}
    for name, (kind, estimator) in models.items():
        if kind == "sklearn" and name == best["model"]:
            final["model"] = estimator
    joblib.dump(final, args.model)
    print(f"wrote {args.model} (final model: {best['model']})")

    report["split"] = {"train_rows": len(train), "test_rows": len(test),
                       "test_share": round(test_share, 4), "rule": f"first ceil({SPLIT_RATIO}*n) by (ts, row_id)"}
    report["contamination"] = {
        "train_attack_share": round(full_attack_share, 4),
        "clean_train_rows": int(len(clean_train)),
        "fit_contamination": FIT_CONTAMINATION,
        "policy": "clean-reference fitting (attack rows excluded); contamination = flag-rate intent",
    }
    report["tuned_on"] = "gold (is_attack_ip AND login_success), FPR <= 0.05"
    report["fpr_budget"] = FPR_BUDGET
    report["final_model"] = {"model": best["model"], "gold_f1": float(best["gold_f1"]),
                             "gold_fpr": float(best["gold_fpr"])}
    report["models_beat_baseline"] = bool((ml[in_budget]["gold_f1"] > rule_f1).any())
    report["best_behavioral_gold_f1"] = float(ml[in_budget]["gold_f1"].max())
    report["ip_prior_gold_f1"] = ip_prior_f1
    report["gates"] = "PASS"
    failures = []
    if test_share < 0.15 or test_share > 0.45:
        failures.append(f"test share {test_share:.3f} outside [0.15, 0.45]")
    if float(best["gold_fpr"]) > FPR_BUDGET:
        failures.append(f"final model FPR {best['gold_fpr']:.4f} above budget {FPR_BUDGET}")
    if ml["gold_f1"].isna().any():
        failures.append("NaN gold f1 in comparison")
    if failures:
        report["gates"] = failures

    args.report.write_text(json.dumps(report, indent=2, default=str))
    print(f"report -> {args.report}")

    con.close()
    print(f"models beating rule baseline (gold F1): {report['models_beat_baseline']}")
    print(f"final model: {best['model']} (gold F1={best['gold_f1']:.4f} FPR={best['gold_fpr']:.4f})")
    if failures:
        print("GATE FAILURES:", *failures, sep="\n  - ")
        sys.exit(1)


def plot_confusion_matrices(cm_data: dict, out: Path) -> None:
    n = len(cm_data)
    if not n:
        return
    fig, axes = plt.subplots(1, n, figsize=(4.2 * n, 3.6), squeeze=False)
    for ax, (name, m) in zip(axes[0], cm_data.items()):
        cm = np.array([[m["tn"], m["fp"]], [m["fn"], m["tp"]]])
        ax.imshow(cm, cmap="Blues")
        for i in range(2):
            for j in range(2):
                ax.text(j, i, f"{cm[i, j]:,}", ha="center", va="center",
                        fontsize=14, color="white" if cm[i, j] > cm.max() / 2 else "black")
        ax.set_xticks([0, 1], ["neg", "pos"])
        ax.set_yticks([0, 1], ["neg", "pos"])
        ax.set_xlabel("predicted")
        ax.set_ylabel("actual")
        ax.set_title(f"{name}\nF1={m['f1']:.3f} FPR={m['fpr']:.3f}")
    fig.suptitle("Confusion matrices at tuned threshold (gold label, test set)")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
