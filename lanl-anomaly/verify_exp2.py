#!/usr/bin/env python3
"""verify_exp2.py - Test each SQL query before running exp2.py.
Run: python3 verify_exp2.py 2>&1 | tee logs/verify_exp2.txt
Time: ~3-5 min"""
import duckdb, numpy as np, time, sys

PASS = "PASS"
FAIL = "FAIL"
results = {}

def test(name, fn):
    t0 = time.time()
    try:
        val = fn()
        dt = time.time() - t0
        print(f"  [{PASS}] {name} ({dt:.1f}s) -> {val}")
        results[name] = (PASS, val, dt)
    except Exception as e:
        dt = time.time() - t0
        print(f"  [{FAIL}] {name} ({dt:.1f}s) -> {e}")
        results[name] = (FAIL, str(e), dt)

print("="*70)
print("verify_exp2.py - Testing SQL queries step by step")
print("="*70)

# ============================================================
# STEP 1: Base 14feat query (same as exp1)
# ============================================================
print("\n--- Step 1: Base 14feat query ---")

def test_base_14():
    con = duckdb.connect('data/raw/lanl/lanl.duckdb', read_only=True)
    r = con.execute("""
    SELECT dst_first, src_first, hour_events, user_events,
           CAST(dst_prior_events AS BIGINT) AS dst_prior_events,
           CAST(fail_1h AS BIGINT) AS fail_1h,
           CAST(vel_1h AS BIGINT) AS vel_1h,
           hour, is_red, src_computer, src_user,
           CASE WHEN ROW_NUMBER() OVER (PARTITION BY src_user, src_computer, dst_computer
                ORDER BY time, dst_user, auth_type, logon_type, orientation, result) = 1
                THEN 1.0 ELSE 0.0 END AS pair_first,
           CASE WHEN ROW_NUMBER() OVER (PARTITION BY src_computer, dst_computer
                ORDER BY time, src_user, dst_user, auth_type, logon_type, orientation, result) = 1
                THEN 1.0 ELSE 0.0 END AS src_dst_pair_first,
           CAST(fail_1h AS DOUBLE) / (CAST(vel_1h AS DOUBLE) + 1.0) AS fail_rate,
           CASE WHEN dst_first = 1 AND is_ntlm THEN 1.0 ELSE 0.0 END AS dst_first_x_ntlm,
           is_ntlm,
           CAST(ROW_NUMBER() OVER (PARTITION BY src_user, src_computer, dst_computer
                ORDER BY time, dst_user, auth_type, logon_type, orientation, result) AS DOUBLE) AS pair_rank
    FROM feat
    ORDER BY time, src_user, dst_user, src_computer, dst_computer, auth_type, logon_type, orientation, result
    """).fetchnumpy()
    con.close()
    n = len(r)
    n_red = int(r['is_red'].sum())
    return f"rows={n:,} red={n_red}"

test("base_14feat", test_base_14)

# ============================================================
# STEP 2: pair_freq_ratio on U737 (small test)
# ============================================================
print("\n--- Step 2: pair_freq_ratio (U737 subset) ---")

def test_pf_small():
    con = duckdb.connect('data/raw/lanl/lanl.duckdb', read_only=True)
    r = con.execute("""
    WITH user_totals AS (
        SELECT src_user, COUNT(*) AS total FROM feat
        WHERE src_user = 'U737@DOM1' GROUP BY src_user
    ),
    pair_counts AS (
        SELECT src_user, src_computer, dst_computer, COUNT(*) AS pair_events
        FROM feat WHERE src_user = 'U737@DOM1'
        GROUP BY src_user, src_computer, dst_computer
    )
    SELECT f.src_user, f.src_computer, f.dst_computer, f.time,
           CAST(pc.pair_events AS DOUBLE) / ut.total AS pair_freq_ratio
    FROM feat f
    JOIN user_totals ut ON f.src_user = ut.src_user
    JOIN pair_counts pc ON f.src_user = pc.src_user
        AND f.src_computer = pc.src_computer
        AND f.dst_computer = pc.dst_computer
    WHERE f.src_user = 'U737@DOM1'
    ORDER BY f.time
    """).fetchdf()
    con.close()
    n = len(r)
    has_nan = r['pair_freq_ratio'].isna().any()
    min_pf = r['pair_freq_ratio'].min()
    max_pf = r['pair_freq_ratio'].max()
    return f"rows={n} nan={has_nan} min={min_pf:.6f} max={max_pf:.6f}"

test("pf_ratio_U737", test_pf_small)

# ============================================================
# STEP 3: pair_freq_ratio FULL dataset
# ============================================================
print("\n--- Step 3: pair_freq_ratio (FULL dataset) ---")

