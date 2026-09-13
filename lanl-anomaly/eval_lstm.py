"""
eval_lstm.py — Evaluate LSTM scores on held-out test set (RUN 7 / RUN 8 / RUN 9 / RUN 10 / RUN 11)

Same GroupShuffleSplit(random_state=42) as exp2.py -> 462 train / 240 test.
LSTM scores already in DuckDB. LGB loaded from joblib.

Usage:
  ./venv/bin/python eval_lstm.py                        # RUN 7: lstm_surprisal (20feat)
  ./venv/bin/python eval_lstm.py --ae-score             # RUN 8/9: 20feat + AE recon
  ./venv/bin/python eval_lstm.py --latent-features      # RUN 10: 37feat (20+16latent+recon)
  ./venv/bin/python eval_lstm.py --features v2          # RUN 11: 22feat (20+auth_counts+smoothed_AE)
  ./venv/bin/python eval_lstm.py --features v2-raw      # RUN 11: 22feat (20+auth_counts+raw_AE)
"""
import argparse
import time
import os
import numpy as np
import duckdb
import lightgbm as lgb
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("--ae-score", action="store_true", help="Use LSTM-AE reconstruction error instead of surprisal")
ap.add_argument("--latent-features", action="store_true", help="Use 37 features: 20 orig + 16 latent PCA + recon error")
ap.add_argument("--features", choices=["v2", "v2-raw"], default=None,
                help="v2: 20orig + auth_counts + smoothed_AE | v2-raw: same but raw AE")
cli_args = ap.parse_args()

t_start = time.time()
step_timings = []  # (label, seconds)

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
       uv.lstm_surprisal,
       uv.lstm_ae_recon_error,
       CAST(uv.auth_count_1h AS DOUBLE) AS auth_count_1h,
       CAST(uv.auth_count_24h AS DOUBLE) AS auth_count_24h
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


# ============================================================
# STEP 1: SQL CTE chain (streaming via DBAPI cursor)
# ============================================================
section_header("STEP 1: LOAD FEATURES + LSTM SCORES")
t0 = timer_start()

DB_PATH = 'data/raw/lanl/lanl.duckdb'
con = duckdb.connect(DB_PATH, read_only=True)
con.execute("SET threads = 4")
con.execute("SET memory_limit = '6GB'")
con.execute("SET preserve_insertion_order = false")

cur = con.cursor()

# Count rows for pre-allocation (CTE chain preserves row count — all JOINs are many-to-one)
n = cur.execute("SELECT COUNT(*) FROM feat").fetchone()[0]
print(f"  Row count: {n:,}")

# Now fetch with streaming
cur.execute(SQL_QUERY)
col_names = [d[0] for d in cur.description]
ncols = len(col_names)

# Pre-allocate typed arrays
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
timer_end("STEP 1: SQL CTE query", t0)
print(f"  [{time.time()-t_start:6.1f}s] Query done")

# Stream dst_computer separately (not in main SELECT to save memory)
section_header("STEP 1b: LOAD dst_computer")
t0_db = timer_start()
con_db = duckdb.connect(DB_PATH, read_only=True)
con_db.execute("SET threads = 2")
con_db.execute("SET memory_limit = '6GB'")
cur_db = con_db.cursor()
cur_db.execute("""
SELECT dst_computer FROM feat
ORDER BY time, src_user, dst_user, src_computer, dst_computer,
         auth_type, logon_type, orientation, result
""")
dst_computers = np.empty(n, dtype=object)
filled_dc = 0
while filled_dc < n:
    rows = cur_db.fetchmany(500_000)
    if not rows:
        break
    blen = len(rows)
    for k in range(blen):
        dst_computers[filled_dc + k] = rows[k][0]
    filled_dc += blen
    if filled_dc % 2_000_000 == 0 or filled_dc < 500_000:
        print(f"    dst_computer: {filled_dc:>10,}/{n:,}  RSS={mem_mb():.0f}MB")
cur_db.close()
con_db.close()
import gc; gc.collect()
timer_end("STEP 1b: dst_computer load", t0_db)
print(f"  dst_computer loaded: {step_timings[-1][1]:.1f}s  RSS={mem_mb():.0f}MB")

