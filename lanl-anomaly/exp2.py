#!/usr/bin/env python3
"""exp2.py - Behavioral baseline features for identity anomaly detection.

Configs:
  A: 14feat baseline (same as exp1 F)
  B: 16feat (+pair_freq_ratio, +is_rare_hour)
  C: 17feat (+pairs_last_100)
  D: 18feat (+pair_interval_ratio)
  E: 20feat (+iat_zscore, +velocity_ratio, +machine_popularity)

Run: python3 exp2.py | tee logs/exp2.txt
Time: ~10-15 min total
"""
import duckdb
import numpy as np
import time
import psutil
import os
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
import lightgbm as lgb
import joblib
import sys
import warnings
warnings.filterwarnings('ignore')

only_config = None
if '--only' in sys.argv:
    idx = sys.argv.index('--only')
    only_config = sys.argv[idx+1].upper()

os.makedirs("logs", exist_ok=True)
t_start = time.time()

def mem_mb():
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

def section_header(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

# ============================================================
# LOAD ALL FEATURES IN ONE QUERY (memory-efficient)
# ============================================================
section_header("STEP 1: LOAD FEATURES")
t0 = time.time()
print(f"  [{time.time()-t_start:6.1f}s] Connecting to DuckDB...")
con = duckdb.connect('data/raw/lanl/lanl.duckdb', read_only=True)
print(f"  [{time.time()-t_start:6.1f}s] Executing main query (CTEs + window functions)...")
result = con.execute("""
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
""").fetchnumpy()
con.close()

y = result['is_red'].astype(bool)
n = len(y)
src_comps = result['src_computer'].copy()
src_users = result['src_user'].copy()

assert n == 29_905_488, f"Expected 29,905,488 rows, got {n}"
assert int(y.sum()) == 702, f"Expected 702 red, got {int(y.sum())}"
n_red = int(y.sum())
query_time = time.time() - t0
array_bytes = sum(v.nbytes for v in result.values())
print(f"  [{time.time()-t_start:6.1f}s] Query done in {query_time:.1f}s")
print(f"  [{time.time()-t_start:6.1f}s] Rows: {n:,}  Red: {n_red}  Columns: {len(result)}")
print(f"  [{time.time()-t_start:6.1f}s] Raw arrays: {array_bytes/1024/1024:.0f} MB")
print(f"  [{time.time()-t_start:6.1f}s] RAM: {mem_mb():.0f} MB")

# ============================================================
# BUILD BASE 14 FEATURES (same as exp1)
# ============================================================
section_header("STEP 2: BUILD FEATURE MATRICES")
t0 = time.time()
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
fnames13 = ['dst_first','src_first','hour_ratio','dst_prior_events','fail_1h',
            'vel_1h','hour_sin','hour_cos','is_ntlm',
            'pair_first','src_dst_pair_first','fail_rate','dst_first_x_ntlm']

pair_rank_raw = result['pair_rank'].astype(np.float32)
pair_rank = np.log1p(pair_rank_raw)
X_14 = np.column_stack([X_13, pair_rank.reshape(-1,1)])
fnames14 = fnames13 + ['log_pair_rank']

pair_freq_ratio = result['pair_freq_ratio'].astype(np.float32)
is_rare_hour = result['is_rare_hour'].astype(np.float32)
pair_interval_ratio = result['pair_interval_ratio'].astype(np.float32)
iat_zscore = result['iat_zscore'].astype(np.float32)
velocity_ratio = result['velocity_ratio'].astype(np.float32)
machine_popularity = result['machine_popularity'].astype(np.float32)
del result, X_raw, X_9, X_13
import gc; gc.collect()

# Track which configs are trained
trained = {}

build_time = time.time() - t0
print(f"  [{time.time()-t_start:6.1f}s] X_14 built in {build_time:.1f}s  shape={X_14.shape}  {X_14.nbytes/1024/1024:.0f} MB")
print(f"  [{time.time()-t_start:6.1f}s] Features: {fnames14}")
print(f"  [{time.time()-t_start:6.1f}s] RAM: {mem_mb():.0f} MB")

# ============================================================
# TRAIN/TEST SPLIT
# ============================================================
t0 = time.time()
gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
for tr_idx, te_idx in gss.split(X_14, y, groups=src_users):
    pass
y_train, y_test = y[tr_idx], y[te_idx]
n_train_red = int(y_train.sum())
n_test_red = int(y_test.sum())
assert n_train_red + n_test_red == 702, f"Red split mismatch: {n_train_red}+{n_test_red} != 702"
assert n_test_red == 240, f"Expected 240 test red, got {n_test_red}"
assert n_train_red == 462, f"Expected 462 train red, got {n_train_red}"
split_time = time.time() - t0
print(f"\n  [{time.time()-t_start:6.1f}s] Train/Test split done in {split_time:.2f}s")
print(f"  [{time.time()-t_start:6.1f}s] Train: {len(tr_idx):,} rows ({n_train_red} red)")
print(f"  [{time.time()-t_start:6.1f}s] Test:  {len(te_idx):,} rows ({n_test_red} red)")
print(f"  [{time.time()-t_start:6.1f}s] Verified: {n_train_red}+{n_test_red}={n_train_red+n_test_red} red")

# ============================================================
# EVAL FUNCTION
# ============================================================
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

# ============================================================
# CONFIG A: 14feat BASELINE
# ============================================================
if only_config is None or only_config == 'A':
 section_header("STEP 3: TRAIN CONFIG A (14feat BASELINE)")
 t_sec = time.time()
 t_train = time.time()
 lgb_a = lgb.LGBMClassifier(
     num_leaves=63, learning_rate=0.03, n_estimators=500,
     scale_pos_weight=3, min_child_samples=100,
     reg_alpha=0.5, reg_lambda=5.0,
     random_state=42, n_jobs=1, verbose=-1
 )
 lgb_a.fit(X_14[tr_idx], y_train)
 train_time_a = time.time() - t_train

 t_pred = time.time()
 print("  TRAIN:")
 train_a = eval_it("LGB-14feat", lgb_a.predict_proba(X_14[tr_idx])[:, 1], y_train)
 print("  TEST:")
 test_a = eval_it("LGB-14feat", lgb_a.predict_proba(X_14[te_idx])[:, 1], y_test)
 pred_time_a = time.time() - t_pred

 print(f"\n  Feature importance:")
 for fn, imp in sorted(zip(fnames14, lgb_a.feature_importances_), key=lambda x: -x[1]):
     print(f"    {fn:<25} {imp:>5}")
 total_a = time.time() - t_sec
 print(f"\n  [{time.time()-t_start:6.1f}s] Config A done: train={train_time_a:.1f}s  predict={pred_time_a:.1f}s  total={total_a:.1f}s")
 trained['A'] = {'model': lgb_a, 'X': X_14, 'train': train_a, 'test': test_a, 'total': total_a, 'train_time': train_time_a, 'pred_time': pred_time_a, 'fnames': fnames14}

# ============================================================
# BUILD 16-FEAT MATRIX (14 + pair_freq_ratio + is_rare_hour)
# ============================================================
section_header("STEP 4: BUILD 16-FEAT MATRIX")
t0 = time.time()
X_16 = np.column_stack([
    X_14,
    pair_freq_ratio.reshape(-1,1),
    is_rare_hour.reshape(-1,1)
])
fnames16 = fnames14 + ['pair_freq_ratio', 'is_rare_hour']
assert X_16.shape == (n, 16), f"X_16 shape: expected ({n}, 16), got {X_16.shape}"
assert not np.any(np.isnan(X_16)), "X_16 contains NaN"
assert not np.any(np.isinf(X_16)), "X_16 contains Inf"
build_16_time = time.time() - t0
print(f"  [{time.time()-t_start:6.1f}s] X_16 built in {build_16_time:.1f}s  shape={X_16.shape}  {X_16.nbytes/1024/1024:.0f} MB")
print(f"  [{time.time()-t_start:6.1f}s] RAM: {mem_mb():.0f} MB")

# ============================================================
# COMPUTE pairs_last_100 (per-user sliding window)
# ============================================================
section_header("STEP 5: COMPUTE pairs_last_100")
t0 = time.time()
print(f"  [{time.time()-t_start:6.1f}s] Loading pairs_last_100 data from DuckDB...")
con = duckdb.connect('data/raw/lanl/lanl.duckdb', read_only=True)
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
sql_time = time.time() - t0
print(f"  [{time.time()-t_start:6.1f}s] SQL query done in {sql_time:.1f}s  rows={len(pl):,}")

t0 = time.time()
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
t_loop = time.time()
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
        elapsed = time.time() - t_loop
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total_users - done) / rate if rate > 0 else 0
        print(f"    [{time.time()-t_start:6.1f}s] {done}/{total_users} users ({elapsed:.0f}s, {rate:.0f} users/s, ETA {eta:.0f}s)")

