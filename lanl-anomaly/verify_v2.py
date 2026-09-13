"""verify_v2.py - Verify all 6 proposed behavioral features.
Run: python3 verify_v2.py 2>&1 | tee logs/verify_v2.txt
Time: ~2-3 min on full dataset."""
import duckdb, os
from datetime import datetime

os.makedirs("logs/verify", exist_ok=True)
con = duckdb.connect('data/raw/lanl/lanl.duckdb', read_only=True)

def q(sql, desc):
    print(f"\n{'='*70}")
    print(f"  {desc}")
    print('='*70)
    try:
        r = con.execute(sql).fetchdf()
        print(r.to_string(index=False))
        return r
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

# ============================================================
# FEATURE 1: hour_deviation
# ============================================================
q("""
WITH user_mean AS (
  SELECT src_user,
    AVG(SIN(hour * 2 * 3.14159265 / 24)) AS sin_mean,
    AVG(COS(hour * 2 * 3.14159265 / 24)) AS cos_mean
  FROM feat WHERE is_red = FALSE
  GROUP BY src_user
),
events AS (
  SELECT f.src_user, f.hour, f.is_red,
    SQRT(
      POW(SIN(f.hour * 2 * 3.14159265 / 24) - u.sin_mean, 2) +
      POW(COS(f.hour * 2 * 3.14159265 / 24) - u.cos_mean, 2)
    ) AS hour_dev
  FROM feat f JOIN user_mean u ON f.src_user = u.src_user
)
SELECT src_user,
       CASE WHEN is_red THEN 'RED' ELSE 'NORM' END AS label,
       ROUND(AVG(hour_dev), 4) AS avg_dev,
       ROUND(MEDIAN(hour_dev), 4) AS med_dev,
       COUNT(*) AS cnt
FROM events
WHERE src_user IN ('U737@DOM1','U1653@DOM1','U86@DOM1')
GROUP BY src_user, is_red
ORDER BY src_user, is_red
""", "FEATURE 1: hour_deviation (circular distance from user mean hour)")

# ============================================================
# FEATURE 2: pairs_last_100
# ============================================================
q("""
WITH numbered AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY src_user ORDER BY time) AS rn
  FROM feat WHERE src_user IN ('U737@DOM1','U1653@DOM1')
),
sliding AS (
  SELECT a.src_user, a.is_red, a.rn,
    (SELECT COUNT(DISTINCT b.dst_computer)
     FROM numbered b
     WHERE b.src_user = a.src_user
       AND b.rn BETWEEN a.rn - 100 AND a.rn) AS pairs_last_100
  FROM numbered a
)
SELECT src_user,
       CASE WHEN is_red THEN 'RED' ELSE 'NORM' END AS label,
       ROUND(AVG(pairs_last_100), 2) AS avg_pairs,
       MIN(pairs_last_100) AS min_pairs,
       MAX(pairs_last_100) AS max_pairs,
       COUNT(*) AS cnt
FROM sliding
GROUP BY src_user, is_red
ORDER BY src_user, is_red
""", "FEATURE 2: pairs_last_100 (distinct pairs in sliding window)")

# ============================================================
# FEATURE 3: pair_freq_ratio
# ============================================================
q("""
WITH user_totals AS (
  SELECT src_user, COUNT(*) AS total FROM feat GROUP BY src_user
),
pair_counts AS (
  SELECT src_user, src_computer, dst_computer, COUNT(*) AS pair_events,
         MAX(CAST(is_red AS INT)) AS has_red
  FROM feat
  GROUP BY src_user, src_computer, dst_computer
)
SELECT pc.src_user,
       CASE WHEN pc.has_red = 1 THEN 'PAIR_W_RED' ELSE 'PAIR_NORM' END AS pair_type,
       COUNT(DISTINCT pc.src_computer || pc.dst_computer) AS n_pairs,
       ROUND(AVG(pc.pair_events * 1.0 / ut.total), 6) AS avg_freq_ratio,
       ROUND(MIN(pc.pair_events * 1.0 / ut.total), 6) AS min_freq,
       ROUND(MAX(pc.pair_events * 1.0 / ut.total), 6) AS max_freq
FROM pair_counts pc JOIN user_totals ut ON pc.src_user = ut.src_user
WHERE pc.src_user IN ('U737@DOM1','U1653@DOM1','U86@DOM1')
GROUP BY pc.src_user, pc.has_red
ORDER BY pc.src_user, pc.has_red
""", "FEATURE 3: pair_freq_ratio (pair events / user total events)")