# ============================================================
# STEP 2: Build X_21 features (copy from exp2.py)
# ============================================================
section_header("STEP 2: BUILD X_21 FEATURES")
t0 = timer_start()

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
pair_interval_ratio = result['pair_interval_ratio'].astype(np.float32)
iat_zscore = result['iat_zscore'].astype(np.float32)
velocity_ratio = result['velocity_ratio'].astype(np.float32)
machine_popularity = result['machine_popularity'].astype(np.float32)
lstm_surprisal = result['lstm_surprisal'].astype(np.float64)
lstm_ae_recon_error = result['lstm_ae_recon_error'].astype(np.float64)
auth_count_1h = result['auth_count_1h'].astype(np.float32)
auth_count_24h = result['auth_count_24h'].astype(np.float32)

del result, pair_interval_ratio
import gc; gc.collect()

X_16 = np.column_stack([X_14, pair_freq_ratio.reshape(-1,1), is_rare_hour.reshape(-1,1)])
del X_14, pair_freq_ratio, is_rare_hour

# pairs_last_100: distinct destinations in sliding window of last 100 events per user
# Computed from in-memory arrays (same ordering as main SQL query, no second DuckDB query)
print("  Computing pairs_last_100 (sliding window)...")
pairs_last_raw = np.zeros(n, dtype=np.float32)

change_mask = np.zeros(n, dtype=bool)
change_mask[0] = True
change_mask[1:] = src_users[1:] != src_users[:-1]
change_points = np.where(change_mask)[0]
user_starts = change_points
user_ends = np.append(change_points[1:], n)
total_users = len(change_points)

done = 0
for i in range(total_users):
    start = user_starts[i]
    end = user_ends[i]
    u_dsts = dst_computers[start:end]
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

pairs_last = pairs_last_raw
print(f"  pairs_last_100 computed")
del dst_computers, change_mask, change_points, user_starts, user_ends
import gc; gc.collect()

X_17 = np.column_stack([X_16, pairs_last.reshape(-1,1)])

X_21 = np.column_stack([X_17, iat_zscore.reshape(-1,1), velocity_ratio.reshape(-1,1),
                         machine_popularity.reshape(-1,1), lstm_ae_recon_error.reshape(-1,1).astype(np.float32)])
fnames21 = ['dst_first','src_first','hour_ratio','dst_prior_events','fail_1h',
            'vel_1h','hour_sin','hour_cos','is_ntlm',
            'pair_first','src_dst_pair_first','fail_rate','dst_first_x_ntlm',
            'log_pair_rank','pair_freq_ratio','is_rare_hour','pairs_last_100',
            'iat_zscore','velocity_ratio','machine_popularity','lstm_ae_recon_error']

del X_16, X_17
import gc; gc.collect()

print(f"  X_21 shape={X_21.shape}  {X_21.nbytes/1024/1024:.0f} MB")
assert X_21.shape == (n, 21)
assert not np.any(np.isnan(X_21))
assert not np.any(np.isinf(X_21))

# ============================================================
# STEP 2c: V2 FEATURES (auth_counts + temporal smoothing)
# ============================================================
if cli_args.features:
    section_header("STEP 2c: V2 FEATURES")
    t0_v2 = timer_start()

    # Temporal smoothing: 10-event rolling mean of AE recon error per user
    print("  Computing smoothed AE recon error (10-event rolling mean per user)...")
    ae_smoothed = np.zeros(n, dtype=np.float32)
    window = 10

    # Find user boundaries (src_users already sorted from SQL ORDER BY)
    change_mask = np.zeros(n, dtype=bool)
    change_mask[0] = True
    change_mask[1:] = src_users[1:] != src_users[:-1]
    u_starts = np.where(change_mask)[0]
    u_ends = np.append(u_starts[1:], n)

    for i in range(len(u_starts)):
        s, e = u_starts[i], u_ends[i]
        n_u = e - s
        ae_slice = lstm_ae_recon_error[s:e].astype(np.float32)
        if n_u <= window:
            # Not enough events for full window, use all available
            ae_smoothed[s:e] = ae_slice.mean()
        else:
            # Prefix sum for fast rolling mean
            cs = np.cumsum(ae_slice)
            # First window-1 elements: partial windows
            for j in range(window - 1):
                ae_smoothed[s + j] = cs[j] / (j + 1)
            # Full windows: use prefix sum difference
            ae_smoothed[s + window - 1:e] = (cs[window - 1:] - np.concatenate([[0], cs[:n_u - window]])) / window

    print(f"  Smoothed AE stats: mean={ae_smoothed.mean():.6f} std={ae_smoothed.std():.6f}")
    print(f"  Raw AE stats:      mean={lstm_ae_recon_error.mean():.6f} std={lstm_ae_recon_error.std():.6f}")

    # Build X_23: X_21 + auth_count_1h + auth_count_24h + smoothed AE (replacing raw AE)
    # Use smoothed AE as the AE feature instead of raw
    X_21_no_ae = X_21[:, :20]  # first 20 features (exclude raw AE)
    if cli_args.features == 'v2':
        X_23 = np.column_stack([X_21_no_ae, ae_smoothed.reshape(-1,1),
                                auth_count_1h.reshape(-1,1), auth_count_24h.reshape(-1,1)])
        fnames23 = fnames21[:20] + ['lstm_ae_smoothed', 'auth_count_1h', 'auth_count_24h']
    else:  # v2-raw
        X_23 = np.column_stack([X_21_no_ae, lstm_ae_recon_error.reshape(-1,1).astype(np.float32),
                                auth_count_1h.reshape(-1,1), auth_count_24h.reshape(-1,1)])
        fnames23 = fnames21[:20] + ['lstm_ae_recon_error', 'auth_count_1h', 'auth_count_24h']

    print(f"  X_23 shape={X_23.shape}  {X_23.nbytes/1024/1024:.0f} MB")
    assert X_23.shape == (n, 23)
    assert not np.any(np.isnan(X_23))
    assert not np.any(np.isinf(X_23))

    del auth_count_1h, auth_count_24h, ae_smoothed, change_mask, u_starts, u_ends
    import gc; gc.collect()

    timer_end("STEP 2c: V2 features", t0_v2)
    print(f"  [{time.time()-t_start:6.1f}s] V2 features built")