pairs_last = np.zeros(n, dtype=np.float32)
pairs_last[base_idx] = pairs_last_raw
compute_time = time.time() - t0
print(f"  [{time.time()-t_start:6.1f}s] pairs_last_100 computed in {compute_time:.1f}s")
print(f"  [{time.time()-t_start:6.1f}s] RAM: {mem_mb():.0f} MB")

# ============================================================
# BUILD 17-FEAT MATRIX (16 + pairs_last_100)
# ============================================================
section_header("STEP 6: BUILD 17-FEAT MATRIX")
t0 = time.time()
X_17 = np.column_stack([X_16, pairs_last.reshape(-1,1)])
fnames17 = fnames16 + ['pairs_last_100']
assert X_17.shape == (n, 17), f"X_17 shape: expected ({n}, 17), got {X_17.shape}"
assert not np.any(np.isnan(X_17)), "X_17 contains NaN"
assert not np.any(np.isinf(X_17)), "X_17 contains Inf"
build_17_time = time.time() - t0
print(f"  [{time.time()-t_start:6.1f}s] X_17 built in {build_17_time:.1f}s  shape={X_17.shape}  {X_17.nbytes/1024/1024:.0f} MB")
print(f"  [{time.time()-t_start:6.1f}s] RAM: {mem_mb():.0f} MB")

