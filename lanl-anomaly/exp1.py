#!/usr/bin/env python3
"""Experiment: 9 vs 13 features, tuned vs baseline LGB."""
import duckdb
import numpy as np
import time
from sklearn.model_selection import GroupShuffleSplit
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
import lightgbm as lgb

t_start = time.time()

print("Loading data...")
t0 = time.time()
con = duckdb.connect('data/raw/lanl/lanl.duckdb')
result = con.execute("""
SELECT dst_first, src_first, hour_events, user_events,
       CAST(dst_prior_events AS BIGINT) AS dst_prior_events,
       CAST(fail_1h AS BIGINT) AS fail_1h,
       CAST(vel_1h AS BIGINT) AS vel_1h,
       hour, is_red, src_computer, src_user,
       CASE WHEN ROW_NUMBER() OVER (PARTITION BY src_user, src_computer, dst_computer ORDER BY time) = 1
            THEN 1.0 ELSE 0.0 END AS pair_first,
       CASE WHEN ROW_NUMBER() OVER (PARTITION BY src_computer, dst_computer ORDER BY time) = 1
            THEN 1.0 ELSE 0.0 END AS src_dst_pair_first,
       CAST(fail_1h AS DOUBLE) / (CAST(vel_1h AS DOUBLE) + 1.0) AS fail_rate,
       CASE WHEN dst_first = 1 AND is_ntlm THEN 1.0 ELSE 0.0 END AS dst_first_x_ntlm,
       is_ntlm
FROM feat
ORDER BY rowid
""").fetchnumpy()
con.close()
print(f"Loaded in {time.time()-t0:.1f}s")

y = result['is_red'].astype(bool)
n = len(y)
n_reds = int(y.sum())
src_comps = result['src_computer']
src_users = result['src_user']

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

pair_first = result['pair_first'].astype(np.float32)
src_dst_pair_first = result['src_dst_pair_first'].astype(np.float32)
fail_rate = result['fail_rate'].astype(np.float32)
dst_first_x_ntlm = result['dst_first_x_ntlm'].astype(np.float32)

X_13 = np.column_stack([X_9, pair_first.reshape(-1,1), src_dst_pair_first.reshape(-1,1),
                         fail_rate.reshape(-1,1), dst_first_x_ntlm.reshape(-1,1)])
fnames13 = ['dst_first','src_first','hour_ratio','dst_prior_events','fail_1h',
            'vel_1h','hour_sin','hour_cos','is_ntlm',
            'pair_first','src_dst_pair_first','fail_rate','dst_first_x_ntlm']

holdout_mask = src_comps == 'C17693'
gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
for tr_idx, te_idx in gss.split(X_13, y, groups=src_users):
    pass
y_train, y_test = y[tr_idx], y[te_idx]
contamination = 702 / 29_905_488

print(f"Train: {len(tr_idx):,} ({int(y_train.sum())} red) / Test: {len(te_idx):,} ({int(y_test.sum())} red)")

X_log = X_13.copy()
X_log[:, 3] = np.log1p(X_log[:, 3])
X_log[:, 4] = np.log1p(X_log[:, 4])
X_log[:, 5] = np.log1p(X_log[:, 5])

def eval_it(name, scores, y_t):
    roc = roc_auc_score(y_t, scores)
    pr = average_precision_score(y_t, scores)
    prec, rec, thr = precision_recall_curve(y_t, scores)
    f1 = np.nan_to_num(2*prec*rec/(prec+rec))
    best = np.argmax(f1[:-1])
    pred = scores >= thr[best]
    tp = int(np.sum(pred & y_t))
    fp = int(np.sum(pred & ~y_t))
    print(f"  {name:<22} ROC={roc:.4f} PR-AUC={pr:.4f} F1={f1[best]:.4f} TP={tp} FP={fp} thr={thr[best]:.6f}")

# ====== A: BASELINE ======
t_sec = time.time()
print("\n" + "="*70)
print("A. BASELINE: 9 features, current hyperparams (spw=100)")
print("="*70)

sc = StandardScaler()
X_tr9 = sc.fit_transform(X_log[tr_idx, :9])
X_te9 = sc.transform(X_log[te_idx, :9])

if9 = IsolationForest(n_estimators=200, contamination=contamination, max_samples=256, n_jobs=1, random_state=42)
if9.fit(X_tr9)
if_tr = -if9.score_samples(X_tr9)
if_min, if_max = np.percentile(if_tr, 1), np.percentile(if_tr, 99)
if_r = if_max - if_min
if9_scores = (-if9.score_samples(X_te9) - if_min) / if_r

lgb9 = lgb.LGBMClassifier(num_leaves=31, learning_rate=0.05, n_estimators=200,
                           scale_pos_weight=100, random_state=42, n_jobs=1, verbose=-1)
lgb9.fit(X_9[tr_idx], y_train)
lgb9_scores = lgb9.predict_proba(X_9[te_idx])[:, 1]

eval_it("IF-9feat", if9_scores, y_test)
eval_it("LGB-9feat", lgb9_scores, y_test)
eval_it("Comb-9feat", 0.5*if9_scores + 0.5*lgb9_scores, y_test)
print(f"  [took {time.time()-t_sec:.1f}s]")

