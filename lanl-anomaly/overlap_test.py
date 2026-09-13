#!/usr/bin/env python3
"""IF + LGB overlap test: do they catch different attacks?

Uses the same GroupShuffleSplit as exp1.py (deterministic).
Inner split carves validation slice for threshold selection.
No test set leakage.
"""
import duckdb
import numpy as np
import time
import joblib
from sklearn.model_selection import GroupShuffleSplit
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve
import lightgbm as lgb

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
src_users = result['src_user']

# ====== Build 13 features (same as exp1.py) ======
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

# Log transforms (same as exp1.py)
X_log = X_13.copy()
X_log[:, 3] = np.log1p(X_log[:, 3])
X_log[:, 4] = np.log1p(X_log[:, 4])
X_log[:, 5] = np.log1p(X_log[:, 5])

# ====== Outer split: same as exp1.py ======
print("\nSplitting data...")
gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
for tr_idx, te_idx in gss.split(X_13, y, groups=src_users):
    pass

y_train, y_test = y[tr_idx], y[te_idx]
src_users_train = src_users[tr_idx]

print(f"Train: {len(tr_idx):,} ({int(y_train.sum())} red)")
print(f"Test:  {len(te_idx):,} ({int(y_test.sum())} red)")

# ====== Inner split: carve validation slice from train ======
gss_val = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=99)
for trtr_idx, val_idx in gss_val.split(X_log[tr_idx], y_train, groups=src_users_train):
    pass

# Map back to original indices
trtr_idx_global = tr_idx[trtr_idx]
val_idx_global = tr_idx[val_idx]

y_trtr = y[trtr_idx_global]
y_val = y[val_idx_global]

print(f"Train-train: {len(trtr_idx_global):,} ({int(y_trtr.sum())} red)")
print(f"Train-val:   {len(val_idx_global):,} ({int(y_val.sum())} red)")

# ====== Helper ======
def eval_model(name, scores, y_true):
    roc = roc_auc_score(y_true, scores)
    pr = average_precision_score(y_true, scores)
    prec, rec, thr = precision_recall_curve(y_true, scores)
    f1 = np.nan_to_num(2*prec*rec/(prec+rec))
    best = np.argmax(f1[:-1])
    tp = int(np.sum((scores >= thr[best]) & y_true))
    fp = int(np.sum((scores >= thr[best]) & ~y_true))
    print(f"  {name:<20} ROC={roc:.4f} PR-AUC={pr:.4f} F1={f1[best]:.4f} TP={tp:>3} FP={fp:>5} thr={thr[best]:.6f}")
    return thr[best]

# ====== Train LGB on train-train ======
print("\n" + "="*70)
print("Training LGB...")
t_sec = time.time()

lgb_model = lgb.LGBMClassifier(
    num_leaves=63, learning_rate=0.03, n_estimators=500,
    scale_pos_weight=3, min_child_samples=100,
    reg_alpha=0.5, reg_lambda=5.0,
    random_state=42, n_jobs=1, verbose=-1
)
lgb_model.fit(X_13[trtr_idx_global], y_trtr)

# Score train-val for threshold
lgb_val_scores = lgb_model.predict_proba(X_13[val_idx_global])[:, 1]
lgb_threshold = eval_model("LGB val", lgb_val_scores, y_val)

# Score full test set
lgb_test_scores = lgb_model.predict_proba(X_13[te_idx])[:, 1]
print(f"  [LGB train took {time.time()-t_sec:.1f}s]")

# ====== Train IF on train-train NORMALS ONLY ======
print("\n" + "="*70)
print("Training IF...")
t_sec = time.time()

trtr_normal_mask = ~y_trtr
X_trtr_norm = X_log[trtr_idx_global][trtr_normal_mask]

sc = StandardScaler()
X_trtr_scaled = sc.fit_transform(X_trtr_norm)

if_model = IsolationForest(
    n_estimators=200, contamination=1e-7,
    max_samples=256, n_jobs=1, random_state=42
)
if_model.fit(X_trtr_scaled)

# Score train-val (ALL rows, including reds, for threshold selection)
if_val_scores = -if_model.score_samples(sc.transform(X_log[val_idx_global]))
if_threshold = eval_model("IF val", if_val_scores, y_val)

# Score full test set
if_test_scores = -if_model.score_samples(sc.transform(X_log[te_idx]))
print(f"  [IF train took {time.time()-t_sec:.1f}s]")

# ====== Evaluate on full test set ======
print("\n" + "="*70)
print("Test set evaluation (full 5.4M rows)")
print("="*70)

eval_model("LGB test", lgb_test_scores, y_test)
eval_model("IF test", if_test_scores, y_test)

# ====== Overlap analysis on 240 test reds ======
print("\n" + "="*70)
print("Overlap analysis (240 test reds)")
print("="*70)

red_mask_test = y_test
if_caught = if_test_scores[red_mask_test] >= if_threshold
lgb_caught = lgb_test_scores[red_mask_test] >= lgb_threshold

both = int((if_caught & lgb_caught).sum())
if_only = int((if_caught & ~lgb_caught).sum())
lgb_only = int((~if_caught & lgb_caught).sum())
neither = int((~if_caught & ~lgb_caught).sum())
union = if_only + lgb_only + both

print(f"  LGB catches:  {int(lgb_caught.sum()):>3} / 240")
print(f"  IF catches:   {int(if_caught.sum()):>3} / 240")
print(f"  Both:         {both:>3}")
print(f"  IF only:      {if_only:>3}")
print(f"  LGB only:     {lgb_only:>3}")
print(f"  Neither:      {neither:>3}")
print(f"  Union:        {union:>3}")
print(f"  (IF alone:    389)")
print(f"  (LGB alone:   94)")

# ====== FP analysis on full test normals ======
print("\n" + "="*70)
print("FP analysis (full test normals)")
print("="*70)

norm_mask_test = ~y_test
if_fp = int((if_test_scores[norm_mask_test] >= if_threshold).sum())
lgb_fp = int((lgb_test_scores[norm_mask_test] >= lgb_threshold).sum())

print(f"  LGB FP:  {lgb_fp:>6} (established: ~372)")
print(f"  IF FP:   {if_fp:>6}")

# ====== Save new LGB model ======
model_path = "models/lanl_lgb_13feat.joblib"
art = {
    "model": lgb_model,
    "roc_auc": roc_auc_score(y_test, lgb_test_scores),
    "threshold": lgb_threshold,
    "features": ['dst_first','src_first','hour_ratio','dst_prior_events','fail_1h',
                 'vel_1h','hour_sin','hour_cos','is_ntlm',
                 'pair_first','src_dst_pair_first','fail_rate','dst_first_x_ntlm'],
}
joblib.dump(art, model_path)
print(f"\nSaved new 13feat model to {model_path}")
print(f"Old 9feat model unchanged at models/lanl_lgb.joblib")

print("\n" + "="*70)
print(f"TOTAL TIME: {time.time()-t_start:.1f}s ({(time.time()-t_start)/60:.1f} min)")
print("="*70)