# ============================================================
# CONFIG B: 16feat (+pair_freq_ratio, +is_rare_hour)
# ============================================================
if only_config is None or only_config == 'B':
 section_header("STEP 7: TRAIN CONFIG B (16feat)")
 t_sec = time.time()
 t_train = time.time()
 lgb_b = lgb.LGBMClassifier(
     num_leaves=63, learning_rate=0.03, n_estimators=500,
     scale_pos_weight=3, min_child_samples=100,
     reg_alpha=0.5, reg_lambda=5.0,
     random_state=42, n_jobs=1, verbose=-1
 )
 lgb_b.fit(X_16[tr_idx], y_train)
 train_time_b = time.time() - t_train

 t_pred = time.time()
 print("  TRAIN:")
 train_b = eval_it("LGB-16feat", lgb_b.predict_proba(X_16[tr_idx])[:, 1], y_train)
 print("  TEST:")
 test_b = eval_it("LGB-16feat", lgb_b.predict_proba(X_16[te_idx])[:, 1], y_test)
 pred_time_b = time.time() - t_pred

 print(f"\n  Feature importance:")
 for fn, imp in sorted(zip(fnames16, lgb_b.feature_importances_), key=lambda x: -x[1]):
     print(f"    {fn:<25} {imp:>5}")
 total_b = time.time() - t_sec
 print(f"\n  [{time.time()-t_start:6.1f}s] Config B done: train={train_time_b:.1f}s  predict={pred_time_b:.1f}s  total={total_b:.1f}s")
 trained['B'] = {'model': lgb_b, 'X': X_16, 'train': train_b, 'test': test_b, 'total': total_b, 'train_time': train_time_b, 'pred_time': pred_time_b, 'fnames': fnames16}

