#!/usr/bin/env python3
"""Train sidequest models on the unified parsed auth logs.

This experiment is intentionally separate from the main RBA pipeline:
the unified logs in logs-lab/events.parquet do not carry attack/ATO labels,
so the honest supervised target here is failed login detection.

Design follows the main project where it still makes sense:
  - features use only strictly earlier events from the same user
  - split is per-user chronological (earlier events train, later test)
  - threshold tuning respects a false-positive budget

Artifacts:
  logs-lab/featured_events.parquet
  logs-lab/reports/model_comparison.csv
  logs-lab/reports/evaluation.json
  logs-lab/models/best_model.joblib

Usage:
  venv/bin/python logs-lab/train_models.py
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["BLIS_NUM_THREADS"] = "1"

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "events.parquet"
DEFAULT_FEATURES = ROOT / "featured_events.parquet"
DEFAULT_REPORT_DIR = ROOT / "reports"
DEFAULT_MODEL_DIR = ROOT / "models"
DEFAULT_COMPARISON = DEFAULT_REPORT_DIR / "model_comparison.csv"
DEFAULT_REPORT = DEFAULT_REPORT_DIR / "evaluation.json"
DEFAULT_MODEL = DEFAULT_MODEL_DIR / "best_model.joblib"

SPLIT_TRAIN_RATIO = 0.55
SPLIT_VAL_RATIO = 0.15
FPR_BUDGET = 0.05
SEED = 42

NUMERIC_COLS = [
    "hour",
    "day_of_week",
    "rapid_login_rate_10m",
    "login_frequency_today",
    "prior_failure_rate",
    "minutes_since_prev",
]

BOOL_COLS = [
    "is_night",
    "is_weekend",
    "country_missing",
    "device_missing",
    "os_missing",
    "browser_missing",
    "ip_missing",
    "country_change",
    "device_change",
    "os_change",
    "browser_change",
    "source_change",
    "failed_recently_30m",
    "ip_seen_before",
    "country_seen_before",
    "device_seen_before",
    "os_seen_before",
    "browser_seen_before",
    "source_seen_before",
]

CATEGORICAL_COLS = ["source", "country", "device", "os", "browser"]
HIGH_CARDINALITY = {"device"}  # cap to top-N to avoid one-hot explosion
FEATURE_COLS = NUMERIC_COLS + BOOL_COLS + CATEGORICAL_COLS


def build_feature_sql(path: Path) -> str:
    src = f"read_parquet('{path}')"
    return f"""
    WITH base AS (
        SELECT
            ROW_NUMBER() OVER (ORDER BY user, ts, source, COALESCE(ip, ''), COALESCE(status, '')) AS row_id,
            ts,
            source,
            COALESCE(NULLIF(user, ''), '__missing_user__') AS user_id,
            NULLIF(ip, '') AS ip,
            COALESCE(NULLIF(country, ''), 'unknown') AS country,
            COALESCE(NULLIF(device, ''), 'unknown') AS device,
            COALESCE(NULLIF(os, ''), 'unknown') AS os,
            COALESCE(NULLIF(browser, ''), 'unknown') AS browser,
            success,
            status
        FROM {src}
        WHERE ts IS NOT NULL AND user IS NOT NULL
    ),
    top_devices AS (
        SELECT device
        FROM base
        GROUP BY device
        ORDER BY COUNT(*) DESC
        LIMIT 20
    ),
    capped AS (
        SELECT b.*,
               CASE WHEN t.device IS NOT NULL THEN b.device ELSE 'other' END AS device_capped
        FROM base b
        LEFT JOIN top_devices t ON b.device = t.device
    ),
    ev AS (
        SELECT *,
               ROW_NUMBER() OVER w AS rn,
               LAG(ts) OVER w AS prev_ts,
               LAG(country) OVER w AS prev_country,
               LAG(device_capped) OVER w AS prev_device,
               LAG(os) OVER w AS prev_os,
               LAG(browser) OVER w AS prev_browser,
               LAG(source) OVER w AS prev_source
        FROM capped
        WINDOW w AS (PARTITION BY user_id ORDER BY ts, row_id)
    ),
    fails AS (
        SELECT user_id, ts
        FROM ev
        WHERE NOT success
    ),
    prior_fail AS (
        SELECT e.*, f.ts AS prior_fail_ts
        FROM ev e
        ASOF LEFT JOIN fails f
        ON e.user_id = f.user_id AND e.ts > f.ts
    )
    SELECT
        row_id,
        ts,
        user_id,
        source,
        country,
        device_capped AS device,
        os,
        browser,
        ip,
        success,
        status,
        EXTRACT(HOUR FROM ts) AS hour,
        dayofweek(ts) AS day_of_week,
        EXTRACT(HOUR FROM ts) IN (22, 23, 0, 1, 2, 3, 4, 5) AS is_night,
        dayofweek(ts) IN (0, 6) AS is_weekend,
        country = 'unknown' AS country_missing,
        device_capped = 'unknown' AS device_missing,
        os = 'unknown' AS os_missing,
        browser = 'unknown' AS browser_missing,
        ip IS NULL AS ip_missing,
        CASE WHEN rn = 1 THEN FALSE ELSE country != prev_country END AS country_change,
        CASE WHEN rn = 1 THEN FALSE ELSE device_capped != prev_device END AS device_change,
        CASE WHEN rn = 1 THEN FALSE ELSE os != prev_os END AS os_change,
        CASE WHEN rn = 1 THEN FALSE ELSE browser != prev_browser END AS browser_change,
        CASE WHEN rn = 1 THEN FALSE ELSE source != prev_source END AS source_change,
        prior_fail_ts IS NOT NULL AND ts - prior_fail_ts <= INTERVAL '30 minutes' AS failed_recently_30m,
        COUNT(*) OVER (
            PARTITION BY user_id
            ORDER BY ts
            RANGE BETWEEN INTERVAL '10 minutes' PRECEDING AND CURRENT ROW
            EXCLUDE CURRENT ROW
        ) AS rapid_login_rate_10m,
        ROW_NUMBER() OVER (
            PARTITION BY user_id, CAST(ts AS DATE)
            ORDER BY ts, row_id
        ) - 1 AS login_frequency_today,
        COALESCE(
            SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) OVER (
                PARTITION BY user_id
                ORDER BY ts, row_id
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            )::DOUBLE
            /
            NULLIF(
                COUNT(*) OVER (
                    PARTITION BY user_id
                    ORDER BY ts, row_id
                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                ),
                0
            ),
            0.0
        ) AS prior_failure_rate,
        COALESCE(date_diff('minute', prev_ts, ts), 10080) AS minutes_since_prev,
        ROW_NUMBER() OVER (PARTITION BY user_id, ip ORDER BY ts, row_id) > 1 AS ip_seen_before,
        ROW_NUMBER() OVER (PARTITION BY user_id, country ORDER BY ts, row_id) > 1 AS country_seen_before,
        ROW_NUMBER() OVER (PARTITION BY user_id, device_capped ORDER BY ts, row_id) > 1 AS device_seen_before,
        ROW_NUMBER() OVER (PARTITION BY user_id, os ORDER BY ts, row_id) > 1 AS os_seen_before,
        ROW_NUMBER() OVER (PARTITION BY user_id, browser ORDER BY ts, row_id) > 1 AS browser_seen_before,
        ROW_NUMBER() OVER (PARTITION BY user_id, source ORDER BY ts, row_id) > 1 AS source_seen_before
    FROM prior_fail
    """


def split_sql(feature_path: Path) -> str:
    return f"""
    WITH ev AS (
        SELECT *,
               ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY ts, row_id) AS rn,
               COUNT(*) OVER (PARTITION BY user_id) AS n_events
        FROM read_parquet('{feature_path}')
    )
    SELECT row_id,
           CASE
               WHEN rn <= CEIL({SPLIT_TRAIN_RATIO} * n_events) THEN 'train'
               WHEN rn <= CEIL(({SPLIT_TRAIN_RATIO} + {SPLIT_VAL_RATIO}) * n_events) THEN 'val'
               ELSE 'test'
           END AS split
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
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": fpr,
    }