timer_end("STEP 2: Feature build", t0)
print(f"  [{time.time()-t_start:6.1f}s] Features built")
del iat_zscore, velocity_ratio, machine_popularity, pairs_last
import gc; gc.collect()

# ============================================================
# STEP 2b: LOAD LATENT FEATURES (if --latent-features)
# ============================================================
if cli_args.latent_features:
    section_header("STEP 2b: LOAD LATENT FEATURES (16 PCA dims)")
    t0_lat = timer_start()

    con_lat = duckdb.connect(DB_PATH, read_only=True)
    con_lat.execute("SET threads = 2")
    con_lat.execute("SET memory_limit = '6GB'")

    # Check columns exist
    n_cols = con_lat.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_name='feat' AND column_name LIKE 'latent_%'"
    ).fetchone()[0]
    assert n_cols == 16, f"Expected 16 latent columns, found {n_cols}"

    # Stream latent columns with same ordering
    cur_lat = con_lat.cursor()
    cur_lat.execute("""
        SELECT latent_0, latent_1, latent_2, latent_3, latent_4, latent_5, latent_6, latent_7,
               latent_8, latent_9, latent_10, latent_11, latent_12, latent_13, latent_14, latent_15
        FROM feat
        ORDER BY time, src_user, dst_user, src_computer, dst_computer,
                 auth_type, logon_type, orientation, result
    """)

    latent = np.empty((n, 16), dtype=np.float32)
    filled_lat = 0
    while filled_lat < n:
        rows = cur_lat.fetchmany(500_000)
        if not rows:
            break
        blen = len(rows)
        latent[filled_lat:filled_lat+blen] = np.array(rows, dtype=np.float32)
        filled_lat += blen
        if filled_lat % 2_000_000 == 0 or filled_lat < 500_000:
            print(f"    latent: {filled_lat:>10,}/{n:,}  RSS={mem_mb():.0f}MB")
    cur_lat.close()
    con_lat.close()
    import gc; gc.collect()

    # Concatenate: 21 features + 16 latent = 37 features
    X_37 = np.column_stack([X_21, latent])
    fnames37 = fnames21 + [f'latent_{i}' for i in range(16)]

    del latent
    import gc; gc.collect()

    print(f"  X_37 shape={X_37.shape}  {X_37.nbytes/1024/1024:.0f} MB")
    assert X_37.shape == (n, 37)
    assert not np.any(np.isnan(X_37))
    assert not np.any(np.isinf(X_37))
    print(f"  Latent stats: min={X_37[:, 21:].min():.4f} max={X_37[:, 21:].max():.4f} mean={X_37[:, 21:].mean():.4f}")
    timer_end("STEP 2b: Latent load", t0_lat)
    print(f"  [{time.time()-t_start:6.1f}s] Latent features loaded")

    # Use X_37 for the rest of the pipeline
    X = X_37
    fnames = fnames37
    n_features = 37
    del X_21
elif cli_args.features:
    X = X_23
    fnames = fnames23
    n_features = 23
    del X_21
else:
    X = X_21
    fnames = fnames21
    n_features = 21

