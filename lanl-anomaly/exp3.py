#!/usr/bin/env python3
"""exp3.py - IF anomaly score as Feature 22 for LGB (RUN 12a/12b)

Adds IF decision_function() score as Feature 22 to the 21-feature LGB model.
Compares IF trained on all data vs normal-only.

Optimizations vs original:
  - pairs_last_100 computed in DuckDB SQL (no Python loop, no second connection)
  - result dict deleted immediately after column extraction (~5.8GB freed)
  - X_22 filled in-place (no column_stack copy)
  - StandardScaler fit only on train set

Usage:
  ./venv/bin/python exp3.py                  # RUN 12a: IF trained on all data
  ./venv/bin/python exp3.py --normal-only    # RUN 12b: IF trained on normal events only
"""
import argparse
import time
import os
import numpy as np
import duckdb
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("--normal-only", action="store_true",
                help="Train IF on normal events only (exclude red from training)")
cli_args = ap.parse_args()

t_start = time.time()
step_timings = []

def mem_mb():
    import psutil
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

def section_header(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

def timer_start():
    return time.time()

def timer_end(label, t0):
    dt = time.time() - t0
    step_timings.append((label, dt))
    return dt

def eval_it(name, scores, y_true):
    roc = roc_auc_score(y_true, scores)
    pr = average_precision_score(y_true, scores)
    prec, rec, thr = precision_recall_curve(y_true, scores)
    f1 = np.nan_to_num(2*prec*rec/(prec+rec))
    best = np.argmax(f1[:-1])
    pred = scores >= thr[best]
    tp = int(np.sum(pred & y_true))
    fp = int(np.sum(pred & ~y_true))
    print(f"  {name:<22} ROC={roc:.4f} PR-AUC={pr:.4f} F1={f1[best]:.4f} TP={tp} FP={fp} thr={thr[best]:.6f}")
    return {'roc': roc, 'pr': pr, 'f1': f1[best], 'tp': tp, 'fp': fp, 'thr': thr[best]}


SQL_QUERY = """
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
),
user_with_pairs AS (
    SELECT uv.*,
        COUNT(DISTINCT uv.dst_computer) OVER (
            PARTITION BY uv.src_user
            ORDER BY uv.time, uv.dst_user, uv.auth_type, uv.logon_type,
                     uv.orientation, uv.result
            ROWS BETWEEN 99 PRECEDING AND CURRENT ROW
        ) AS pairs_last_100
    FROM user_velocity uv
)
SELECT uwp.dst_first, uwp.src_first, uwp.hour_events, uwp.user_events,
       CAST(uwp.dst_prior_events AS BIGINT) AS dst_prior_events,
       CAST(uwp.fail_1h AS BIGINT) AS fail_1h,
       CAST(uwp.vel_1h AS BIGINT) AS vel_1h,
       uwp.hour, uwp.is_red, uwp.src_computer, uwp.src_user,
       CASE WHEN ROW_NUMBER() OVER (PARTITION BY uwp.src_user, uwp.src_computer, uwp.dst_computer
            ORDER BY uwp.time, uwp.dst_user, uwp.auth_type, uwp.logon_type, uwp.orientation, uwp.result) = 1
            THEN 1.0 ELSE 0.0 END AS pair_first,
       CASE WHEN ROW_NUMBER() OVER (PARTITION BY uwp.src_computer, uwp.dst_computer
            ORDER BY uwp.time, uwp.src_user, uwp.dst_user, uwp.auth_type, uwp.logon_type, uwp.orientation, uwp.result) = 1
            THEN 1.0 ELSE 0.0 END AS src_dst_pair_first,
       CAST(uwp.fail_1h AS DOUBLE) / (CAST(uwp.vel_1h AS DOUBLE) + 1.0) AS fail_rate,
       CASE WHEN uwp.dst_first = 1 AND uwp.is_ntlm THEN 1.0 ELSE 0.0 END AS dst_first_x_ntlm,
       uwp.is_ntlm,
       CAST(ROW_NUMBER() OVER (PARTITION BY uwp.src_user, uwp.src_computer, uwp.dst_computer
            ORDER BY uwp.time, uwp.dst_user, uwp.auth_type, uwp.logon_type, uwp.orientation, uwp.result) AS DOUBLE) AS pair_rank,
       CAST(pc.pair_events AS DOUBLE) / ut.total AS pair_freq_ratio,
       CASE WHEN rh.src_user IS NOT NULL THEN 1.0 ELSE 0.0 END AS is_rare_hour,
       COALESCE(uwp.pair_interval / (uwp.user_avg_pair_interval + 1), 0.0) AS pair_interval_ratio,
       COALESCE((uwp.time_since_last - uwp.iat_mean) / (uwp.iat_std + 1e-6), 0.0) AS iat_zscore,
       CAST(uwp.auth_count_1h AS DOUBLE) / (CAST(uwp.auth_count_24h AS DOUBLE) + 1.0) AS velocity_ratio,
       mp.machine_popularity,
       uwp.lstm_surprisal,
       uwp.lstm_ae_recon_error,
       CAST(uwp.auth_count_1h AS DOUBLE) AS auth_count_1h,
       CAST(uwp.auth_count_24h AS DOUBLE) AS auth_count_24h,
       uwp.pairs_last_100
FROM user_with_pairs uwp
JOIN user_totals ut ON uwp.src_user = ut.src_user
JOIN pair_counts pc ON uwp.src_user = pc.src_user
    AND uwp.src_computer = pc.src_computer
    AND uwp.dst_computer = pc.dst_computer
JOIN machine_pop mp ON uwp.dst_computer = mp.dst_computer
LEFT JOIN rare_hours rh ON uwp.src_user = rh.src_user AND uwp.hour = rh.hour
ORDER BY uwp.time, uwp.src_user, uwp.dst_user, uwp.src_computer, uwp.dst_computer,
         uwp.auth_type, uwp.logon_type, uwp.orientation, uwp.result
"""


# ============================================================
# STEP 1: SQL CTE chain (pairs_last_100 now computed in SQL)
# ============================================================
section_header("STEP 1: LOAD FEATURES (SQL includes pairs_last_100)")
t0 = timer_start()

DB_PATH = 'data/raw/lanl/lanl.duckdb'
con = duckdb.connect(DB_PATH, read_only=True)
con.execute("SET threads = 1")
con.execute("SET memory_limit = '6GB'")
con.execute("SET preserve_insertion_order = false")

cur = con.cursor()
n = cur.execute("SELECT COUNT(*) FROM feat").fetchone()[0]
print(f"  Row count: {n:,}")

cur.execute(SQL_QUERY)
col_names = [d[0] for d in cur.description]
print(f"  Columns: {len(col_names)} (includes pairs_last_100 from SQL)")

result = {}
for name in col_names:
    if name == 'is_red':
        result[name] = np.empty(n, dtype=bool)
    elif name in ('src_user', 'src_computer'):
        result[name] = np.empty(n, dtype=object)
    else:
        result[name] = np.empty(n, dtype=np.float64)

batch_size = 500_000
filled = 0
while filled < n:
    rows = cur.fetchmany(batch_size)
    if not rows:
        break
    batch_arr = np.array(rows, dtype=object)
    blen = len(rows)
    for j, name in enumerate(col_names):
        result[name][filled:filled+blen] = batch_arr[:, j]
    filled += blen
    del batch_arr, rows
    if filled % 2_000_000 == 0 or filled < batch_size:
        print(f"    fetched {filled:>10,}/{n:,} rows  RSS={mem_mb():.0f}MB")
cur.close()
con.close()
import gc; gc.collect()

y = result['is_red'].astype(bool)
n = len(y)
src_users = result['src_user'].copy()
n_red = int(y.sum())
print(f"  Rows: {n:,}  Red: {n_red}")
print(f"  RAM: {mem_mb():.0f} MB")
timer_end("STEP 1: SQL query (with pairs_last_100)", t0)

# ============================================================
# STEP 2: Build 21 features from result dict, then DELETE result
# ============================================================
section_header("STEP 2: BUILD 21 FEATURES + DELETE result dict")
t0 = timer_start()

feat9 = ['dst_first', 'src_first', 'hour_events', 'user_events',
         'dst_prior_events', 'fail_1h', 'vel_1h', 'hour', 'is_ntlm']
X_raw = np.column_stack([result[k].astype(np.float32) for k in feat9])

X_9 = np.empty((n, 9), dtype=np.float32)
X_9[:, 0] = X_raw[:, 0]
X_9[:, 1] = X_raw[:, 1]
ue = np.maximum(X_raw[:, 3], 1)
X_9[:, 2] = X_raw[:, 2] / ue
X_9[:, 3] = X_raw[:, 4]
X_9[:, 4] = X_raw[:, 5]
X_9[:, 5] = X_raw[:, 6]
h_rad = X_raw[:, 7] / 24.0 * 2 * np.pi
X_9[:, 6] = np.sin(h_rad)
X_9[:, 7] = np.cos(h_rad)
X_9[:, 8] = X_raw[:, 8]
del X_raw, ue, h_rad

pair_first = result['pair_first'].astype(np.float32)
src_dst_pair_first = result['src_dst_pair_first'].astype(np.float32)
fail_rate = result['fail_rate'].astype(np.float32)
dst_first_x_ntlm = result['dst_first_x_ntlm'].astype(np.float32)

X_13 = np.column_stack([X_9, pair_first.reshape(-1,1), src_dst_pair_first.reshape(-1,1),
                         fail_rate.reshape(-1,1), dst_first_x_ntlm.reshape(-1,1)])
del X_9, pair_first, src_dst_pair_first, fail_rate, dst_first_x_ntlm

pair_rank_raw = result['pair_rank'].astype(np.float32)
pair_rank = np.log1p(pair_rank_raw)
X_14 = np.column_stack([X_13, pair_rank.reshape(-1,1)])
del X_13, pair_rank_raw, pair_rank

pair_freq_ratio = result['pair_freq_ratio'].astype(np.float32)
is_rare_hour = result['is_rare_hour'].astype(np.float32)
lstm_ae_recon_error = result['lstm_ae_recon_error'].astype(np.float64)

X_16 = np.column_stack([X_14, pair_freq_ratio.reshape(-1,1), is_rare_hour.reshape(-1,1)])
del X_14, pair_freq_ratio, is_rare_hour

pairs_last_100 = result['pairs_last_100'].astype(np.float32)
iat_zscore = result['iat_zscore'].astype(np.float32)
velocity_ratio = result['velocity_ratio'].astype(np.float32)
machine_popularity = result['machine_popularity'].astype(np.float32)

X_21 = np.column_stack([X_16, pairs_last_100.reshape(-1,1),
                         iat_zscore.reshape(-1,1), velocity_ratio.reshape(-1,1),
                         machine_popularity.reshape(-1,1), lstm_ae_recon_error.reshape(-1,1).astype(np.float32)])
fnames21 = ['dst_first','src_first','hour_ratio','dst_prior_events','fail_1h',
            'vel_1h','hour_sin','hour_cos','is_ntlm',
            'pair_first','src_dst_pair_first','fail_rate','dst_first_x_ntlm',
            'log_pair_rank','pair_freq_ratio','is_rare_hour','pairs_last_100',
            'iat_zscore','velocity_ratio','machine_popularity','lstm_ae_recon_error']

# DELETE result dict immediately — saves ~5.8GB
del result, X_16, pairs_last_100, iat_zscore, velocity_ratio, machine_popularity
import gc; gc.collect()

print(f"  X_21 shape={X_21.shape}  {X_21.nbytes/1024/1024:.0f} MB")
print(f"  RAM after result del: {mem_mb():.0f} MB")
assert X_21.shape == (n, 21)
assert not np.any(np.isnan(X_21))
assert not np.any(np.isinf(X_21))
timer_end("STEP 2: Feature build + result del", t0)

# ============================================================
# STEP 3: Train/test split
# ============================================================
section_header("STEP 3: TRAIN/TEST SPLIT")
t0 = timer_start()
gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
for tr_idx, te_idx in gss.split(X_21, y, groups=src_users):
    pass

y_train, y_test = y[tr_idx], y[te_idx]
n_train_red = int(y_train.sum())
n_test_red = int(y_test.sum())
assert n_train_red + n_test_red == 702, f"Red split mismatch: {n_train_red}+{n_test_red} != 702"
assert n_test_red == 240, f"Expected 240 test red, got {n_test_red}"
print(f"  Train: {len(tr_idx):,} rows ({n_train_red} red)")
print(f"  Test:  {len(te_idx):,} rows ({n_test_red} red)")
timer_end("STEP 3: Split", t0)

# ============================================================
# STEP 4: Train IF + compute scores as Feature 22
# ============================================================
section_header("STEP 4: TRAIN IF + ADD SCORE AS FEATURE 22")
t0 = timer_start()

# Scale only train set for IF fit (not full 30M)
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_21[tr_idx])
print(f"  Scaler fit on train: {X_train_scaled.shape}  RAM={mem_mb():.0f}MB")