def tune_threshold(y_true: np.ndarray, scores: np.ndarray, fpr_budget: float = FPR_BUDGET) -> tuple[float, bool]:
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    if len(thresholds) == 0:
        return 0.5, False
    with np.errstate(invalid="ignore", divide="ignore"):
        f1 = 2 * precision[:-1] * recall[:-1] / (precision[:-1] + recall[:-1])
    f1 = np.nan_to_num(f1, nan=0.0)
    negatives = ~y_true.astype(bool)
    order = np.argsort(scores, kind="mergesort")
    sorted_scores = scores[order]
    cum_neg = np.cumsum(negatives[order].astype(np.int64))
    n_neg = int(np.sum(negatives))
    idx = np.searchsorted(sorted_scores, thresholds, side="left")
    neg_below = np.where(idx > 0, cum_neg[np.maximum(idx - 1, 0)], 0)
    fpr = (n_neg - neg_below) / max(n_neg, 1)
    within_budget = bool(np.any(fpr <= fpr_budget))
    cand = (fpr <= fpr_budget) if within_budget else np.ones_like(fpr, dtype=bool)
    best = int(np.argmax(np.where(cand, f1, -np.inf)))
    return float(thresholds[best]), within_budget


def build_supervised_pipeline(estimator) -> Pipeline:
    pre = ColumnTransformer(
        transformers=[
            ("num", Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
            ]), NUMERIC_COLS),
            ("bool", "passthrough", BOOL_COLS),
            ("cat", Pipeline([
                ("imputer", SimpleImputer(strategy="constant", fill_value="unknown")),
                ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
            ]), CATEGORICAL_COLS),
        ]
    )
    return Pipeline([("pre", pre), ("model", estimator)])


