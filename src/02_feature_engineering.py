#!/usr/bin/env python3
"""Feature engineering for the RBA sample (Phase 4).

One shared feature function (feature_sql) computes all features for both
offline training and live events — the same SQL template runs against the
sample parquet or against (prior events + live event) for one user.

Features (validated against the sample, Aug 8 2026):
  hour                  : 0-23 from ts
  is_night              : hour in {22,23,0..5}
  is_weekend            : dayofweek in {0,6} (DuckDB: Sunday=0, verified)
  country_change        : country differs from the user's previous event;
                          first event ever -> 0 (explicit policy, not suspicious)
  device_change         : (device_type, os_family, browser_family) tuple differs
                          from the previous event; first event -> 0
  failed_before_success : a failed login exists in the 5 minutes before this
                          event (strictly earlier; ASOF join must be '>' or it
                          self-matches failures and flags all of them)
  rapid_login_rate      : count of this user's events in the prior 60 seconds
  login_frequency_today : count of this user's events earlier on the same day

Every historical feature uses only events strictly earlier than the current
event, ordered by (ts, row_id) — ts is strictly increasing per user in the
sample (validated: 0 ties, 0 descents), so ordering is deterministic.

Usage:
  python src/02_feature_engineering.py
  python src/02_feature_engineering.py --input data/processed/sample.parquet
"""
import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data" / "processed" / "sample.parquet"
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "features.parquet"
DEFAULT_REPORT = ROOT / "data" / "processed" / "features_report.json"


def feature_sql(src: str) -> str:
    """Shared feature function: same SQL for offline sample and live user events.

    `src` is a table expression returning columns row_id, ts, user_id,
    country, device_type, os_family, browser_family, login_success.
    """
    return f"""
    WITH ev AS (
        SELECT *, ROW_NUMBER() OVER w AS rn
        FROM {src}
        WINDOW w AS (PARTITION BY user_id ORDER BY ts, row_id)
    ),
    fails AS (
        SELECT user_id, ts FROM {src} WHERE NOT login_success
    ),
    prior_fail AS (
        SELECT e.*, f.ts AS prior_fail_ts
        FROM ev e
        ASOF LEFT JOIN fails f
        ON e.user_id = f.user_id AND e.ts > f.ts
    )
    SELECT p.*,
        EXTRACT(HOUR FROM p.ts) AS hour,
        EXTRACT(HOUR FROM p.ts) IN (22, 23, 0, 1, 2, 3, 4, 5) AS is_night,
        dayofweek(p.ts) IN (0, 6) AS is_weekend,
        CASE WHEN p.rn = 1 THEN FALSE
             ELSE p.country != LAG(p.country) OVER w END AS country_change,
        CASE WHEN p.rn = 1 THEN FALSE
             ELSE p.device_type != LAG(p.device_type) OVER w
               OR p.os_family != LAG(p.os_family) OVER w
               OR p.browser_family != LAG(p.browser_family) OVER w END AS device_change,
        p.prior_fail_ts IS NOT NULL
            AND p.ts - p.prior_fail_ts <= INTERVAL '5 minutes' AS failed_before_success,
        COUNT(*) OVER (
            PARTITION BY p.user_id ORDER BY p.ts
            RANGE BETWEEN INTERVAL '60 seconds' PRECEDING AND CURRENT ROW
            EXCLUDE CURRENT ROW) AS rapid_login_rate,
        ROW_NUMBER() OVER (
            PARTITION BY p.user_id, CAST(p.ts AS DATE)
            ORDER BY p.ts, p.row_id) - 1 AS login_frequency_today
    FROM prior_fail p
    WINDOW w AS (PARTITION BY p.user_id ORDER BY p.ts, p.row_id)
    """


