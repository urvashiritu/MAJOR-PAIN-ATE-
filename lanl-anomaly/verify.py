"""verify.py - Run this to check underfitting vs overfitting and feature importance"""
import duckdb, numpy as np, lightgbm as lgb
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score, precision_recall_curve
import warnings, sys, os
warnings.filterwarnings('ignore')

LOG_DIR = "logs/verify"
os.makedirs(LOG_DIR, exist_ok=True)
log_lines = []

def log(msg):
    print(msg)
    log_lines.append(msg)

con = duckdb.connect('data/raw/lanl/lanl.duckdb', read_only=True)
result = con.execute('''
WITH ranked AS (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY src_user, src_computer, dst_computer ORDER BY time, dst_user, auth_type, logon_type, orientation, result) AS pair_rank
  FROM feat
)
SELECT is_red, dst_first, src_first, hour_events, user_events,
       dst_prior_events, fail_1h, vel_1h, hour, is_ntlm, pair_rank, src_user
FROM ranked
ORDER BY time, src_user, dst_user, src_computer, dst_computer, auth_type, logon_type, orientation, result
''').fetchnumpy()
con.close()

y = result['is_red'].astype(bool)
pr = result['pair_rank']
src_users = result['src_user']

feat9 = ['dst_first', 'src_first', 'hour_events', 'user_events', 'dst_prior_events', 'fail_1h', 'vel_1h', 'hour', 'is_ntlm']
X_raw = np.column_stack([result[k].astype(np.float32) for k in feat9])
X_9 = np.empty((len(y), 9), dtype=np.float32)
X_9[:,0] = X_raw[:,0]; X_9[:,1] = X_raw[:,1]
ue = np.maximum(X_raw[:,3], 1); X_9[:,2] = X_raw[:,2] / ue
X_9[:,3] = X_raw[:,4]; X_9[:,4] = X_raw[:,5]; X_9[:,5] = X_raw[:,6]
h_rad = X_raw[:,7] / 24.0 * 2 * np.pi
X_9[:,6] = np.sin(h_rad); X_9[:,7] = np.cos(h_rad); X_9[:,8] = X_raw[:,8]
pf = np.zeros(len(y), dtype=np.float32); pf[0] = 1.0
for i in range(1, len(y)):
    if src_users[i] != src_users[i-1]: pf[i] = 1.0
spf = np.zeros(len(y), dtype=np.float32); spf[0] = 1.0
for i in range(1, len(y)):
    if src_users[i] != src_users[i-1]: spf[i] = 1.0
fail_rate = result['fail_1h'].astype(np.float32) / (result['vel_1h'].astype(np.float32) + 1.0)
dst_first_x_ntlm = result['dst_first'].astype(np.float32) * result['is_ntlm'].astype(np.float32)
X_13 = np.column_stack([X_9, pf.reshape(-1,1), spf.reshape(-1,1), fail_rate.reshape(-1,1), dst_first_x_ntlm.reshape(-1,1)])
X_14 = np.column_stack([X_13, np.log1p(pr.astype(np.float32)).reshape(-1,1)])

gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
for tr_idx, te_idx in gss.split(X_14, y, groups=src_users):
    pass

tr_data = lgb.Dataset(X_14[tr_idx], label=y[tr_idx])
te_data = lgb.Dataset(X_14[te_idx], label=y[te_idx], reference=tr_data)

params = {
    'objective': 'binary', 'metric': 'binary_logloss', 'verbose': -1,
    'num_leaves': 63, 'learning_rate': 0.03, 'scale_pos_weight': 3,
    'min_child_samples': 100, 'reg_alpha': 0.5, 'reg_lambda': 5.0,
    'feature_fraction': 0.8, 'bagging_fraction': 0.8, 'bagging_freq': 5,
    'seed': 42
}
model = lgb.train(params, tr_data, num_boost_round=500,
                  valid_sets=[tr_data, te_data],
                  callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)])

train_pred = model.predict(X_14[tr_idx])
test_pred = model.predict(X_14[te_idx])

train_auc = roc_auc_score(y[tr_idx], train_pred)
test_auc = roc_auc_score(y[te_idx], test_pred)

