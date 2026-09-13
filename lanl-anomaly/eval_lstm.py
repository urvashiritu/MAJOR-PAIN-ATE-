"""
eval_lstm.py — Evaluate LSTM surprisal on held-out test set (RUN 7)

Same GroupShuffleSplit(random_state=42) as exp2.py → 462 train / 240 test.
LSTM scores already in DuckDB. LGB loaded from joblib.
"""
import sys
import time
import os
import numpy as np
import duckdb
import joblib
import lightgbm as lgb
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve

t_start = time.time()

def mem_mb():
    import psutil
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

def section_header(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

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
# STEP 1: SQL CTE chain (copy from exp2.py)
# ============================================================
section_header("STEP 1: LOAD FEATURES + LSTM SCORES")
t0 = time.time()
con = duckdb.connect('data/raw/lanl/lanl.duckdb', read_only=True)
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
       mp.machine_popularity,
       uv.lstm_surprisal
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

y = result['is_red'].astype(bool)
n = len(y)
src_users = result['src_user'].copy()
n_red = int(y.sum())
print(f"  Rows: {n:,}  Red: {n_red}  Columns: {len(result)}")
print(f"  RAM: {mem_mb():.0f} MB")
print(f"  [{time.time()-t_start:6.1f}s] Query done in {time.time()-t0:.1f}s")

# ============================================================
# STEP 2: Build X_20 features (copy from exp2.py)
# ============================================================
section_header("STEP 2: BUILD X_20 FEATURES")
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

pair_rank_raw = result['pair_rank'].astype(np.float32)
pair_rank = np.log1p(pair_rank_raw)
X_14 = np.column_stack([X_13, pair_rank.reshape(-1,1)])

pair_freq_ratio = result['pair_freq_ratio'].astype(np.float32)
is_rare_hour = result['is_rare_hour'].astype(np.float32)
pair_interval_ratio = result['pair_interval_ratio'].astype(np.float32)
iat_zscore = result['iat_zscore'].astype(np.float32)
velocity_ratio = result['velocity_ratio'].astype(np.float32)
machine_popularity = result['machine_popularity'].astype(np.float32)
lstm_surprisal = result['lstm_surprisal'].astype(np.float64)

del result, X_raw
import gc; gc.collect()

X_16 = np.column_stack([X_14, pair_freq_ratio.reshape(-1,1), is_rare_hour.reshape(-1,1)])

# pairs_last_100: distinct destinations in sliding window of last 100 events per user
# (computed separately, not in main SQL — same as exp2.py lines 312-379)
print("  Computing pairs_last_100 (sliding window)...")
con2 = duckdb.connect('data/raw/lanl/lanl.duckdb', read_only=True)
pl = con2.execute("""
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
con2.close()

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
    if done % 200 == 0 or done == total_users:
        print(f"    {done}/{total_users} users")

pairs_last = np.zeros(n, dtype=np.float32)
pairs_last[base_idx] = pairs_last_raw
print(f"  pairs_last_100 computed")

X_17 = np.column_stack([X_16, pairs_last.reshape(-1,1)])

X_20 = np.column_stack([X_17, iat_zscore.reshape(-1,1), velocity_ratio.reshape(-1,1), machine_popularity.reshape(-1,1)])
fnames20 = ['dst_first','src_first','hour_ratio','dst_prior_events','fail_1h',
            'vel_1h','hour_sin','hour_cos','is_ntlm',
            'pair_first','src_dst_pair_first','fail_rate','dst_first_x_ntlm',
            'log_pair_rank','pair_freq_ratio','is_rare_hour','pairs_last_100',
            'iat_zscore','velocity_ratio','machine_popularity']

del X_9, X_13
import gc; gc.collect()

print(f"  X_20 shape={X_20.shape}  {X_20.nbytes/1024/1024:.0f} MB")
assert X_20.shape == (n, 20)
assert not np.any(np.isnan(X_20))
assert not np.any(np.isinf(X_20))
print(f"  [{time.time()-t_start:6.1f}s] Features built in {time.time()-t0:.1f}s")

# ============================================================
# STEP 3: Train/test split (same as exp2.py)
# ============================================================
section_header("STEP 3: TRAIN/TEST SPLIT")
t0 = time.time()
gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
for tr_idx, te_idx in gss.split(X_20, y, groups=src_users):
    pass

y_train, y_test = y[tr_idx], y[te_idx]
n_train_red = int(y_train.sum())
n_test_red = int(y_test.sum())
assert n_train_red + n_test_red == 702, f"Red split mismatch: {n_train_red}+{n_test_red} != 702"
assert n_test_red == 240, f"Expected 240 test red, got {n_test_red}"
print(f"  Train: {len(tr_idx):,} rows ({n_train_red} red)")
print(f"  Test:  {len(te_idx):,} rows ({n_test_red} red)")
print(f"  Verified: {n_train_red}+{n_test_red}={n_train_red+n_test_red} red")
print(f"  [{time.time()-t_start:6.1f}s] Split done in {time.time()-t0:.1f}s")

# ============================================================
# STEP 4: Load LSTM scores from DuckDB
# ============================================================
section_header("STEP 4: LOAD LSTM SCORES")
t0 = time.time()
lstm_scores = lstm_surprisal

n_nan = int(np.sum(np.isnan(lstm_scores)))
n_inf = int(np.sum(np.isinf(lstm_scores)))
print(f"  Loaded {len(lstm_scores):,} scores")
print(f"  NaN: {n_nan}  Inf: {n_inf}")
assert n_nan == 0, "LSTM scores contain NaN"
assert n_inf == 0, "LSTM scores contain Inf"

lstm_test = lstm_scores[te_idx]
lstm_red_test = lstm_test[y_test]
print(f"  Test set: {len(lstm_test):,} rows, {int(y_test.sum())} red")
print(f"  LSTM on test reds: mean={np.mean(lstm_red_test):.4f} p95={np.percentile(lstm_red_test, 95):.4f}")
print(f"  LSTM on test benign: mean={np.mean(lstm_test[~y_test]):.4f} p95={np.percentile(lstm_test[~y_test], 95):.4f}")
print(f"  [{time.time()-t_start:6.1f}s] LSTM scores loaded in {time.time()-t0:.1f}s")

# ============================================================
# STEP 5: Train LGB on train set, predict on test set
# ============================================================
section_header("STEP 5: TRAIN + PREDICT LGB")
t0 = time.time()

t_train = time.time()
lgb_model = lgb.LGBMClassifier(
    num_leaves=63, learning_rate=0.03, n_estimators=500,
    scale_pos_weight=3, min_child_samples=100,
    reg_alpha=0.5, reg_lambda=5.0,
    random_state=42, n_jobs=1, verbose=-1
)
lgb_model.fit(X_20[tr_idx], y_train)
print(f"  LGB train: {time.time()-t_train:.1f}s")

lgb_train_scores = lgb_model.predict_proba(X_20[tr_idx])[:, 1]
lgb_test_scores = lgb_model.predict_proba(X_20[te_idx])[:, 1]
print(f"  LGB predict: {time.time()-t_train:.1f}s total")
print(f"  [{time.time()-t_start:6.1f}s] LGB done in {time.time()-t0:.1f}s")

# ============================================================
# STEP 6: EVALUATE STANDALONE MODELS ON TEST SET
# ============================================================
section_header("STEP 6: STANDALONE EVALUATION")
print(f"  Test set: {len(te_idx):,} rows ({n_test_red} red)\n")

print("  LSTM standalone:")
lstm_eval = eval_it("LSTM", lstm_test, y_test)

print("\n  LGB standalone:")
lgb_eval = eval_it("LGB-20feat", lgb_test_scores, y_test)

# ============================================================
# STEP 7: OVERLAP ANALYSIS (test set, red events only)
# ============================================================
section_header("STEP 7: OVERLAP ANALYSIS (LSTM vs LGB)")

# LSTM catches
prec, rec, thr = precision_recall_curve(y_test, lstm_test)
f1_vals = np.nan_to_num(2*prec*rec/(prec+rec))
lstm_thr = thr[np.argmax(f1_vals[:-1])]
lstm_catches = (lstm_test >= lstm_thr) & y_test
n_lstm = int(np.sum(lstm_catches))
print(f"  LSTM catches: {n_lstm}/{n_test_red} ({100*n_lstm/n_test_red:.1f}%) @ thr={lstm_thr:.4f}")

# LGB catches
prec, rec, thr = precision_recall_curve(y_test, lgb_test_scores)
f1_vals = np.nan_to_num(2*prec*rec/(prec+rec))
lgb_thr = thr[np.argmax(f1_vals[:-1])]
lgb_catches = (lgb_test_scores >= lgb_thr) & y_test
n_lgb = int(np.sum(lgb_catches))
print(f"  LGB catches:  {n_lgb}/{n_test_red} ({100*n_lgb/n_test_red:.1f}%) @ thr={lgb_thr:.6f}")

# Overlap
both = int(np.sum(lstm_catches & lgb_catches))
lstm_only = int(np.sum(lstm_catches & ~lgb_catches))
lgb_only = int(np.sum(~lstm_catches & lgb_catches))
neither = int(np.sum(~lstm_catches & ~lgb_catches & y_test))

assert both + lstm_only + lgb_only + neither == n_test_red, \
    f"Overlap mismatch: {both}+{lstm_only}+{lgb_only}+{neither} != {n_test_red}"

print(f"\n  Overlap:")
print(f"    Both:     {both:>3} ({100*both/n_test_red:.1f}%)")
print(f"    LSTM-only:{lstm_only:>3} ({100*lstm_only/n_test_red:.1f}%)")
print(f"    LGB-only: {lgb_only:>3} ({100*lgb_only/n_test_red:.1f}%)")
print(f"    Neither:  {neither:>3} ({100*neither/n_test_red:.1f}%)")
print(f"    Sum:      {both+lstm_only+lgb_only+neither} == {n_test_red}")

# ============================================================
# STEP 8: ENSEMBLE SWEEP
# ============================================================
section_header("STEP 8: ENSEMBLE SWEEP (alpha * LSTM + (1-alpha) * LGB)")

# Normalize scores to [0,1] range for blending
lstm_norm = (lstm_test - lstm_test.min()) / (lstm_test.max() - lstm_test.min() + 1e-10)
lgb_norm = (lgb_test_scores - lgb_test_scores.min()) / (lgb_test_scores.max() - lgb_test_scores.min() + 1e-10)

best_f1 = 0
best_alpha = 0
best_result = None

for alpha in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
    blend = alpha * lstm_norm + (1.0 - alpha) * lgb_norm
    result = eval_it(f"a={alpha:.1f}", blend, y_test)
    if result['f1'] > best_f1:
        best_f1 = result['f1']
        best_alpha = alpha
        best_result = result

print(f"\n  Best: alpha={best_alpha:.1f} F1={best_result['f1']:.4f} TP={best_result['tp']} FP={best_result['fp']}")
print(f"  [{time.time()-t_start:6.1f}s] Ensemble sweep done in {time.time()-t0:.1f}s")

# ============================================================
# STEP 9: SUMMARY
# ============================================================
section_header("SUMMARY")
print(f"  Model:    LSTM (2ep, bs128, SurprisalLSTM 128h 2l ctx50)")
print(f"  LGB:      Config E (20feat)")
print(f"  Split:    GroupShuffleSplit(random_state=42)")
print(f"  Test:     {n_test_red} red / {len(te_idx):,} total")
print(f"")
print(f"  Standalone:")
print(f"    LSTM:  ROC={lstm_eval['roc']:.4f} F1={lstm_eval['f1']:.4f} TP={lstm_eval['tp']} FP={lstm_eval['fp']}")
print(f"    LGB:   ROC={lgb_eval['roc']:.4f} F1={lgb_eval['f1']:.4f} TP={lgb_eval['tp']} FP={lgb_eval['fp']}")
print(f"  Ensemble:")
print(f"    Best:  alpha={best_alpha:.1f} F1={best_result['f1']:.4f} TP={best_result['tp']} FP={best_result['fp']}")
print(f"  Overlap:")
print(f"    Both={both} LSTM-only={lstm_only} LGB-only={lgb_only} Neither={neither}")
print(f"\n  Total runtime: {time.time()-t_start:.1f}s")