def evaluate_supervised(name: str, pipeline: Pipeline, train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame) -> tuple[dict, dict]:
    X_train = train[FEATURE_COLS]
    X_val = val[FEATURE_COLS]
    X_test = test[FEATURE_COLS]
    y_train = (~train["success"]).to_numpy(dtype=bool)
    y_val = (~val["success"]).to_numpy(dtype=bool)
    y_test = (~test["success"]).to_numpy(dtype=bool)

    t0 = time.time()
    pipeline.fit(X_train, y_train)
    fit_s = time.time() - t0
    val_scores = pipeline.predict_proba(X_val)[:, 1]
    threshold, within_budget = tune_threshold(y_val, val_scores)
    scores = pipeline.predict_proba(X_test)[:, 1]
    metrics = metrics_at(y_test, scores, threshold)
    result = {
        "model": name,
        "status": "ok",
        "threshold": threshold,
        "within_fpr_budget": within_budget,
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "f1": metrics["f1"],
        "fpr": metrics["fpr"],
        "roc_auc": float(roc_auc_score(y_test, scores)),
        "pr_auc": float(average_precision_score(y_test, scores)),
        "fit_seconds": fit_s,
        "note": "supervised failed-login classifier; threshold tuned on val, metrics on test",
    }
    artifact = {
        "pipeline": pipeline,
        "threshold": threshold,
        "features": FEATURE_COLS,
        "label": "not success",
        "metrics": result,
    }
    return result, artifact