prec, rec, thr = precision_recall_curve(y[te_idx], test_pred)
f1 = np.nan_to_num(2*prec*rec/(prec+rec))
best_idx = np.argmax(f1[:-1])
best_thr = thr[best_idx]

train_tp = int(np.sum((train_pred >= best_thr) & y[tr_idx]))
train_fp = int(np.sum((train_pred >= best_thr) & (~y[tr_idx])))
test_tp = int(np.sum((test_pred >= best_thr) & y[te_idx]))
test_fp = int(np.sum((test_pred >= best_thr) & (~y[te_idx])))

n_tr_atk = int(y[tr_idx].sum())
n_te_atk = int(y[te_idx].sum())

rule_train_tp = int(np.sum((pr[tr_idx] <= 5) & y[tr_idx]))
rule_test_tp = int(np.sum((pr[te_idx] <= 5) & y[te_idx]))
rule_train_fp = int(np.sum((pr[tr_idx] <= 5) & (~y[tr_idx])))
rule_test_fp = int(np.sum((pr[te_idx] <= 5) & (~y[te_idx])))

feat_names = feat9 + ['pair_first', 'src_dst_pair_first', 'fail_rate', 'dst_first_x_ntlm', 'log_pair_rank']
importance = model.feature_importance(importance_type='gain')

log('')
log('='*60)
log('1. UNDERFITTING vs OVERFITTING')
log('='*60)
log(f'  Early stopped at round: {model.num_trees()}/500')
log(f'  Train AUC: {train_auc:.6f}')
log(f'  Test  AUC: {test_auc:.6f}')
log(f'  AUC gap:   {train_auc - test_auc:.6f}')
if train_auc - test_auc > 0.01:
    log(f'  Verdict: OVERFITTING (gap > 0.01)')
elif test_auc < 0.95:
    log(f'  Verdict: UNDERFITTING (test AUC < 0.95)')
else:
    log(f'  Verdict: GOOD FIT but weak features')

log('')
log('='*60)
log('2. TRAIN vs TEST PERFORMANCE (LGB at F1 threshold)')
log('='*60)
log(f'  LGB train: {train_tp}/{n_tr_atk} ({train_tp/n_tr_atk*100:.1f}%) FP={train_fp:,}')
log(f'  LGB test:  {test_tp}/{n_te_atk} ({test_tp/n_te_atk*100:.1f}%) FP={test_fp:,}')

log('')
log('='*60)
log('3. TRAIN vs TEST PERFORMANCE (Rule)')
log('='*60)
log(f'  Rule train: {rule_train_tp}/{n_tr_atk} ({rule_train_tp/n_tr_atk*100:.1f}%) FP={rule_train_fp:,}')
log(f'  Rule test:  {rule_test_tp}/{n_te_atk} ({rule_test_tp/n_te_atk*100:.1f}%) FP={rule_test_fp:,}')

log('')
log('='*60)
log('4. FEATURE IMPORTANCE (gain)')
log('='*60)
sorted_idx = np.argsort(importance)[::-1]
for i in range(len(feat_names)):
    log(f'  {feat_names[sorted_idx[i]]:<25} {importance[sorted_idx[i]]:>12.1f}')

log('')
log('='*60)
log('5. OVERLAP: Rule vs LGB on TEST (do they catch same attacks?)')
log('='*60)
rule_test_catches = pr[te_idx] <= 5
lgb_test_catches = test_pred >= best_thr
both = int(np.sum(rule_test_catches & lgb_test_catches & y[te_idx]))
rule_only = int(np.sum(rule_test_catches & ~lgb_test_catches & y[te_idx]))
lgb_only = int(np.sum(~rule_test_catches & lgb_test_catches & y[te_idx]))
neither = int(np.sum(~rule_test_catches & ~lgb_test_catches & y[te_idx]))
log(f'  Both catch:   {both}')
log(f'  Rule only:    {rule_only}')
log(f'  LGB only:     {lgb_only}  <-- THIS is what ML adds beyond rule')
log(f'  Neither:      {neither}')

# Save log
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = f"{LOG_DIR}/verify_{timestamp}.txt"
with open(log_path, 'w') as f:
    f.write('\n'.join(log_lines))
log(f'\nLog saved to: {log_path}')