contamination = 702 / 29_900_000

if cli_args.normal_only:
    mask_normal = y_train == 0
    X_train_if = X_train_scaled[mask_normal]
    print(f"  IF training: {len(X_train_if):,} normal events (excluded {n_train_red} red)")
else:
    X_train_if = X_train_scaled
    print(f"  IF training: {len(X_train_if):,} events (all data)")

t_if = time.time()
if_model = IsolationForest(
    n_estimators=200,
    max_samples=256,
    contamination=contamination,
    random_state=42,
    n_jobs=-1,
    verbose=0
)
if_model.fit(X_train_if)
print(f"  IF train: {time.time()-t_if:.1f}s")

del X_train_scaled, X_train_if
import gc; gc.collect()

# Score full dataset in chunks to avoid 2.3GB scaled copy
print(f"  Scoring full dataset in chunks...")
t_score = time.time()
if_scores_all = np.empty(n, dtype=np.float64)
chunk_size = 2_000_000
for start in range(0, n, chunk_size):
    end = min(start + chunk_size, n)
    X_chunk_scaled = scaler.transform(X_21[start:end])
    if_scores_all[start:end] = if_model.decision_function(X_chunk_scaled)
    del X_chunk_scaled
    if end < n:
        print(f"    scored {end:,}/{n:,}  RSS={mem_mb():.0f}MB")