# ============================================================
# FEATURE 4: vel_ratio_user
# ============================================================
q("""
WITH user_vel_mean AS (
  SELECT src_user, AVG(vel_1h) AS mean_vel
  FROM feat WHERE is_red = FALSE GROUP BY src_user
)
SELECT f.src_user,
       CASE WHEN f.is_red THEN 'RED' ELSE 'NORM' END AS label,
       ROUND(AVG(f.vel_1h * 1.0 / u.mean_vel), 4) AS avg_vel_ratio,
       ROUND(MEDIAN(f.vel_1h * 1.0 / u.mean_vel), 4) AS med_vel_ratio,
       COUNT(*) AS cnt
FROM feat f JOIN user_vel_mean u ON f.src_user = u.src_user
WHERE f.src_user IN ('U737@DOM1','U1653@DOM1','U86@DOM1')
GROUP BY f.src_user, f.is_red
ORDER BY f.src_user, f.is_red
""", "FEATURE 4: vel_ratio_user (vel_1h / user mean vel)")

# ============================================================
# FEATURE 5: fail_ratio_user
# ============================================================
q("""
WITH user_fail_mean AS (
  SELECT src_user, AVG(fail_1h) AS mean_fail
  FROM feat WHERE is_red = FALSE GROUP BY src_user
)
SELECT f.src_user,
       CASE WHEN f.is_red THEN 'RED' ELSE 'NORM' END AS label,
       ROUND(AVG(f.fail_1h * 1.0 / u.mean_fail), 4) AS avg_fail_ratio,
       ROUND(MEDIAN(f.fail_1h * 1.0 / u.mean_fail), 4) AS med_fail_ratio,
       COUNT(*) AS cnt
FROM feat f JOIN user_fail_mean u ON f.src_user = u.src_user
WHERE f.src_user IN ('U737@DOM1','U1653@DOM1','U86@DOM1')
GROUP BY f.src_user, f.is_red
ORDER BY f.src_user, f.is_red
""", "FEATURE 5: fail_ratio_user (fail_1h / user mean fail)")

# ============================================================
# FEATURE 6: is_rare_hour
# ============================================================
q("""
WITH hour_dist AS (
  SELECT src_user, hour, COUNT(*) AS cnt,
    NTILE(10) OVER (PARTITION BY src_user ORDER BY COUNT(*) ASC) AS decile
  FROM feat WHERE is_red = FALSE
  GROUP BY src_user, hour
),
rare_hours AS (
  SELECT src_user, hour FROM hour_dist WHERE decile <= 2
)
SELECT f.src_user,
       CASE WHEN f.is_red THEN 'RED' ELSE 'NORM' END AS label,
       ROUND(AVG(CASE WHEN rh.hour IS NOT NULL THEN 1.0 ELSE 0.0 END), 4) AS pct_rare_hour,
       COUNT(*) AS cnt
FROM feat f LEFT JOIN rare_hours rh ON f.src_user = rh.src_user AND f.hour = rh.hour
WHERE f.src_user IN ('U737@DOM1','U1653@DOM1','U86@DOM1')
GROUP BY f.src_user, f.is_red
ORDER BY f.src_user, f.is_red
""", "FEATURE 6: is_rare_hour (fraction of events in user's rare hours)")

# ============================================================
# SUMMARY: Pass/Fail
# ============================================================
print(f"\n{'='*70}")
print("  PASS/FAIL SUMMARY")
print('='*70)
print("""
  Check the output above for each feature:

  Feature 1 (hour_deviation): PASS if RED avg_dev > NORM avg_dev for 2/3 users
  Feature 2 (pairs_last_100): PASS if RED and NORM show different ranges
  Feature 3 (pair_freq_ratio): PASS if PAIR_W_RED avg_freq < PAIR_NORM avg_freq
  Feature 4 (vel_ratio_user):  PASS if RED vel_ratio != NORM for 1/2 users (skip U1653)
  Feature 5 (fail_ratio_user): PASS if RED fail_ratio > NORM for 2/3 users
  Feature 6 (is_rare_hour):    PASS if RED pct_rare_hour > NORM for 2/3 users

  Features that PASS go into the pipeline. Features that FAIL get dropped.
""")

con.close()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
print(f"Done. Run: python3 verify_v2.py 2>&1 | tee logs/verify/verify_v2_{ts}.txt")