def run_gates(con: duckdb.DuckDBPyConnection, out: Path) -> list:
    failures = []
    row = con.execute(f"""
        SELECT COUNT(*) AS n,
               COUNT(*) FILTER (WHERE hour IS NULL) AS null_hour,
               COUNT(*) FILTER (WHERE country_change IS NULL) AS null_cc,
               COUNT(*) FILTER (WHERE device_change IS NULL) AS null_dc,
               COUNT(*) FILTER (WHERE rn = 1 AND country_change) AS first_cc,
               COUNT(*) FILTER (WHERE rn = 1 AND device_change) AS first_dc,
               COUNT(*) FILTER (WHERE failed_before_success IS NULL) AS null_fbs,
               COUNT(*) FILTER (WHERE rapid_login_rate IS NULL) AS null_rlr,
               COUNT(*) FILTER (WHERE login_frequency_today IS NULL) AS null_lft
        FROM read_parquet('{out}')
    """).fetchone()
    n, null_hour, null_cc, null_dc, first_cc, first_dc, null_fbs, null_rlr, null_lft = row
    if n != 1_000_000:
        failures.append(f"rows = {n}, expected 1,000,000")
    if null_hour or null_cc or null_dc or null_fbs or null_rlr or null_lft:
        failures.append(f"NULLs: hour={null_hour} cc={null_cc} dc={null_dc} fbs={null_fbs} rlr={null_rlr} lft={null_lft}")
    if first_cc or first_dc:
        failures.append(f"first events flagged: country_change={first_cc} device_change={first_dc}")
    return failures


def feature_report(con: duckdb.DuckDBPyConnection, out: Path) -> dict:
    dist = con.execute(f"""
        SELECT 'country_change' AS f, COUNT(*) FILTER (WHERE country_change) AS true_n, COUNT(*) AS total,
               MIN(country_change) AS mn, MAX(country_change) AS mx FROM read_parquet('{out}')
        UNION ALL
        SELECT 'device_change', COUNT(*) FILTER (WHERE device_change), COUNT(*), MIN(device_change), MAX(device_change) FROM read_parquet('{out}')
        UNION ALL
        SELECT 'failed_before_success', COUNT(*) FILTER (WHERE failed_before_success), COUNT(*), MIN(failed_before_success), MAX(failed_before_success) FROM read_parquet('{out}')
        UNION ALL
        SELECT 'is_night', COUNT(*) FILTER (WHERE is_night), COUNT(*), MIN(is_night), MAX(is_night) FROM read_parquet('{out}')
        UNION ALL
        SELECT 'is_weekend', COUNT(*) FILTER (WHERE is_weekend), COUNT(*), MIN(is_weekend), MAX(is_weekend) FROM read_parquet('{out}')
    """).fetchall()
    num = con.execute(f"""
        SELECT 'hour', MIN(hour), MEDIAN(hour), MAX(hour) FROM read_parquet('{out}')
        UNION ALL
        SELECT 'rapid_login_rate', MIN(rapid_login_rate), MEDIAN(rapid_login_rate), MAX(rapid_login_rate) FROM read_parquet('{out}')
        UNION ALL
        SELECT 'login_frequency_today', MIN(login_frequency_today), MEDIAN(login_frequency_today), MAX(login_frequency_today) FROM read_parquet('{out}')
    """).fetchall()
    return {
        "binary_features": [dict(zip(["feature", "true_count", "total", "min", "max"], r)) for r in dist],
        "numeric_features": [dict(zip(["feature", "min", "median", "max"], r)) for r in num],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = ap.parse_args()

    con = duckdb.connect(":memory:")
    con.execute("SET threads=8")

    sql = feature_sql(f"read_parquet('{args.input}')")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE feat AS
        SELECT * EXCLUDE (rn), rn FROM ({sql})
    """)
    con.execute(f"COPY feat TO '{args.output}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    print(f"wrote {args.output}")

    report = feature_report(con, args.output)
    report["gates"] = "PASS"
    failures = run_gates(con, args.output)
    if failures:
        report["gates"] = failures

    for b in report["binary_features"]:
        print(f"{b['feature']:<24}{b['true_count']:>10,} / {b['total']:>10,}")
    for n in report["numeric_features"]:
        print(f"{n['feature']:<24}min={n['min']}  median={n['median']}  max={n['max']}")
    print(f"gates: {report['gates']}")

    args.report.write_text(json.dumps(report, indent=2, default=str))
    print(f"report -> {args.report}")

    con.close()
    if failures:
        print("GATE FAILURES:", *failures, sep="\n  - ")
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