def test_pf_full():
    con = duckdb.connect('data/raw/lanl/lanl.duckdb', read_only=True)
    r = con.execute("""
    WITH user_totals AS (
        SELECT src_user, COUNT(*) AS total FROM feat GROUP BY src_user
    ),
    pair_counts AS (
        SELECT src_user, src_computer, dst_computer, COUNT(*) AS pair_events
        FROM feat GROUP BY src_user, src_computer, dst_computer
    )
    SELECT f.src_user, f.src_computer, f.dst_computer, f.time,
           CAST(pc.pair_events AS DOUBLE) / ut.total AS pair_freq_ratio
    FROM feat f
    JOIN user_totals ut ON f.src_user = ut.src_user
    JOIN pair_counts pc ON f.src_user = pc.src_user
        AND f.src_computer = pc.src_computer
        AND f.dst_computer = pc.dst_computer
    ORDER BY f.time, f.src_user, f.dst_user, f.src_computer, f.dst_computer,
             f.auth_type, f.logon_type, f.orientation, f.result
    """).fetchdf()
    con.close()
    n = len(r)
    has_nan = r['pair_freq_ratio'].isna().any()
    return f"rows={n:,} nan={has_nan}"

test("pf_ratio_FULL", test_pf_full)

# ============================================================
# STEP 4: is_rare_hour on U737 (small test)
# ============================================================
print("\n--- Step 4: is_rare_hour (U737 subset) ---")

def test_ih_small():
    con = duckdb.connect('data/raw/lanl/lanl.duckdb', read_only=True)
    r = con.execute("""
    WITH hour_dist AS (
        SELECT src_user, hour, COUNT(*) AS cnt,
            NTILE(10) OVER (PARTITION BY src_user ORDER BY COUNT(*) ASC) AS decile
        FROM feat WHERE is_red = FALSE AND src_user = 'U737@DOM1'
        GROUP BY src_user, hour
    ),
    rare_hours AS (
        SELECT src_user, hour FROM hour_dist WHERE decile <= 2
    )
    SELECT f.src_user, f.src_computer, f.dst_computer, f.time,
           CASE WHEN rh.src_user IS NOT NULL THEN 1.0 ELSE 0.0 END AS is_rare_hour
    FROM feat f
    LEFT JOIN rare_hours rh ON f.src_user = rh.src_user AND f.hour = rh.hour
    WHERE f.src_user = 'U737@DOM1'
    ORDER BY f.time
    """).fetchdf()
    con.close()
    n = len(r)
    pct_rare = r['is_rare_hour'].mean()
    return f"rows={n} pct_rare={pct_rare:.4f}"

test("is_rare_hour_U737", test_ih_small)

# ============================================================
# STEP 5: is_rare_hour FULL dataset
# ============================================================
print("\n--- Step 5: is_rare_hour (FULL dataset) ---")

def test_ih_full():
    con = duckdb.connect('data/raw/lanl/lanl.duckdb', read_only=True)
    r = con.execute("""
    WITH hour_dist AS (
        SELECT src_user, hour, COUNT(*) AS cnt,
            NTILE(10) OVER (PARTITION BY src_user ORDER BY COUNT(*) ASC) AS decile
        FROM feat WHERE is_red = FALSE
        GROUP BY src_user, hour
    ),
    rare_hours AS (
        SELECT src_user, hour FROM hour_dist WHERE decile <= 2
    )
    SELECT f.src_user, f.src_computer, f.dst_computer, f.time,
           CASE WHEN rh.src_user IS NOT NULL THEN 1.0 ELSE 0.0 END AS is_rare_hour
    FROM feat f
    LEFT JOIN rare_hours rh ON f.src_user = rh.src_user AND f.hour = rh.hour
    ORDER BY f.time, f.src_user, f.dst_user, f.src_computer, f.dst_computer,
             f.auth_type, f.logon_type, f.orientation, f.result
    """).fetchdf()
    con.close()
    n = len(r)
    has_nan = r['is_rare_hour'].isna().any()
    pct_rare = r['is_rare_hour'].mean()
    return f"rows={n:,} nan={has_nan} pct_rare={pct_rare:.4f}"

test("is_rare_hour_FULL", test_ih_full)

# ============================================================
# STEP 6: pairs_last_100 data on U737 (small test)
# ============================================================
print("\n--- Step 6: pairs_last_100 data (U737 subset) ---")