print(f"  IF score all: {time.time()-t_score:.1f}s")

if_scores_test = if_scores_all[te_idx]
print(f"  IF scores: min={if_scores_all.min():.4f} max={if_scores_all.max():.4f} mean={if_scores_all.mean():.4f}")
print(f"  IF test red mean: {if_scores_test[y_test].mean():.4f}")
print(f"  IF test benign mean: {if_scores_test[~y_test].mean():.4f}")

print("\n  IF standalone (test set):")
if_eval = eval_it("IF-standalone", -if_scores_test, y_test)

del scaler
import gc; gc.collect()
timer_end("STEP 4: IF scoring", t0)

# ============================================================
# STEP 5: Build X_22 in-place + train LGB
# ============================================================
section_header("STEP 5: BUILD X_22 IN-PLACE + TRAIN LGB")
t0 = timer_start()

# In-place fill: avoid column_stack copy
X_22 = np.empty((n, 22), dtype=np.float32)
X_22[:, :21] = X_21
X_22[:, 21] = if_scores_all.astype(np.float32)
fnames22 = fnames21 + ['if_anomaly_score']

del X_21, if_scores_all
import gc; gc.collect()
print(f"  X_22 shape={X_22.shape}  RAM={mem_mb():.0f}MB")

# Baseline: 21 features (same as RUN 9)
t_lgb = time.time()
lgb_21 = lgb.LGBMClassifier(
    num_leaves=63, learning_rate=0.03, n_estimators=500,
    scale_pos_weight=3, min_child_samples=100,
    reg_alpha=0.5, reg_lambda=5.0,
    random_state=42, n_jobs=-1, verbose=-1
)
lgb_21.fit(X_22[tr_idx, :21], y_train)
lgb_21_test = lgb_21.predict_proba(X_22[te_idx, :21])[:, 1]
print(f"  LGB-21 train: {time.time()-t_lgb:.1f}s")