# ============================================================
# STEP 3: Train/test split (same as exp2.py)
# ============================================================
section_header("STEP 3: TRAIN/TEST SPLIT")
t0 = timer_start()
gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
for tr_idx, te_idx in gss.split(X, y, groups=src_users):
    pass

y_train, y_test = y[tr_idx], y[te_idx]
n_train_red = int(y_train.sum())
n_test_red = int(y_test.sum())
assert n_train_red + n_test_red == 702, f"Red split mismatch: {n_train_red}+{n_test_red} != 702"
assert n_test_red == 240, f"Expected 240 test red, got {n_test_red}"
print(f"  Train: {len(tr_idx):,} rows ({n_train_red} red)")
print(f"  Test:  {len(te_idx):,} rows ({n_test_red} red)")
print(f"  Verified: {n_train_red}+{n_test_red}={n_train_red+n_test_red} red")
timer_end("STEP 3: Train/test split", t0)
print(f"  [{time.time()-t_start:6.1f}s] Split done")

# ============================================================
# STEP 4: LOAD LSTM scores from DuckDB
# ============================================================
section_header("STEP 4: LOAD LSTM SCORES")
t0 = timer_start()

if cli_args.ae_score:
    score_col = "lstm_ae_recon_error"
    model_label = "LSTM-AE"
else:
    score_col = "lstm_surprisal"
    model_label = "LSTM-surprisal"

lstm_scores = lstm_surprisal if score_col == "lstm_surprisal" else lstm_ae_recon_error

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
timer_end("STEP 4: LSTM scores", t0)
print(f"  [{time.time()-t_start:6.1f}s] LSTM scores loaded")

# ============================================================
# STEP 5: Train LGB on train set, predict on test set
# ============================================================
section_header("STEP 5: TRAIN + PREDICT LGB")
t0 = timer_start()

t_train = time.time()
lgb_model = lgb.LGBMClassifier(
    num_leaves=63, learning_rate=0.03, n_estimators=500,
    scale_pos_weight=3, min_child_samples=100,
    reg_alpha=0.5, reg_lambda=5.0,
    random_state=42, n_jobs=-1, verbose=-1
)
lgb_model.fit(X[tr_idx], y_train)
print(f"  LGB train: {time.time()-t_train:.1f}s")

lgb_train_scores = lgb_model.predict_proba(X[tr_idx])[:, 1]
lgb_test_scores = lgb_model.predict_proba(X[te_idx])[:, 1]
print(f"  LGB predict: {time.time()-t_train:.1f}s total")
timer_end("STEP 5: LGB train+predict", t0)
print(f"  [{time.time()-t_start:6.1f}s] LGB done")

# ============================================================
# STEP 6: EVALUATE STANDALONE MODELS ON TEST SET
# ============================================================
section_header("STEP 6: STANDALONE EVALUATION")
t0 = timer_start()
print(f"  Test set: {len(te_idx):,} rows ({n_test_red} red)\n")

print("  LSTM standalone:")
lstm_eval = eval_it("LSTM", lstm_test, y_test)

print("\n  LGB standalone:")
lgb_eval = eval_it(f"LGB-{n_features}feat", lgb_test_scores, y_test)
timer_end("STEP 6: Standalone eval", t0)

# ============================================================
# STEP 7: OVERLAP ANALYSIS (test set, red events only)
# ============================================================
section_header("STEP 7: OVERLAP ANALYSIS (LSTM vs LGB)")
t0 = timer_start()

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
timer_end("STEP 7: Overlap analysis", t0)

# ============================================================
# STEP 8: ENSEMBLE SWEEP
# ============================================================
section_header("STEP 8: ENSEMBLE SWEEP (alpha * LSTM + (1-alpha) * LGB)")
t0 = timer_start()

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
timer_end("STEP 8: Ensemble sweep", t0)
print(f"  [{time.time()-t_start:6.1f}s] Ensemble sweep done")

# ============================================================
# STEP 9: SUMMARY
# ============================================================
section_header("SUMMARY")
print(f"  Model:    {model_label} (2ep, bs128, 128h 2l ctx50)")
print(f"  LGB:      {n_features} features")
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

total = time.time() - t_start
print(f"\n  TIMING BREAKDOWN")
print(f"  {'─'*50}")
for label, dt in step_timings:
    print(f"    {label:<30} {dt:>7.1f}s  ({100*dt/total:4.1f}%)")
print(f"    {'─'*48}")
print(f"    {'Total':<30} {total:>7.1f}s")
print(f"\n  Total runtime: {total:.1f}s ({total/60:.1f} min)")