def test_pl_small():
    con = duckdb.connect('data/raw/lanl/lanl.duckdb', read_only=True)
    r = con.execute("""
    SELECT src_user, dst_computer, time,
           ROW_NUMBER() OVER (PARTITION BY src_user ORDER BY time) AS rn
    FROM feat WHERE src_user = 'U737@DOM1'
    ORDER BY src_user, time
    """).fetchdf()
    con.close()
    n = len(r)
    max_rn = r['rn'].max()
    n_users = r['src_user'].nunique()
    return f"rows={n} users={n_users} max_rn={max_rn}"

test("pairs_last_100_U737", test_pl_small)

# ============================================================
# STEP 7: pairs_last_100 data FULL dataset
# ============================================================
print("\n--- Step 7: pairs_last_100 data (FULL dataset) ---")

def test_pl_full():
    con = duckdb.connect('data/raw/lanl/lanl.duckdb', read_only=True)
    r = con.execute("""
    SELECT src_user, dst_computer, time,
           ROW_NUMBER() OVER (PARTITION BY src_user ORDER BY time) AS rn
    FROM feat
    ORDER BY src_user, time
    """).fetchdf()
    con.close()
    n = len(r)
    n_users = r['src_user'].nunique()
    return f"rows={n:,} users={n_users}"

test("pairs_last_100_FULL", test_pl_full)

# ============================================================
# STEP 8: pairs_last_100 Python sliding window (U737 only)
# ============================================================
print("\n--- Step 8: pairs_last_100 Python sliding window (U737) ---")

def test_sliding_small():
    con = duckdb.connect('data/raw/lanl/lanl.duckdb', read_only=True)
    r = con.execute("""
    SELECT src_user, dst_computer, time,
           ROW_NUMBER() OVER (PARTITION BY src_user ORDER BY time) AS rn
    FROM feat WHERE src_user = 'U737@DOM1'
    ORDER BY src_user, time
    """).fetchdf()
    con.close()

    dsts = r['dst_computer'].values
    n = len(dsts)
    pairs_last = np.zeros(n, dtype=np.float32)
    s = set()
    for j in range(n):
        s.add(dsts[j])
        if j >= 100:
            s.discard(dsts[j - 100])
        pairs_last[j] = len(s)

    has_nan = np.any(np.isnan(pairs_last))
    min_pl = pairs_last.min()
    max_pl = pairs_last.max()
    mean_pl = pairs_last.mean()
    return f"rows={n} nan={has_nan} min={min_pl:.0f} max={max_pl:.0f} mean={mean_pl:.1f}"

test("sliding_U737", test_sliding_small)

# ============================================================
# STEP 9: Check ORDER BY matches between queries
# ============================================================
print("\n--- Step 9: Verify ORDER BY consistency ---")

def test_order():
    con = duckdb.connect('data/raw/lanl/lanl.duckdb', read_only=True)
    # Get first 5 rows from base query
    base = con.execute("""
    SELECT time, src_user, dst_user, src_computer, dst_computer,
           auth_type, logon_type, orientation, result
    FROM feat
    ORDER BY time, src_user, dst_user, src_computer, dst_computer,
             auth_type, logon_type, orientation, result
    LIMIT 5
    """).fetchdf()

    # Get first 5 rows from pair_freq query
    pf = con.execute("""
    WITH user_totals AS (
        SELECT src_user, COUNT(*) AS total FROM feat GROUP BY src_user
    ),
    pair_counts AS (
        SELECT src_user, src_computer, dst_computer, COUNT(*) AS pair_events
        FROM feat GROUP BY src_user, src_computer, dst_computer
    )
    SELECT f.time, f.src_user, f.dst_user, f.src_computer, f.dst_computer,
           f.auth_type, f.logon_type, f.orientation, f.result
    FROM feat f
    JOIN user_totals ut ON f.src_user = ut.src_user
    JOIN pair_counts pc ON f.src_user = pc.src_user
        AND f.src_computer = pc.src_computer
        AND f.dst_computer = pc.dst_computer
    ORDER BY f.time, f.src_user, f.dst_user, f.src_computer, f.dst_computer,
             f.auth_type, f.logon_type, f.orientation, f.result
    LIMIT 5
    """).fetchdf()
    con.close()

    match = base.equals(pf)
    return f"match={match}"

test("order_consistency", test_order)

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "="*70)
print("SUMMARY")
print("="*70)
n_pass = sum(1 for v in results.values() if v[0] == PASS)
n_fail = sum(1 for v in results.values() if v[0] == FAIL)
for name, (status, val, dt) in results.items():
    print(f"  {status} {name:<25} {val}")
print(f"\n  {n_pass}/{n_pass+n_fail} passed")
if n_fail > 0:
    print("  FIX FAILURES BEFORE RUNNING exp2.py")
    sys.exit(1)
else:
    print("  ALL GOOD - safe to run exp2.py")