# ============================================================
# CONFIG C: 17feat (+pairs_last_100)
# ============================================================
if only_config is None or only_config == 'C':
 section_header("STEP 8: TRAIN CONFIG C (17feat)")
 t_sec = time.time()
 t_train = time.time()
 lgb_c = lgb.LGBMClassifier(
     num_leaves=63, learning_rate=0.03, n_estimators=500,
     scale_pos_weight=3, min_child_samples=100,
     reg_alpha=0.5, reg_lambda=5.0,
     random_state=42, n_jobs=1, verbose=-1
 )
 lgb_c.fit(X_17[tr_idx], y_train)
 train_time_c = time.time() - t_train

 t_pred = time.time()
 print("  TRAIN:")
 train_c = eval_it("LGB-17feat", lgb_c.predict_proba(X_17[tr_idx])[:, 1], y_train)
 print("  TEST:")
 test_c = eval_it("LGB-17feat", lgb_c.predict_proba(X_17[te_idx])[:, 1], y_test)
 pred_time_c = time.time() - t_pred

 print(f"\n  Feature importance:")
 for fn, imp in sorted(zip(fnames17, lgb_c.feature_importances_), key=lambda x: -x[1]):
     print(f"    {fn:<25} {imp:>5}")
 total_c = time.time() - t_sec
 print(f"\n  [{time.time()-t_start:6.1f}s] Config C done: train={train_time_c:.1f}s  predict={pred_time_c:.1f}s  total={total_c:.1f}s")
 trained['C'] = {'model': lgb_c, 'X': X_17, 'train': train_c, 'test': test_c, 'total': total_c, 'train_time': train_time_c, 'pred_time': pred_time_c, 'fnames': fnames17}

# ============================================================
# CONFIG D: 18feat (+pair_interval_ratio)
# ============================================================
if only_config is None or only_config == 'D':
 section_header("STEP 9: TRAIN CONFIG D (18feat +pair_interval_ratio)")
 X_18 = np.column_stack([X_17, pair_interval_ratio.reshape(-1,1)])
 fnames18 = fnames17 + ['pair_interval_ratio']
 assert X_18.shape == (n, 18), f"X_18 shape: expected ({n}, 18), got {X_18.shape}"
 assert not np.any(np.isnan(X_18)), "X_18 contains NaN"
 assert not np.any(np.isinf(X_18)), "X_18 contains Inf"
 print(f"  [{time.time()-t_start:6.1f}s] X_18 built  shape={X_18.shape}  {X_18.nbytes/1024/1024:.0f} MB")

 t_sec = time.time()
 t_train = time.time()
 lgb_d = lgb.LGBMClassifier(
     num_leaves=63, learning_rate=0.03, n_estimators=500,
     scale_pos_weight=3, min_child_samples=100,
     reg_alpha=0.5, reg_lambda=5.0,
     random_state=42, n_jobs=1, verbose=-1
 )
 lgb_d.fit(X_18[tr_idx], y_train)
 train_time_d = time.time() - t_train

 t_pred = time.time()
 print("  TRAIN:")
 train_d = eval_it("LGB-18feat", lgb_d.predict_proba(X_18[tr_idx])[:, 1], y_train)
 print("  TEST:")
 test_d = eval_it("LGB-18feat", lgb_d.predict_proba(X_18[te_idx])[:, 1], y_test)
 pred_time_d = time.time() - t_pred

 print(f"\n  Feature importance:")
 for fn, imp in sorted(zip(fnames18, lgb_d.feature_importances_), key=lambda x: -x[1]):
     print(f"    {fn:<25} {imp:>5}")
 total_d = time.time() - t_sec
 print(f"\n  [{time.time()-t_start:6.1f}s] Config D done: train={train_time_d:.1f}s  predict={pred_time_d:.1f}s  total={total_d:.1f}s")
 trained['D'] = {'model': lgb_d, 'X': X_18, 'train': train_d, 'test': test_d, 'total': total_d, 'train_time': train_time_d, 'pred_time': pred_time_d, 'fnames': fnames18}

