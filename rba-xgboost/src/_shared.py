#!/usr/bin/env python3
"""Shared evaluation code used by the model pipeline (src/07).

Loads the same features, splits per-user chronologically, and evaluates with
the same metrics/threshold tuning so all models stay directly comparable.
"""
from pathlib import Path

import numpy as np
from sklearn.metrics import precision_recall_curve

SEED = 42
SPLIT_RATIO = 0.7
FPR_BUDGET = 0.05
CHALLENGE_RATES = [0.005, 0.01, 0.02, 0.05, 0.10, 0.20]
FEATURE_COLS = [
    "is_night", "is_weekend", "country_change", "device_change",
    "failed_recently", "rapid_login_rate", "login_frequency_today",
    "hour_sin", "hour_cos",
    "geo_unreliable", "is_generator_bot", "ua_os_conflict",
    "is_private_ip", "rtt_missing", "is_vlc",
    "ip_seen_before", "country_seen_before", "asn_seen_before",
    "device_seen_before", "os_seen_before", "browser_seen_before",
    "hours_since_last_login", "login_frequency_24h",
    "hour_deviation", "unique_ips_7d", "impossible_travel",
]


def split_sql(features: Path) -> str:
    """Per-user chronological split: first ceil(0.7*n) events -> train."""
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
    """Best-F1 threshold subject to FPR <= fpr_budget (else the min-FPR one)."""
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
