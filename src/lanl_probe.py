"""LANL feasibility probe: do red-team auth events separate from normal behavior?

Reads feat.parquet, compares three event groups:
  A = red-team matched events (label 1)
  B = non-red events of the 104 compromised users (their own normal baseline)
  C = events of normal users

Reports per-feature means and ROC-AUC (A vs B and A vs C).
"""
import duckdb
import pandas as pd
from sklearn.metrics import roc_auc_score

con = duckdb.connect()

con.execute("""
CREATE OR REPLACE TABLE feat AS SELECT * FROM 'data/raw/lanl/feat.parquet'
""")

con.execute("""
CREATE OR REPLACE TABLE rt_users AS SELECT DISTINCT user FROM read_csv('data/raw/lanl/redteam.txt', delim=',', columns={'time':'INT','user':'VARCHAR','src_computer':'VARCHAR','dst_computer':'VARCHAR'})
""")

FEATURES = ["dst_first", "src_first", "hour_ratio", "dst_prior_events", "fail_1h", "vel_1h"]

means = con.execute(f"""
WITH t AS (
    SELECT *,
        hour_events * 1.0 / user_events AS hour_ratio,
        CASE WHEN src_user IN (SELECT user FROM rt_users) THEN
            CASE WHEN is_red THEN 'A' ELSE 'B' END
        ELSE 'C' END AS grp
    FROM feat
)
SELECT grp, count(*) AS n, {", ".join(f"round(avg({f}),4) AS {f}" for f in FEATURES)}
FROM t GROUP BY grp ORDER BY grp
""").fetchdf()
print("=== Per-group feature means ===")
print(means.to_string(index=False))
print()

sample = con.execute("""
WITH t AS (
    SELECT *,
        hour_events * 1.0 / user_events AS hour_ratio,
        CASE WHEN is_red THEN 'A' WHEN src_user IN (SELECT user FROM rt_users) THEN 'B' ELSE 'C' END AS grp
    FROM feat
)
SELECT is_red, dst_first, src_first, hour_ratio, dst_prior_events, fail_1h, vel_1h, grp
FROM t
WHERE is_red OR grp = 'B'
UNION ALL
SELECT is_red, dst_first, src_first, hour_ratio, dst_prior_events, fail_1h, vel_1h, grp
FROM (SELECT * FROM t WHERE grp = 'C' USING SAMPLE reservoir(200000 ROWS))
""").fetchdf()
print(f"sample rows: {len(sample):,}")
print(f"red events in sample: {int(sample.is_red.sum()):,}")
print()

rows = []
for f in FEATURES:
    ab = roc_auc_score(sample.is_red, sample[f])
    rows.append((f, round(ab, 4)))
auctab = pd.DataFrame(rows, columns=["feature", "AUC_A_vs_B"])
print("=== Per-feature ROC-AUC: red events vs compromised-users' normal events ===")
print(auctab.to_string(index=False))
print()

bad = sample[sample.grp.isin(["A", "C"])].copy()
bad_label = (bad.grp == "A").astype(int)
rows = []
for f in FEATURES:
    auc = roc_auc_score(bad_label, bad[f])
    rows.append((f, round(auc, 4)))
auctab2 = pd.DataFrame(rows, columns=["feature", "AUC_A_vs_C"])
print("=== Per-feature ROC-AUC: red events vs normal users' events ===")
print(auctab2.to_string(index=False))