# ====== B: 12 features, same hyperparams ======
t_sec = time.time()
print("\n" + "="*70)
print("B. 13 features, same hyperparams (spw=100)")
print("="*70)

sc12 = StandardScaler()
X_tr12 = sc12.fit_transform(X_log[tr_idx])
X_te12 = sc12.transform(X_log[te_idx])

if12 = IsolationForest(n_estimators=200, contamination=contamination, max_samples=256, n_jobs=1, random_state=42)
if12.fit(X_tr12)
if_tr12 = -if12.score_samples(X_tr12)
if_min12, if_max12 = np.percentile(if_tr12, 1), np.percentile(if_tr12, 99)
if_r12 = if_max12 - if_min12
if12_scores = (-if12.score_samples(X_te12) - if_min12) / if_r12

lgb12 = lgb.LGBMClassifier(num_leaves=31, learning_rate=0.05, n_estimators=200,
                            scale_pos_weight=100, random_state=42, n_jobs=1, verbose=-1)
lgb12.fit(X_13[tr_idx], y_train)
lgb12_scores = lgb12.predict_proba(X_13[te_idx])[:, 1]

eval_it("IF-12feat", if12_scores, y_test)
eval_it("LGB-12feat", lgb12_scores, y_test)
eval_it("Comb-12feat", 0.5*if12_scores + 0.5*lgb12_scores, y_test)
print(f"  [took {time.time()-t_sec:.1f}s]")

# ====== C: 12 features, TUNED LGB (spw=10) ======
t_sec = time.time()
print("\n" + "="*70)
print("C. 13 features, TUNED LGB (spw=10, regularization)")
print("="*70)

lgb_tuned = lgb.LGBMClassifier(
    num_leaves=63, learning_rate=0.03, n_estimators=500,
    scale_pos_weight=10, min_child_samples=50,
    reg_alpha=0.1, reg_lambda=1.0,
    random_state=42, n_jobs=1, verbose=-1
)
lgb_tuned.fit(X_13[tr_idx], y_train)
lgb_tuned_scores = lgb_tuned.predict_proba(X_13[te_idx])[:, 1]

eval_it("IF-12feat", if12_scores, y_test)
eval_it("LGB-tuned", lgb_tuned_scores, y_test)
eval_it("Comb-tuned", 0.5*if12_scores + 0.5*lgb_tuned_scores, y_test)

atk_p = lgb_tuned_scores[y_test]
norm_p = lgb_tuned_scores[~y_test]
print(f"\n  LGB-tuned prob distribution:")
print(f"    Attacks: min={atk_p.min():.4f} p25={np.percentile(atk_p,25):.4f} p50={np.median(atk_p):.4f} p75={np.percentile(atk_p,75):.4f} max={atk_p.max():.4f}")
print(f"    Normal:  min={norm_p.min():.6f} p50={np.median(norm_p):.6f} p75={np.percentile(norm_p,75):.6f} max={norm_p.max():.4f}")

print(f"\n  LGB-tuned feature importance:")
for fn, imp in sorted(zip(fnames13, lgb_tuned.feature_importances_), key=lambda x: -x[1]):
    print(f"    {fn:<25} {imp:>5}")
print(f"  [took {time.time()-t_sec:.1f}s]")

# ====== D: 12 features, TUNED LGB v2 (spw=3) ======
t_sec = time.time()
print("\n" + "="*70)
print("D. 13 features, TUNED LGB v2 (spw=3, heavy regularization)")
print("="*70)

lgb_t2 = lgb.LGBMClassifier(
    num_leaves=63, learning_rate=0.03, n_estimators=500,
    scale_pos_weight=3, min_child_samples=100,
    reg_alpha=0.5, reg_lambda=5.0,
    random_state=42, n_jobs=1, verbose=-1
)
lgb_t2.fit(X_13[tr_idx], y_train)
lgb_t2_scores = lgb_t2.predict_proba(X_13[te_idx])[:, 1]

eval_it("IF-12feat", if12_scores, y_test)
eval_it("LGB-tuned-v2", lgb_t2_scores, y_test)
eval_it("Comb-tuned-v2", 0.5*if12_scores + 0.5*lgb_t2_scores, y_test)

atk_p2 = lgb_t2_scores[y_test]
norm_p2 = lgb_t2_scores[~y_test]
print(f"\n  LGB-tuned-v2 prob distribution:")
print(f"    Attacks: min={atk_p2.min():.4f} p25={np.percentile(atk_p2,25):.4f} p50={np.median(atk_p2):.4f} p75={np.percentile(atk_p2,75):.4f} max={atk_p2.max():.4f}")
print(f"    Normal:  min={norm_p2.min():.6f} p50={np.median(norm_p2):.6f} p75={np.percentile(norm_p2,75):.6f} max={norm_p2.max():.4f}")

print(f"\n  LGB-tuned-v2 feature importance:")
for fn, imp in sorted(zip(fnames13, lgb_t2.feature_importances_), key=lambda x: -x[1]):
    print(f"    {fn:<25} {imp:>5}")
print(f"  [took {time.time()-t_sec:.1f}s]")

print("\n" + "="*70)
print(f"TOTAL TIME: {time.time()-t_start:.1f}s")
print("="*70)