# With IF: 22 features
t_lgb = time.time()
lgb_22 = lgb.LGBMClassifier(
    num_leaves=63, learning_rate=0.03, n_estimators=500,
    scale_pos_weight=3, min_child_samples=100,
    reg_alpha=0.5, reg_lambda=5.0,
    random_state=42, n_jobs=-1, verbose=-1
)
lgb_22.fit(X_22[tr_idx], y_train)
lgb_22_test = lgb_22.predict_proba(X_22[te_idx])[:, 1]
print(f"  LGB-22 train: {time.time()-t_lgb:.1f}s")
timer_end("STEP 5: LGB training", t0)

# ============================================================
# STEP 6: EVALUATE
# ============================================================
section_header("STEP 6: EVALUATION")
t0 = timer_start()

print(f"  Test set: {len(te_idx):,} rows ({n_test_red} red)\n")

print("  IF standalone:")
if_eval = eval_it("IF-standalone", -if_scores_test, y_test)

print("\n  LGB-21 (baseline, RUN 9):")
lgb21_eval = eval_it("LGB-21feat", lgb_21_test, y_test)

print("\n  LGB-22 (with IF score):")
lgb22_eval = eval_it("LGB-22feat+IF", lgb_22_test, y_test)

# Feature importance for LGB-22
print("\n  Feature importance (LGB-22):")
importances = lgb_22.feature_importances_
sorted_idx = np.argsort(importances)[::-1]
for i, idx in enumerate(sorted_idx):
    bar = '#' * int(50 * importances[idx] / importances[sorted_idx[0]])
    print(f"    {fnames22[idx]:<25} {importances[idx]:>6}  {bar}")

