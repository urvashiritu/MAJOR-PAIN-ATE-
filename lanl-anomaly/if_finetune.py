#!/usr/bin/env python3
"""IF fine-tune: contamination sweep on ALL normal events, 9/13/14 features.

IF trains on ALL normal events (not just train split).
Test on ALL 702 reds + 100k sampled normals.
Only IF — no LGB.
5 contamination values: mixed, 1e-15, 1e-10, 1e-7, 0.5
"""
import duckdb
import numpy as np
import time
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve

t_start = time.time()

# ====== Load data ======
print("Loading data...")
t0 = time.time()
con = duckdb.connect('data/raw/lanl/lanl.duckdb')
result = con.execute("""
SELECT dst_first, src_first, hour_events, user_events,
       CAST(dst_prior_events AS BIGINT) AS dst_prior_events,
       CAST(fail_1h AS BIGINT) AS fail_1h,
       CAST(vel_1h AS BIGINT) AS vel_1h,
       hour, is_red, src_computer, src_user,
       CASE WHEN ROW_NUMBER() OVER (PARTITION BY src_user, src_computer, dst_computer ORDER BY time, dst_user, auth_type, logon_type, orientation, result) = 1
            THEN 1.0 ELSE 0.0 END AS pair_first,
       CASE WHEN ROW_NUMBER() OVER (PARTITION BY src_computer, dst_computer ORDER BY time, src_user, dst_user, auth_type, logon_type, orientation, result) = 1
            THEN 1.0 ELSE 0.0 END AS src_dst_pair_first,
       CAST(fail_1h AS DOUBLE) / (CAST(vel_1h AS DOUBLE) + 1.0) AS fail_rate,
       CASE WHEN dst_first = 1 AND is_ntlm THEN 1.0 ELSE 0.0 END AS dst_first_x_ntlm,
       is_ntlm,
       CAST(ROW_NUMBER() OVER (PARTITION BY src_user, src_computer, dst_computer ORDER BY time, dst_user, auth_type, logon_type, orientation, result) AS DOUBLE) AS pair_rank
FROM feat
ORDER BY time, src_user, dst_user, src_computer, dst_computer, auth_type, logon_type, orientation, result
""").fetchnumpy()
con.close()
print(f"Loaded in {time.time()-t0:.1f}s")

y = result['is_red'].astype(bool)
n = len(y)
n_reds = int(y.sum())
print(f"Total: {n:,} rows, {n_reds} reds")

# ====== Build features ======

# 9 features (original LANL)
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

# 13 features
pair_first = result['pair_first'].astype(np.float32)
src_dst_pair_first = result['src_dst_pair_first'].astype(np.float32)
fail_rate = result['fail_rate'].astype(np.float32)
dst_first_x_ntlm = result['dst_first_x_ntlm'].astype(np.float32)

X_13 = np.column_stack([X_9, pair_first.reshape(-1,1), src_dst_pair_first.reshape(-1,1),
                         fail_rate.reshape(-1,1), dst_first_x_ntlm.reshape(-1,1)])

# 14 features (+pair_rank)
pair_rank = np.log1p(result['pair_rank'].astype(np.float32))
X_14 = np.column_stack([X_13, pair_rank.reshape(-1,1)])

# ====== Test set: ALL reds + 100k sampled normals ======
rng = np.random.RandomState(42)
normal_indices = np.where(~y)[0]
sampled_normals = rng.choice(normal_indices, size=100_000, replace=False)
test_indices = np.concatenate([np.where(y)[0], sampled_normals])

y_test = y[test_indices]
print(f"Test set: {len(test_indices):,} rows ({int(y_test.sum())} red, {int((~y_test).sum())} normal)")

# ====== Helpers ======
def eval_if(name, scores, y_t):
    roc = roc_auc_score(y_t, scores)
    pr = average_precision_score(y_t, scores)
    prec, rec, thr = precision_recall_curve(y_t, scores)
    f1 = np.nan_to_num(2*prec*rec/(prec+rec))
    best = np.argmax(f1[:-1])
    pred = scores >= thr[best]
    tp = int(np.sum(pred & y_t))
    fp = int(np.sum(pred & ~y_t))
    print(f"  {name:<25} ROC={roc:.4f} PR-AUC={pr:.4f} F1={f1[best]:.4f} TP={tp:>3} FP={fp:>5} thr={thr[best]:.6f}")

def log_apply(X):
    X_log = X.copy()
    X_log[:, 3] = np.log1p(X_log[:, 3])
    X_log[:, 4] = np.log1p(X_log[:, 4])
    X_log[:, 5] = np.log1p(X_log[:, 5])
    return X_log

def train_and_score(X_log, train_indices, contamination):
    X_norm = X_log[train_indices]
    sc = StandardScaler()
    X_tr = sc.fit_transform(X_norm)
    X_te = sc.transform(X_log[test_indices])
    model = IsolationForest(n_estimators=200, contamination=contamination,
                            max_samples=256, n_jobs=1, random_state=42)
    model.fit(X_tr)
    raw = -model.score_samples(X_te)
    lo, hi = np.percentile(raw, 1), np.percentile(raw, 99)
    return (raw - lo) / (hi - lo if hi > lo else 1.0)

contamination_real = 702 / 29_905_488
normal_idx = np.where(~y)[0]
all_idx = np.arange(n)

contaminations = [
    ("IF-mixed",      all_idx,    contamination_real),
    ("IF-normal-1e15", normal_idx, 1e-15),
    ("IF-normal-1e10", normal_idx, 1e-10),
    ("IF-normal-1e7",  normal_idx, 1e-7),
    ("IF-normal-0.5",  normal_idx, 0.5),
]

# ====== A: 9 features ======
t_sec = time.time()
print("\n" + "="*70)
print("A. IF contamination comparison (9feat)")
print("="*70)
X_log9 = log_apply(X_9)
for name, tr_idx, c in contaminations:
    eval_if(name, train_and_score(X_log9, tr_idx, c), y_test)
print(f"  [took {time.time()-t_sec:.1f}s]")

# ====== B: 13 features ======
t_sec = time.time()
print("\n" + "="*70)
print("B. IF contamination comparison (13feat)")
print("="*70)
X_log13 = log_apply(X_13)
for name, tr_idx, c in contaminations:
    eval_if(name, train_and_score(X_log13, tr_idx, c), y_test)
print(f"  [took {time.time()-t_sec:.1f}s]")

# ====== C: 14 features (+pair_rank) ======
t_sec = time.time()
print("\n" + "="*70)
print("C. IF contamination comparison (14feat +pair_rank)")
print("="*70)
X_log14 = log_apply(X_14)
for name, tr_idx, c in contaminations:
    eval_if(name, train_and_score(X_log14, tr_idx, c), y_test)
print(f"  [took {time.time()-t_sec:.1f}s]")

print("\n" + "="*70)
print(f"TOTAL TIME: {time.time()-t_start:.1f}s ({(time.time()-t_start)/60:.1f} min)")
print("="*70)
