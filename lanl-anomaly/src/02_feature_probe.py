"""LANL feasibility probe: do red-team auth events separate from normal behavior?

Recovered from git history (src/lanl_probe.py, last committed 2026-08-20,
deleted 2026-08-29 in 59bb082); feature list extended to the current 9.
Run AFTER src/01_build_features.py. This decides whether training is justified
at all — it computed the Aug 19 green-light numbers (unusual hour 0.711,
first-visit destination 0.650, destination familiarity inverse 0.970, ...).

Reads feat.parquet, compares three event groups:
  A = red-team matched events (label 1)
  B = non-red events of the 104 compromised users (their own normal baseline)
  C = events of normal users

Reports per-feature means and ROC-AUC (A vs B and A vs C).
"""
import argparse
from pathlib import Path

import duckdb
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "raw" / "lanl"

FEATURES = ["dst_first", "src_first", "hour_ratio", "dst_prior_events",
            "fail_1h", "vel_1h", "hour_sin", "hour_cos", "is_ntlm"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--feat", default=str(DATA / "feat.parquet"))
    ap.add_argument("--redteam", default=str(DATA / "redteam.txt"))
    args = ap.parse_args()

    con = duckdb.connect()

    con.execute(f"""
    CREATE OR REPLACE TABLE feat AS SELECT * FROM '{args.feat}'
    """)

    con.execute(f"""
    CREATE OR REPLACE TABLE rt_users AS
    SELECT DISTINCT user FROM read_csv('{args.redteam}', delim=',', header=false,
        columns={{'time':'BIGINT','user':'VARCHAR',
                  'src_computer':'VARCHAR','dst_computer':'VARCHAR'}})
    """)

    means = con.execute(f"""
    WITH t AS (
        SELECT *,
            hour_events * 1.0 / user_events AS hour_ratio,
            sin(hour / 24.0 * 2 * pi()) AS hour_sin,
            cos(hour / 24.0 * 2 * pi()) AS hour_cos,
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

    sample = con.execute(f"""
    WITH t AS (
        SELECT *,
            hour_events * 1.0 / user_events AS hour_ratio,
            sin(hour / 24.0 * 2 * pi()) AS hour_sin,
            cos(hour / 24.0 * 2 * pi()) AS hour_cos,
            CASE WHEN is_red THEN 'A' WHEN src_user IN (SELECT user FROM rt_users) THEN 'B' ELSE 'C' END AS grp
        FROM feat
    )
    SELECT is_red, {", ".join(FEATURES)}, grp
    FROM t
    WHERE is_red OR grp = 'B'
    UNION ALL
    SELECT is_red, {", ".join(FEATURES)}, grp
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


if __name__ == "__main__":
    main()