timer_end("STEP 6: Evaluation", t0)

# ============================================================
# SUMMARY
# ============================================================
section_header("SUMMARY")
mode = "all-data" if not cli_args.normal_only else "normal-only"
print(f"  Mode:     IF trained on {mode}")
print(f"  Split:    GroupShuffleSplit(random_state=42)")
print(f"  Test:     {n_test_red} red / {len(te_idx):,} total\n")

print(f"  IF standalone:  ROC={if_eval['roc']:.4f} F1={if_eval['f1']:.4f} TP={if_eval['tp']} FP={if_eval['fp']}")
print(f"  LGB-21 (base):  ROC={lgb21_eval['roc']:.4f} F1={lgb21_eval['f1']:.4f} TP={lgb21_eval['tp']} FP={lgb21_eval['fp']}")
print(f"  LGB-22 (+IF):   ROC={lgb22_eval['roc']:.4f} F1={lgb22_eval['f1']:.4f} TP={lgb22_eval['tp']} FP={lgb22_eval['fp']}")

delta_f1 = lgb22_eval['f1'] - lgb21_eval['f1']
delta_tp = lgb22_eval['tp'] - lgb21_eval['tp']
delta_fp = lgb22_eval['fp'] - lgb21_eval['fp']
print(f"\n  Delta vs baseline:")
print(f"    F1:  {delta_f1:+.4f} ({'W' if delta_f1 > 0 else 'L'})")
print(f"    TP:  {delta_tp:+d} ({'W' if delta_tp > 0 else 'L'})")
print(f"    FP:  {delta_fp:+d} ({'W' if delta_fp < 0 else 'L'})")

total = time.time() - t_start
print(f"\n  TIMING BREAKDOWN")
print(f"  {'─'*50}")
for label, dt in step_timings:
    print(f"    {label:<40} {dt:>7.1f}s  ({100*dt/total:4.1f}%)")
print(f"    {'─'*48}")
print(f"    {'Total':<40} {total:>7.1f}s")
print(f"\n  Total runtime: {total:.1f}s ({total/60:.1f} min)")