# ============================================================
# CONFIG E: 20feat (17 + iat_zscore + velocity_ratio + machine_popularity)
# ============================================================
if only_config is None or only_config == 'E':
 section_header("STEP 10: TRAIN CONFIG E (20feat +iat_zscore +velocity_ratio +machine_popularity)")
 X_20 = np.column_stack([X_17, iat_zscore.reshape(-1,1), velocity_ratio.reshape(-1,1), machine_popularity.reshape(-1,1)])
 fnames20 = fnames17 + ['iat_zscore', 'velocity_ratio', 'machine_popularity']
 assert X_20.shape == (n, 20), f"X_20 shape: expected ({n}, 20), got {X_20.shape}"
 assert not np.any(np.isnan(X_20)), "X_20 contains NaN"
 assert not np.any(np.isinf(X_20)), "X_20 contains Inf"
 print(f"  [{time.time()-t_start:6.1f}s] X_20 built  shape={X_20.shape}  {X_20.nbytes/1024/1024:.0f} MB")

 t_sec = time.time()
 t_train = time.time()
 lgb_e = lgb.LGBMClassifier(
     num_leaves=63, learning_rate=0.03, n_estimators=500,
     scale_pos_weight=3, min_child_samples=100,
     reg_alpha=0.5, reg_lambda=5.0,
     random_state=42, n_jobs=1, verbose=-1
 )
 lgb_e.fit(X_20[tr_idx], y_train)
 train_time_e = time.time() - t_train

 t_pred = time.time()
 print("  TRAIN:")
 train_e = eval_it("LGB-20feat", lgb_e.predict_proba(X_20[tr_idx])[:, 1], y_train)
 print("  TEST:")
 test_e = eval_it("LGB-20feat", lgb_e.predict_proba(X_20[te_idx])[:, 1], y_test)
 pred_time_e = time.time() - t_pred

 print(f"\n  Feature importance:")
 for fn, imp in sorted(zip(fnames20, lgb_e.feature_importances_), key=lambda x: -x[1]):
     print(f"    {fn:<25} {imp:>5}")
 total_e = time.time() - t_sec
 print(f"\n  [{time.time()-t_start:6.1f}s] Config E done: train={train_time_e:.1f}s  predict={pred_time_e:.1f}s  total={total_e:.1f}s")
 trained['E'] = {'model': lgb_e, 'X': X_20, 'train': train_e, 'test': test_e, 'total': total_e, 'train_time': train_time_e, 'pred_time': pred_time_e, 'fnames': fnames20}

 os.makedirs("models", exist_ok=True)
 joblib.dump({
     "model": lgb_e, "model_type": "lightgbm",
     "threshold": test_e['thr'], "features": fnames20,
     "roc_auc": test_e['roc'], "pr_auc": test_e['pr'],
     "f1": test_e['f1'], "tp": test_e['tp'], "fp": test_e['fp'],
     "scale_pos_weight": 3,
 }, "models/lanl_lgb_20feat.joblib")
 print(f"  saved models/lanl_lgb_20feat.joblib")

# ============================================================
# OVERLAP ANALYSIS (test set only, red events only)
# ============================================================
section_header("STEP 10: OVERLAP ANALYSIS (Rule vs LGB)")
t_sec = time.time()

pair_rank_test = pair_rank_raw[te_idx]
red_mask = y_test
rule_catches = (pair_rank_test <= 5) & red_mask
n_rule = int(np.sum(rule_catches))
print(f"  Rule (pair_rank<=5) catches: {n_rule}/{n_test_red} ({100*n_rule/n_test_red:.1f}%)")
print()