def evaluate_isolation_forest(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame) -> tuple[dict, dict]:
    normal_train = train[train["success"]].reset_index(drop=True)
    base_pre = ColumnTransformer(
        transformers=[
            ("num", Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
            ]), NUMERIC_COLS),
            ("bool", "passthrough", BOOL_COLS),
            ("cat", Pipeline([
                ("imputer", SimpleImputer(strategy="constant", fill_value="unknown")),
                ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
            ]), CATEGORICAL_COLS),
        ]
    )
    X_fit = base_pre.fit_transform(normal_train[FEATURE_COLS])
    X_val = base_pre.transform(val[FEATURE_COLS])
    X_test = base_pre.transform(test[FEATURE_COLS])
    y_val = (~val["success"]).to_numpy(dtype=bool)
    y_test = (~test["success"]).to_numpy(dtype=bool)

    model = IsolationForest(contamination=0.10, random_state=SEED, n_jobs=-1)
    t0 = time.time()
    model.fit(X_fit)
    fit_s = time.time() - t0
    val_scores = -model.decision_function(X_val)
    threshold, within_budget = tune_threshold(y_val, val_scores)
    scores = -model.decision_function(X_test)
    metrics = metrics_at(y_test, scores, threshold)
    result = {
        "model": "isolation_forest",
        "status": "ok",
        "threshold": threshold,
        "within_fpr_budget": within_budget,
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "f1": metrics["f1"],
        "fpr": metrics["fpr"],
        "roc_auc": float(roc_auc_score(y_test, scores)),
        "pr_auc": float(average_precision_score(y_test, scores)),
        "fit_seconds": fit_s,
        "note": "fit on successful train events only; threshold tuned on val, metrics on test",
    }
    artifact = {
        "preprocessor": base_pre,
        "model": model,
        "threshold": threshold,
        "features": FEATURE_COLS,
        "label": "not success",
        "metrics": result,
    }
    return result, artifact


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    ap.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    args = ap.parse_args()

    args.features.parent.mkdir(parents=True, exist_ok=True)
    args.comparison.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.model.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(":memory:")
    con.execute("SET threads=2")

    print(f"loading unified events from {args.input} ...", flush=True)
    total_rows = con.execute(f"SELECT COUNT(*) FROM read_parquet('{args.input}')").fetchone()[0]
    print(f"events: {total_rows:,}", flush=True)

    sql = build_feature_sql(args.input)
    t0 = time.time()
    con.execute(f"""
        COPY ({sql})
        TO '{args.features}'
        (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    print(f"wrote {args.features} ({time.time() - t0:.1f}s)", flush=True)

    cols = ", ".join(FEATURE_COLS + ["success", "row_id", "user_id", "source"])
    split_cte = split_sql(args.features)
    train_sql = f"WITH sp AS ({split_cte}) SELECT {cols} FROM read_parquet('{args.features}') t JOIN sp s USING(row_id) WHERE s.split='train'"
    val_sql = f"WITH sp AS ({split_cte}) SELECT {cols} FROM read_parquet('{args.features}') t JOIN sp s USING(row_id) WHERE s.split='val'"
    test_sql = f"WITH sp AS ({split_cte}) SELECT {cols} FROM read_parquet('{args.features}') t JOIN sp s USING(row_id) WHERE s.split='test'"

    print("loading train split ...", flush=True)
    train = con.execute(train_sql).df()
    print("loading val split ...", flush=True)
    val = con.execute(val_sql).df()
    print("loading test split ...", flush=True)
    test = con.execute(test_sql).df()
    y_train = ~train["success"]
    y_val = ~val["success"]
    y_test = ~test["success"]
    print(f"split: train {len(train):,} / val {len(val):,} / test {len(test):,}", flush=True)
    print(f"failure share: train {y_train.mean():.4f} / val {y_val.mean():.4f} / test {y_test.mean():.4f}", flush=True)

    comparisons: list[dict] = []
    artifacts: dict[str, dict] = {}

    supervised = {
        "logistic_regression": build_supervised_pipeline(
            LogisticRegression(max_iter=1000, class_weight="balanced", random_state=SEED)
        ),
        "hist_gradient_boosting": build_supervised_pipeline(
            HistGradientBoostingClassifier(
                max_iter=200,
                learning_rate=0.1,
                max_leaf_nodes=31,
                class_weight="balanced",
                early_stopping=True,
                validation_fraction=0.1,
                n_iter_no_change=20,
                random_state=SEED,
            )
        ),
    }

    for name, pipeline in supervised.items():
        print(f"training {name} ...", flush=True)
        result, artifact = evaluate_supervised(name, pipeline, train, val, test)
        comparisons.append(result)
        artifacts[name] = artifact
        print(
            f"{name:<24} F1={result['f1']:.4f} "
            f"P={result['precision']:.4f} R={result['recall']:.4f} "
            f"FPR={result['fpr']:.4f} ROC-AUC={result['roc_auc']:.4f}",
            flush=True,
        )

    print("training isolation_forest ...", flush=True)
    result, artifact = evaluate_isolation_forest(train, val, test)
    comparisons.append(result)
    artifacts["isolation_forest"] = artifact
    print(
        f"isolation_forest         F1={result['f1']:.4f} "
        f"P={result['precision']:.4f} R={result['recall']:.4f} "
        f"FPR={result['fpr']:.4f} ROC-AUC={result['roc_auc']:.4f}",
        flush=True,
    )

    comparison_df = pd.DataFrame(comparisons).sort_values(
        ["f1", "roc_auc", "pr_auc"], ascending=[False, False, False]
    )
    comparison_df.to_csv(args.comparison, index=False)
    print(f"wrote {args.comparison}", flush=True)

    best_name = comparison_df.iloc[0]["model"]
    joblib.dump(artifacts[best_name], args.model)
    print(f"wrote {args.model} ({best_name})", flush=True)

    total_rows = len(train) + len(val) + len(test)
    all_users = sorted(set(train["user_id"].unique()) | set(test["user_id"].unique()))
    all_sources = sorted(set(train["source"].unique()) | set(test["source"].unique()))
    report = {
        "dataset": {
            "input": str(args.input),
            "featured": str(args.features),
            "rows": total_rows,
            "users": len(all_users),
            "sources": all_sources,
        },
        "label": {
            "target": "not success",
            "train_failure_share": round(float(y_train.mean()), 4),
            "val_failure_share": round(float(y_val.mean()), 4),
            "test_failure_share": round(float(y_test.mean()), 4),
            "caveat": "This sidequest evaluates failed-login detection on unified auth logs, not attack/ATO labels.",
        },
        "split": {
            "rule": f"first ceil({SPLIT_TRAIN_RATIO}*n) -> train, next ceil({SPLIT_VAL_RATIO}*n) -> val, rest -> test, per user by (ts, row_id)",
            "train_rows": len(train),
            "val_rows": len(val),
            "test_rows": len(test),
            "threshold_tuning": "threshold tuned on val split; precision/recall/f1/fpr reported on test split",
        },
        "features": {
            "numeric": NUMERIC_COLS,
            "boolean": BOOL_COLS,
            "categorical": CATEGORICAL_COLS,
            "leakage_avoidance": "status is carried for audit only and excluded from training features",
        },
        "fpr_budget": FPR_BUDGET,
        "models": comparisons,
        "winner": best_name,
    }
    args.report.write_text(json.dumps(report, indent=2))
    print(f"wrote {args.report}", flush=True)


if __name__ == "__main__":
    main()
