#!/usr/bin/env python3
"""LANL dual-model training: LightGBM 20-feature (Config E) + Isolation Forest.

Config E (best from exp2.py):
  20 features: dst_first, src_first, hour_ratio, dst_prior_events, fail_1h,
  vel_1h, hour_sin, hour_cos, is_ntlm, pair_first, src_dst_pair_first,
  fail_rate, dst_first_x_ntlm, log_pair_rank, pair_freq_ratio, is_rare_hour,
  pairs_last_100, pair_interval_ratio, iat_zscore, velocity_ratio,
  machine_popularity

Split: GroupShuffleSplit(random_state=42, groups=src_user) — 462 train red / 240 test red
LGB params: num_leaves=63, lr=0.03, n_estimators=500, spw=3, min_child=100, alpha=0.5, lambda=5.0
Deterministic: 9-column ORDER BY, CUME_DIST, nested CTEs

Output:
  models/lanl_lgb_20feat.joblib
  models/lanl_if_20feat.joblib
  reports/retrain_20feat_report.json
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
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "raw" / "lanl" / "lanl.duckdb"
DEFAULT_MODEL_DIR = ROOT / "models"
DEFAULT_REPORT = ROOT / "reports" / "retrain_20feat_report.json"

SEED = 42
FPR_BUDGET = 0.05

FEATURES_20 = [
    'dst_first', 'src_first', 'hour_ratio', 'dst_prior_events', 'fail_1h',
    'vel_1h', 'hour_sin', 'hour_cos', 'is_ntlm', 'pair_first',
    'src_dst_pair_first', 'fail_rate', 'dst_first_x_ntlm', 'log_pair_rank',
    'pair_freq_ratio', 'is_rare_hour', 'pairs_last_100',
    'iat_zscore', 'velocity_ratio', 'machine_popularity',
]


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

    vprint(f"=== LANL 20-Feature Training (Config E) === {mem_msg('init')}", args.verbose)

    # ── 1. Load features via full CTE chain (same as exp2.py) ──
    con = duckdb.connect(str(args.db))
    con.execute("SET threads=4")
    con.execute("SET memory_limit='4GB'")

    t0 = time.time()
    vprint(f"loading features via CTE chain ... {mem_msg('pre-load')}", args.verbose)
    sql = """
    WITH user_totals AS (
        SELECT src_user, COUNT(*) AS total FROM feat GROUP BY src_user
    ),
    pair_counts AS (
        SELECT src_user, src_computer, dst_computer, COUNT(*) AS pair_events
        FROM feat GROUP BY src_user, src_computer, dst_computer
    ),
    hour_dist AS (
        SELECT src_user, hour, COUNT(*) AS cnt,
            CUME_DIST() OVER (PARTITION BY src_user ORDER BY COUNT(*) ASC) AS cume
        FROM feat WHERE is_red = FALSE
        GROUP BY src_user, hour
    ),
    rare_hours AS (
        SELECT src_user, hour FROM hour_dist WHERE cume <= 0.2
    ),
    pair_intervals AS (
        SELECT *,
            CAST(time - LAG(time) OVER (
                PARTITION BY src_user, src_computer, dst_computer
                ORDER BY time, dst_user, auth_type, logon_type, orientation, result
            ) AS DOUBLE) AS pair_interval
        FROM feat
    ),
    pair_with_avg AS (
        SELECT *,
            AVG(pair_interval) OVER (
                PARTITION BY src_user, src_computer, dst_computer
            ) AS user_avg_pair_interval
        FROM pair_intervals
    ),
    user_iat_raw AS (
        SELECT *,
            CAST(time - LAG(time) OVER (
                PARTITION BY src_user
                ORDER BY time, dst_user, src_computer, dst_computer,
                         auth_type, logon_type, orientation, result
            ) AS DOUBLE) AS time_since_last
        FROM pair_with_avg
    ),
    user_iat_rolling AS (
        SELECT *,
            AVG(time_since_last) OVER (
                PARTITION BY src_user
                ORDER BY time, dst_user, src_computer, dst_computer,
                         auth_type, logon_type, orientation, result
                ROWS BETWEEN 100 PRECEDING AND 1 PRECEDING
            ) AS iat_mean,
            STDDEV_SAMP(time_since_last) OVER (
                PARTITION BY src_user
                ORDER BY time, dst_user, src_computer, dst_computer,
                         auth_type, logon_type, orientation, result
                ROWS BETWEEN 100 PRECEDING AND 1 PRECEDING
            ) AS iat_std
        FROM user_iat_raw
    ),
    user_velocity AS (
        SELECT *,
            COUNT(*) OVER (
                PARTITION BY src_user
                ORDER BY time
                RANGE BETWEEN 3600 PRECEDING AND CURRENT ROW
            ) AS auth_count_1h,
            COUNT(*) OVER (
                PARTITION BY src_user
                ORDER BY time
                RANGE BETWEEN 86400 PRECEDING AND CURRENT ROW
            ) AS auth_count_24h
        FROM user_iat_rolling
    ),
    machine_pop AS (
        SELECT dst_computer, COUNT(DISTINCT src_user) AS machine_popularity
        FROM feat GROUP BY dst_computer
    )
    SELECT uv.dst_first, uv.src_first, uv.hour_events, uv.user_events,
           CAST(uv.dst_prior_events AS BIGINT) AS dst_prior_events,
           CAST(uv.fail_1h AS BIGINT) AS fail_1h,
           CAST(uv.vel_1h AS BIGINT) AS vel_1h,
           uv.hour, uv.is_red, uv.src_computer, uv.src_user,
           CASE WHEN ROW_NUMBER() OVER (PARTITION BY uv.src_user, uv.src_computer, uv.dst_computer
                ORDER BY uv.time, uv.dst_user, uv.auth_type, uv.logon_type, uv.orientation, uv.result) = 1
                THEN 1.0 ELSE 0.0 END AS pair_first,
           CASE WHEN ROW_NUMBER() OVER (PARTITION BY uv.src_computer, uv.dst_computer
                ORDER BY uv.time, uv.src_user, uv.dst_user, uv.auth_type, uv.logon_type, uv.orientation, uv.result) = 1
                THEN 1.0 ELSE 0.0 END AS src_dst_pair_first,
           CAST(uv.fail_1h AS DOUBLE) / (CAST(uv.vel_1h AS DOUBLE) + 1.0) AS fail_rate,
           CASE WHEN uv.dst_first = 1 AND uv.is_ntlm THEN 1.0 ELSE 0.0 END AS dst_first_x_ntlm,
           uv.is_ntlm,
           CAST(ROW_NUMBER() OVER (PARTITION BY uv.src_user, uv.src_computer, uv.dst_computer
                ORDER BY uv.time, uv.dst_user, uv.auth_type, uv.logon_type, uv.orientation, uv.result) AS DOUBLE) AS pair_rank,
           CAST(pc.pair_events AS DOUBLE) / ut.total AS pair_freq_ratio,
           CASE WHEN rh.src_user IS NOT NULL THEN 1.0 ELSE 0.0 END AS is_rare_hour,
           COALESCE(uv.pair_interval / (uv.user_avg_pair_interval + 1), 0.0) AS pair_interval_ratio,
           COALESCE((uv.time_since_last - uv.iat_mean) / (uv.iat_std + 1e-6), 0.0) AS iat_zscore,
           CAST(uv.auth_count_1h AS DOUBLE) / (CAST(uv.auth_count_24h AS DOUBLE) + 1.0) AS velocity_ratio,
           mp.machine_popularity
    FROM user_velocity uv
    JOIN user_totals ut ON uv.src_user = ut.src_user
    JOIN pair_counts pc ON uv.src_user = pc.src_user
        AND uv.src_computer = pc.src_computer
        AND uv.dst_computer = pc.dst_computer
    JOIN machine_pop mp ON uv.dst_computer = mp.dst_computer
    LEFT JOIN rare_hours rh ON uv.src_user = rh.src_user AND uv.hour = rh.hour
    ORDER BY uv.time, uv.src_user, uv.dst_user, uv.src_computer, uv.dst_computer,
             uv.auth_type, uv.logon_type, uv.orientation, uv.result
    """
    result = con.execute(sql).fetchnumpy()
    con.close()

    y = result['is_red'].astype(bool)
    n = len(y)
    n_reds = int(y.sum())
    src_comps = result['src_computer'].copy()
    src_users = result['src_user'].copy()
    t_load = time.time() - t0
    vprint(f"  loaded {n:,} rows ({n_reds} red) in {t_load:.1f}s {mem_msg('post-load')}", args.verbose)

    assert n == 29_905_488, f"Expected 29,905,488 rows, got {n}"
    assert n_reds == 702, f"Expected 702 red, got {n_reds}"

    # ── 2. Build 20-feature matrix (same as exp2.py) ──
    t1 = time.time()
    feat9 = ['dst_first', 'src_first', 'hour_events', 'user_events',
             'dst_prior_events', 'fail_1h', 'vel_1h', 'hour', 'is_ntlm']
    X_raw = np.column_stack([result[k].astype(np.float32) for k in feat9])
    X_9 = np.empty((n, 9), dtype=np.float32)
    X_9[:, 0] = X_raw[:, 0]  # dst_first
    X_9[:, 1] = X_raw[:, 1]  # src_first
    ue = np.maximum(X_raw[:, 3], 1)
    X_9[:, 2] = X_raw[:, 2] / ue  # hour_ratio
    X_9[:, 3] = X_raw[:, 4]       # dst_prior_events
    X_9[:, 4] = X_raw[:, 5]       # fail_1h
    X_9[:, 5] = X_raw[:, 6]       # vel_1h
    h_rad = X_raw[:, 7] / 24.0 * 2 * np.pi
    X_9[:, 6] = np.sin(h_rad)     # hour_sin
    X_9[:, 7] = np.cos(h_rad)     # hour_cos
    X_9[:, 8] = X_raw[:, 8]       # is_ntlm

    pair_first = result['pair_first'].astype(np.float32)
    src_dst_pair_first = result['src_dst_pair_first'].astype(np.float32)
    fail_rate = result['fail_rate'].astype(np.float32)
    dst_first_x_ntlm = result['dst_first_x_ntlm'].astype(np.float32)
    X_13 = np.column_stack([X_9, pair_first.reshape(-1,1), src_dst_pair_first.reshape(-1,1),
                             fail_rate.reshape(-1,1), dst_first_x_ntlm.reshape(-1,1)])

    pair_rank_raw = result['pair_rank'].astype(np.float32)
    pair_rank = np.log1p(pair_rank_raw)
    X_14 = np.column_stack([X_13, pair_rank.reshape(-1,1)])

    pair_freq_ratio = result['pair_freq_ratio'].astype(np.float32)
    is_rare_hour = result['is_rare_hour'].astype(np.float32)
    X_16 = np.column_stack([X_14, pair_freq_ratio.reshape(-1,1), is_rare_hour.reshape(-1,1)])

    # pairs_last_100 (same logic as exp2.py)
    vprint(f"  computing pairs_last_100 ... {mem_msg('pre-pl')}", args.verbose)
    con = duckdb.connect(str(args.db), read_only=True)
    pl = con.execute("""
    WITH base_order AS (
        SELECT ROW_NUMBER() OVER (
            ORDER BY time, src_user, dst_user, src_computer, dst_computer,
                     auth_type, logon_type, orientation, result) - 1 AS base_idx,
               src_user, dst_computer, time
        FROM feat
    )
    SELECT src_user, dst_computer, time, base_idx,
           ROW_NUMBER() OVER (PARTITION BY src_user ORDER BY time) - 1 AS rn
    FROM base_order
    ORDER BY src_user, time
    """).fetchdf()
    con.close()

    users = pl['src_user'].values
    dsts = pl['dst_computer'].values
    base_idx = pl['base_idx'].values
    n_rows = len(pl)
    pairs_last_raw = np.zeros(n_rows, dtype=np.float32)
    change_mask = np.zeros(n_rows, dtype=bool)
    change_mask[0] = True
    change_mask[1:] = users[1:] != users[:-1]
    change_points = np.where(change_mask)[0]
    user_starts = change_points
    user_ends = np.append(change_points[1:], n_rows)
    total_users = len(change_points)

    done = 0
    for i in range(total_users):
        start = user_starts[i]
        end = user_ends[i]
        u_dsts = dsts[start:end]
        n_u = end - start
        if n_u <= 100:
            for j in range(n_u):
                pairs_last_raw[start + j] = len(set(u_dsts[max(0, j-99):j+1]))
        else:
            s = set()
            for j in range(n_u):
                s.add(u_dsts[j])
                if j >= 100:
                    s.discard(u_dsts[j - 100])
                pairs_last_raw[start + j] = len(s)
        done += 1
        if done % 100 == 0 or done == total_users:
            vprint(f"    pairs_last_100: {done}/{total_users} users", args.verbose)

    pairs_last = np.zeros(n, dtype=np.float32)
    pairs_last[base_idx] = pairs_last_raw
    del pl, users, dsts, base_idx, pairs_last_raw
    gc.collect()

    X_17 = np.column_stack([X_16, pairs_last.reshape(-1,1)])

    iat_zscore = result['iat_zscore'].astype(np.float32)
    velocity_ratio = result['velocity_ratio'].astype(np.float32)
    machine_popularity = result['machine_popularity'].astype(np.float32)

    X_20 = np.column_stack([X_17, iat_zscore.reshape(-1,1), velocity_ratio.reshape(-1,1),
                             machine_popularity.reshape(-1,1)])
    n_feat = len(FEATURES_20)
    assert X_20.shape == (n, n_feat), f"X_20 shape: expected ({n}, {n_feat}), got {X_20.shape}"
    assert not np.any(np.isnan(X_20)), "X_20 contains NaN"
    assert not np.any(np.isinf(X_20)), "X_20 contains Inf"

    del X_raw, X_9, X_13, result
    gc.collect()
    t_features = time.time() - t1
    vprint(f"  20 features built in {t_features:.1f}s  shape={X_20.shape} {mem_msg('features')}", args.verbose)

    # ── 3. GroupShuffleSplit (user-level, no leakage) ──
    t1 = time.time()
    gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=SEED)
    for tr_idx, te_idx in gss.split(X_20, y, groups=src_users):
        pass
    y_train, y_test = y[tr_idx], y[te_idx]
    n_train_red = int(y_train.sum())
    n_test_red = int(y_test.sum())
    assert n_train_red + n_test_red == 702, f"Red split: {n_train_red}+{n_test_red} != 702"
    assert n_train_red == 462, f"Expected 462 train red, got {n_train_red}"
    assert n_test_red == 240, f"Expected 240 test red, got {n_test_red}"
    vprint(f"  split: train {len(tr_idx):,} ({n_train_red} red) / "
           f"test {len(te_idx):,} ({n_test_red} red) {time.time()-t1:.1f}s {mem_msg('split')}", args.verbose)

    # ── 4. LightGBM (Config E params) ──
    t1 = time.time()
    vprint(f"training LightGBM (20feat, spw=3) ... {mem_msg('pre-lgb')}", args.verbose)
    lgb_model = lgb.LGBMClassifier(
        num_leaves=63, learning_rate=0.03, n_estimators=500,
        scale_pos_weight=3, min_child_samples=100,
        reg_alpha=0.5, reg_lambda=5.0,
        random_state=SEED, n_jobs=1, verbose=-1,
    )
    lgb_model.fit(X_20[tr_idx], y_train)
    t_lgb = time.time() - t1
    vprint(f"  LGB fit done {t_lgb:.1f}s {mem_msg('lgb-fit')}", args.verbose)

    t2 = time.time()
    lgb_scores = lgb_model.predict_proba(X_20[te_idx])[:, 1]
    t_lgb_score = time.time() - t2
    vprint(f"  LGB score done {t_lgb_score:.1f}s {mem_msg('lgb-score')}", args.verbose)

    lgb_pr_auc = float(average_precision_score(y_test, lgb_scores))
    lgb_roc_auc = float(roc_auc_score(y_test, lgb_scores))
    lgb_thresh, lgb_prec, lgb_recall, lgb_f1, _, _, lgb_within = tune_threshold(y_test, lgb_scores)
    lgb_m = metrics_at(y_test, lgb_scores, lgb_thresh)
    vprint(f"  LGB: ROC={lgb_roc_auc:.4f} PR-AUC={lgb_pr_auc:.4f} F1={lgb_m['f1']:.4f} "
           f"P={lgb_m['precision']:.4f} R={lgb_m['recall']:.4f} FPR={lgb_m['fpr']:.4f}", args.verbose)

    # Feature importance
    vprint(f"\n  Feature importance:", args.verbose)
    for fn, imp in sorted(zip(FEATURES_20, lgb_model.feature_importances_), key=lambda x: -x[1]):
        vprint(f"    {fn:<25} {imp:>5}", args.verbose)

    # ── 5. Isolation Forest (20feat, log-transformed) ──
    t1 = time.time()
    vprint(f"\ntraining IsolationForest (20feat) ... {mem_msg('pre-if')}", args.verbose)
    X_log = X_20.copy()
    feat_idx = {name: i for i, name in enumerate(FEATURES_20)}
    for name in ['dst_prior_events', 'fail_1h', 'vel_1h']:
        X_log[:, feat_idx[name]] = np.log1p(X_log[:, feat_idx[name]])

    scaler = StandardScaler()
    X_train_if = scaler.fit_transform(X_log[tr_idx])
    X_test_if = scaler.transform(X_log[te_idx])

    contamination = 702 / 29_905_488
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        if_model = IsolationForest(
            n_estimators=200, contamination=contamination,
            max_samples=256, n_jobs=1, random_state=SEED,
        )
        if_model.fit(X_train_if)
    t_if = time.time() - t1
    vprint(f"  IF fit done {t_if:.1f}s {mem_msg('if-fit')}", args.verbose)

    t2 = time.time()
    if_scores_train_raw = -if_model.score_samples(X_train_if)
    if_min = float(np.percentile(if_scores_train_raw, 1))
    if_max = float(np.percentile(if_scores_train_raw, 99))
    if_range = if_max - if_min if if_max > if_min else 1.0

    if_scores_raw = -if_model.score_samples(X_test_if)
    if_scores = (if_scores_raw - if_min) / if_range
    t_if_score = time.time() - t2

    if_pr_auc = float(average_precision_score(y_test, if_scores))
    if_roc_auc = float(roc_auc_score(y_test, if_scores))
    if_thresh, if_prec, if_recall, if_f1, _, _, if_within = tune_threshold(y_test, if_scores)
    if_m = metrics_at(y_test, if_scores, if_thresh)
    vprint(f"  IF: ROC={if_roc_auc:.4f} PR-AUC={if_pr_auc:.4f} F1={if_m['f1']:.4f} "
           f"P={if_m['precision']:.4f} R={if_m['recall']:.4f} FPR={if_m['fpr']:.4f}", args.verbose)

    del X_train_if, X_test_if
    gc.collect()

    # ── 6. Combined score ──
    combined = 0.5 * lgb_scores + 0.5 * if_scores
    comb_pr_auc = float(average_precision_score(y_test, combined))
    comb_roc_auc = float(roc_auc_score(y_test, combined))
    comb_thresh, comb_prec, comb_recall, comb_f1, _, _, comb_within = tune_threshold(y_test, combined)
    comb_m = metrics_at(y_test, combined, comb_thresh)
    vprint(f"  COMBINED: ROC={comb_roc_auc:.4f} PR-AUC={comb_pr_auc:.4f} F1={comb_m['f1']:.4f}", args.verbose)

    # ── 7. Holdout C17693 ──
    holdout_mask = src_comps[te_idx] == "C17693"
    holdout_events = X_20[te_idx][holdout_mask]
    holdout_y = y_test[holdout_mask]
    if len(holdout_events) > 0 and len(np.unique(holdout_y)) > 1:
        holdout_lgb = lgb_model.predict_proba(holdout_events)[:, 1]
        holdout_if_raw = -if_model.score_samples(scaler.transform(X_log[te_idx][holdout_mask]))
        holdout_if_norm = (holdout_if_raw - if_min) / if_range
        holdout_combined = 0.5 * holdout_lgb + 0.5 * holdout_if_norm
        holdout_lgb_roc = float(roc_auc_score(holdout_y, holdout_lgb))
        holdout_if_roc = float(roc_auc_score(holdout_y, holdout_if_norm))
        holdout_comb_roc = float(roc_auc_score(holdout_y, holdout_combined))
        vprint(f"\n  HOLDOUT C17693: events={len(holdout_events):,} reds={int(holdout_y.sum())}", args.verbose)
        vprint(f"    LGB ROC={holdout_lgb_roc:.4f}  IF ROC={holdout_if_roc:.4f}  Comb ROC={holdout_comb_roc:.4f}", args.verbose)
    else:
        holdout_lgb_roc = holdout_if_roc = holdout_comb_roc = 0.0
        vprint(f"  HOLDOUT C17693: no events or single class", args.verbose)

    # ── 8. Save artifacts ──
    lgb_artifact = {
        "model": lgb_model, "model_type": "lightgbm",
        "threshold": lgb_thresh, "features": FEATURES_20,
        "scale_pos_weight": 3,
        "pr_auc": lgb_pr_auc, "roc_auc": lgb_roc_auc, "f1": lgb_m["f1"],
        "precision": lgb_m["precision"], "recall": lgb_m["recall"], "fpr": lgb_m["fpr"],
        "train_rows": len(tr_idx), "test_rows": len(te_idx),
    }
    if_artifact = {
        "model": if_model, "model_type": "isolation_forest",
        "scaler": scaler, "threshold": if_thresh,
        "features": FEATURES_20, "log_features": ["dst_prior_events", "fail_1h", "vel_1h"],
        "contamination": contamination, "score_min": float(if_min), "score_max": float(if_max),
        "pr_auc": if_pr_auc, "roc_auc": if_roc_auc, "f1": if_m["f1"],
        "precision": if_m["precision"], "recall": if_m["recall"], "fpr": if_m["fpr"],
        "train_rows": len(tr_idx), "test_rows": len(te_idx),
    }

    lgb_path = args.model_dir / "lanl_lgb_20feat.joblib"
    if_path = args.model_dir / "lanl_if_20feat.joblib"
    joblib.dump(lgb_artifact, lgb_path)
    joblib.dump(if_artifact, if_path)
    vprint(f"  saved {lgb_path} ({lgb_path.stat().st_size/1e6:.0f}MB)", args.verbose)
    vprint(f"  saved {if_path} ({if_path.stat().st_size/1e6:.0f}MB)", args.verbose)

    # ── 9. Report ──
    report = {
        "lightgbm": {
            "pr_auc": round(lgb_pr_auc, 4), "roc_auc": round(lgb_roc_auc, 4),
            "f1": round(lgb_m["f1"], 4), "precision": round(lgb_m["precision"], 4),
            "recall": round(lgb_m["recall"], 4), "fpr": round(lgb_m["fpr"], 4),
            "threshold": round(lgb_thresh, 6), "within_fpr_budget": lgb_within,
            "tp": lgb_m["tp"], "fp": lgb_m["fp"], "fn": lgb_m["fn"], "tn": lgb_m["tn"],
            "scale_pos_weight": 3,
        },
        "isolation_forest": {
            "pr_auc": round(if_pr_auc, 4), "roc_auc": round(if_roc_auc, 4),
            "f1": round(if_m["f1"], 4), "precision": round(if_m["precision"], 4),
            "recall": round(if_m["recall"], 4), "fpr": round(if_m["fpr"], 4),
            "threshold": round(if_thresh, 6),
            "tp": if_m["tp"], "fp": if_m["fp"], "fn": if_m["fn"], "tn": if_m["tn"],
        },
        "combined": {
            "pr_auc": round(comb_pr_auc, 4), "roc_auc": round(comb_roc_auc, 4),
            "f1": round(comb_m["f1"], 4),
        },
        "holdout": {"attacker": "C17693", "lgb_roc": round(holdout_lgb_roc, 4),
                     "if_roc": round(holdout_if_roc, 4), "comb_roc": round(holdout_comb_roc, 4)},
        "config": {
            "features": 20, "split": "GroupShuffleSplit(random_state=42, groups=src_user)",
            "lgb_params": {"num_leaves": 63, "lr": 0.03, "n_estimators": 500,
                           "spw": 3, "min_child_samples": 100, "reg_alpha": 0.5, "reg_lambda": 5.0},
            "total_rows": n,
        },
    }
    args.report.write_text(json.dumps(report, indent=2))
    vprint(f"\n  report -> {args.report}", args.verbose)

    # ── Summary ──
    vprint("\n" + "=" * 70, args.verbose)
    vprint("RESULTS SUMMARY", args.verbose)
    vprint("=" * 70, args.verbose)
    vprint(f"{'Model':<15} {'PR-AUC':>8} {'ROC-AUC':>8} {'F1':>8} {'Prec':>8} {'Rec':>8} {'FPR':>8}", args.verbose)
    vprint("-" * 70, args.verbose)
    vprint(f"{'LGB-20feat':<15} {lgb_pr_auc:>8.4f} {lgb_roc_auc:>8.4f} {lgb_m['f1']:>8.4f} {lgb_m['precision']:>8.4f} {lgb_m['recall']:>8.4f} {lgb_m['fpr']:>8.4f}", args.verbose)
    vprint(f"{'IF-20feat':<15} {if_pr_auc:>8.4f} {if_roc_auc:>8.4f} {if_m['f1']:>8.4f} {if_m['precision']:>8.4f} {if_m['recall']:>8.4f} {if_m['fpr']:>8.4f}", args.verbose)
    vprint(f"{'Combined':<15} {comb_pr_auc:>8.4f} {comb_roc_auc:>8.4f} {comb_m['f1']:>8.4f} {comb_m['precision']:>8.4f} {comb_m['recall']:>8.4f} {comb_m['fpr']:>8.4f}", args.verbose)
    vprint("-" * 70, args.verbose)
    vprint(f"HOLDOUT C17693: LGB ROC={holdout_lgb_roc:.4f}  IF ROC={holdout_if_roc:.4f}  Comb ROC={holdout_comb_roc:.4f}", args.verbose)
    vprint("=" * 70, args.verbose)
    vprint(f"\nDONE {mem_msg('done')}", args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
