"""Build the per-event feature table (feat) from auth_slice in lanl.duckdb.

Recovered from git history (src/lanl_features.sql, last committed 2026-08-20,
deleted 2026-08-29 in 59bb082) with one addition: `is_ntlm` (added 2026-08-27,
commit a317e40) so the output matches the current 9-feature training set
(see src/03_retrain_both.py IF_FEATURES).

The window-function SQL is verbatim from the recovered file — it is the code
whose output was independently verified with 0 mismatches over all 29.9M rows
(reports/lanl_dataset_scan_report.md, gate G5).

Safety: the rebuild goes into a scratch table `feat_rebuild` first. If a `feat`
table already exists, the two are compared on (time, src_user, src_computer,
dst_computer) across all feature columns; `feat` is only replaced when the
mismatch count is 0 (or with --force).

Usage:
  python src/01_build_features.py              # rebuild + verify + swap + export
  python src/01_build_features.py --no-swap    # rebuild + verify only
"""
import argparse
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "raw" / "lanl"

# Comparison keys + all derived feature columns shared between the rebuild
# and the existing feat table.
COMPARE_COLS = ["dst_first", "src_first", "hour_events", "user_events",
                "dst_prior_events", "fail_1h", "vel_1h", "hour", "is_red", "is_ntlm"]

FEATURE_SQL = """
WITH base AS (
    SELECT
        a.time,
        a.src_user,
        a.dst_user,
        a.src_computer,
        a.dst_computer,
        a.auth_type,
        a.logon_type,
        a.orientation,
        a.result,
        (a.time % 86400) / 3600 AS hour,
        EXISTS (
            SELECT 1 FROM redteam_distinct r
            WHERE r.time = a.time AND r.user = a.src_user
              AND r.src_computer = a.src_computer AND r.dst_computer = a.dst_computer
        ) AS is_red
    FROM auth_slice a
)
SELECT
    b.*,
    CASE WHEN min(b.time) OVER (PARTITION BY b.src_user, b.dst_computer) = b.time THEN 1 ELSE 0 END AS dst_first,
    CASE WHEN min(b.time) OVER (PARTITION BY b.src_user, b.src_computer) = b.time THEN 1 ELSE 0 END AS src_first,
    count(*) OVER (PARTITION BY b.src_user, b.hour) AS hour_events,
    count(*) OVER (PARTITION BY b.src_user) AS user_events,
    count(*) OVER (PARTITION BY b.src_user, b.dst_computer ORDER BY b.time RANGE BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS dst_prior_events,
    coalesce(sum(CASE WHEN b.result = 'Fail' THEN 1 ELSE 0 END) OVER (PARTITION BY b.src_user ORDER BY b.time RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING), 0) AS fail_1h,
    count(*) OVER (PARTITION BY b.src_user ORDER BY b.time RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING) AS vel_1h,
    CASE WHEN b.auth_type = 'NTLM' THEN 1 ELSE 0 END AS is_ntlm
FROM base b
"""


def table_exists(con, name):
    return con.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE table_name = ?", [name]
    ).fetchone()[0] > 0


def verify(con, verbose=True):
    """Compare feat_rebuild against feat. Returns (n_rebuild, n_feat, mismatches)."""
    n_rebuild = con.execute("SELECT count(*) FROM feat_rebuild").fetchone()[0]
    n_red_rebuild = con.execute("SELECT count(*) FROM feat_rebuild WHERE is_red").fetchone()[0]
    if not table_exists(con, "feat"):
        if verbose:
            print(f"feat_rebuild: {n_rebuild:,} rows ({n_red_rebuild:,} red) — no existing feat to compare")
        return n_rebuild, None, None
    n_feat = con.execute("SELECT count(*) FROM feat").fetchone()[0]
    n_red_feat = con.execute("SELECT count(*) FROM feat WHERE is_red").fetchone()[0]
    cols = ", ".join(f"a.{c} IS DISTINCT FROM b.{c}" for c in COMPARE_COLS)
    mismatch = con.execute(f"""
        SELECT count(*) FROM feat_rebuild a
        FULL OUTER JOIN feat b
          ON a.time = b.time AND a.src_user = b.src_user
         AND a.src_computer = b.src_computer AND a.dst_computer = b.dst_computer
        WHERE a.time IS NULL OR b.time IS NULL OR {cols}
    """).fetchone()[0]
    if verbose:
        print(f"feat_rebuild : {n_rebuild:,} rows ({n_red_rebuild:,} red)")
        print(f"feat (old)   : {n_feat:,} rows ({n_red_feat:,} red)")
        print(f"mismatched/unmatched rows: {mismatch:,}")
    return n_rebuild, n_feat, mismatch


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(DATA / "lanl.duckdb"))
    ap.add_argument("--redteam", default=str(DATA / "redteam.txt"))
    ap.add_argument("--out-parquet", default=str(DATA / "feat.parquet"))
    ap.add_argument("--no-swap", action="store_true", help="build + verify only, keep old feat")
    ap.add_argument("--force", action="store_true", help="swap even if verification reports mismatches")
    args = ap.parse_args()

    con = duckdb.connect(args.db)
    con.execute(f"""
        CREATE OR REPLACE TABLE redteam AS
        SELECT * FROM read_csv('{args.redteam}', delim=',', header=false,
            columns={{'time':'BIGINT','user':'VARCHAR',
                      'src_computer':'VARCHAR','dst_computer':'VARCHAR'}})
    """)
    con.execute("CREATE OR REPLACE TABLE redteam_distinct AS SELECT DISTINCT * FROM redteam")

    t0 = time.time()
    con.execute("CREATE OR REPLACE TABLE feat_rebuild AS " + FEATURE_SQL)
    print(f"feat_rebuild built in {time.time() - t0:.0f}s", flush=True)

    n_rebuild, n_feat, mismatch = verify(con)

    if args.no_swap:
        con.close()
        return
    if mismatch is not None and mismatch > 0 and not args.force:
        con.close()
        raise SystemExit(f"verification failed ({mismatch:,} mismatches) — feat NOT replaced; "
                         f"inspect feat_rebuild or rerun with --force")
    con.execute("CREATE OR REPLACE TABLE feat AS SELECT * FROM feat_rebuild")
    con.execute("DROP TABLE feat_rebuild")
    con.execute(f"COPY feat TO '{args.out_parquet}' (FORMAT PARQUET)")
    print(f"feat replaced ({n_rebuild:,} rows) and exported to {args.out_parquet}")
    con.close()


if __name__ == "__main__":
    main()