for name in ['A', 'B', 'C', 'D', 'E']:
 if name not in trained:
     continue
 cfg = trained[name]
 scores = cfg['model'].predict_proba(cfg['X'][te_idx])[:, 1]
 t_model = time.time()
 prec, rec, thr = precision_recall_curve(y_test, scores)
 f1_vals = np.nan_to_num(2*prec*rec/(prec+rec))
 best_thr = thr[np.argmax(f1_vals[:-1])]
 lgb_catches = (scores >= best_thr) & red_mask

 both = int(np.sum(rule_catches & lgb_catches))
 rule_only = int(np.sum(rule_catches & ~lgb_catches))
 lgb_only = int(np.sum(~rule_catches & lgb_catches))
 neither = int(np.sum(~rule_catches & ~lgb_catches & red_mask))
 n_lgb = int(np.sum(lgb_catches))

 assert both + rule_only + lgb_only + neither == n_test_red, \
     f"Overlap sum mismatch: {both}+{rule_only}+{lgb_only}+{neither} != {n_test_red}"

 overlap_time = time.time() - t_model
 feat_count = len(cfg['fnames'])
 print(f"  {name} ({feat_count}feat, thr={best_thr:.6f}, {overlap_time:.2f}s):")
 print(f"    Rule catches:     {n_rule}/{n_test_red} ({100*n_rule/n_test_red:.1f}%)")
 print(f"    LGB catches:      {n_lgb}/{n_test_red} ({100*n_lgb/n_test_red:.1f}%)")
 print(f"    Both:             {both}")
 print(f"    Rule-only:        {rule_only}")
 print(f"    LGB-only:         {lgb_only}  {'*** ML CATCHES UNIQUE ATTACKS ***' if lgb_only > 0 else ''}")
 print(f"    Neither:          {neither}")
 print()

overlap_total = time.time() - t_sec
print(f"  [{time.time()-t_start:6.1f}s] Overlap analysis done in {overlap_total:.2f}s")

# ============================================================
# SUMMARY
# ============================================================
section_header("SUMMARY")
total_time = time.time() - t_start

print(f"\n  CONFIG RESULTS:")
print(f"  {'Config':<12} {'Features':<8} {'Train F1':<10} {'Test F1':<10} {'Train TP':<10} {'Test TP':<10} {'Test FP':<10}")
print(f"  {'-'*70}")
for name in ['A', 'B', 'C', 'D', 'E']:
  if name in trained:
     cfg = trained[name]
     fnames = cfg['fnames']
     label = f"{name} ({len(fnames)}feat)"
     print(f"  {label:<12} {len(fnames):<8} {cfg['train']['f1']:<10.4f} {cfg['test']['f1']:<10.4f} {cfg['train']['tp']:<10} {cfg['test']['tp']:<10} {cfg['test']['fp']:<10}")

print(f"\n  TIMING BREAKDOWN:")
print(f"  {'Step':<35} {'Time':<10} {'% Total':<10}")
print(f"  {'-'*55}")
print(f"  {'1. Load features':<35} {query_time:<10.1f} {100*query_time/total_time:<10.1f}%")
print(f"  {'2. Build feature matrices':<35} {build_time:<10.1f} {100*build_time/total_time:<10.1f}%")
print(f"  {'3. Train/test split':<35} {split_time:<10.2f} {100*split_time/total_time:<10.1f}%")
step_num = 4
for name in ['A', 'B', 'C', 'D', 'E']:
  if name in trained:
     cfg = trained[name]
     fnames = cfg['fnames']
     label = f"{step_num}. Config {name} ({len(fnames)}feat)"
     print(f"  {label:<35} {cfg['total']:<10.1f} {100*cfg['total']/total_time:<10.1f}%")
     step_num += 1
label = f"{step_num}. Overlap analysis"
print(f"  {label:<35} {overlap_total:<10.2f} {100*overlap_total/total_time:<10.1f}%")
print(f"  {'-'*55}")
print(f"  {'TOTAL':<35} {total_time:<10.1f} {'100.0':<10}%")

print(f"\n  SYSTEM:")
print(f"  RAM peak: {mem_mb():.0f} MB")
print(f"  Dataset: {n:,} events, {n_red} red, {len(set(src_users)):} users")
print(f"\n  [{total_time:.1f}s] Done. Log: logs/exp2.txt")
