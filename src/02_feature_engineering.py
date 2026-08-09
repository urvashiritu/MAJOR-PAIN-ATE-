#!/usr/bin/env python3
"""Feature engineering over the FULL cleaned RBA dataset (Phase 4).

One shared feature function (feature_sql) computes all features for both
offline training and live events — the same SQL template runs against the
full cleaned parquet (31.3M rows) or against (prior events + live event)
for one user.

Design (revised Aug 8 2026): features are computed over each user's TRUE
full history, THEN src/01_load_and_sample.py draws the sample FROM this
featured table. A sampled event therefore carries exactly the feature the
live system would have computed at that moment. (Previously features were
computed on the sample itself — the robot user's random 50K-row subset
made its features wrong: rapid_login_rate mean 0.118 vs true 34.0, and
failed_recently 41.9% vs a true 100%.)

Features (validated against the full dataset, Aug 8 2026):
  hour                  : 0-23 from ts (UTC — the generator's timestamps
                          are naive, so night/weekend are UTC-based)
  is_night              : hour in {22,23,0..5}
  is_weekend            : dayofweek in {0,6} (DuckDB: Sunday=0, verified)
  country_change        : country differs from the user's previous event;
                          first event ever -> 0 (explicit policy, not suspicious)
  device_change         : (device_type, os_family, browser_family) tuple differs
                          from the previous event; first event -> 0
  failed_recently       : a failed login exists in the 5 minutes before this
                          event (any event, success or failure; strictly
                          earlier; ASOF join must be '>' or it self-matches
                          failures and flags all of them)
  rapid_login_rate      : count of this user's events in the prior 60 seconds
  login_frequency_today : count of this user's events earlier on the same day
  ip_seen_before        : a strictly-earlier event exists from the same IP
  country_seen_before   : a strictly-earlier event exists from the same country
  asn_seen_before       : a strictly-earlier event exists with the same ASN
  device_seen_before    : a strictly-earlier event exists with the same
                          (device_type, os_family, browser_family) tuple
  os_seen_before        : a strictly-earlier event exists with the same os_family
  browser_seen_before   : a strictly-earlier event exists with the same
                          browser_family

Every historical feature uses only events strictly earlier than the current
event, ordered by (ts, row_id) — ts is strictly increasing per user in the
dataset (validated: 0 ties, 0 descents), so ordering is deterministic.
The seen-before features are computed as "first occurrence of the value
within the user's history" (ROW_NUMBER over the (user, value) partition),
so a value that reappears non-consecutively still counts as seen before —
unlike a pairwise LAG comparison.
No feature reads user_baselines.parquet (that would leak future
information); per-event features are history-only by construction.

Usage:
  python src/02_feature_engineering.py
  python src/02_feature_engineering.py --input data/processed/rba_clean.parquet
"""
import argparse
import json
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data" / "processed" / "rba_clean.parquet"
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "rba_features.parquet"
DEFAULT_REPORT = ROOT / "data" / "processed" / "features_report.json"


def feature_sql(src: str) -> str:
    """Shared feature function: same SQL for offline full pass and live user events.

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
            AND p.ts - p.prior_fail_ts <= INTERVAL '5 minutes' AS failed_recently,
        COUNT(*) OVER (
            PARTITION BY p.user_id ORDER BY p.ts
            RANGE BETWEEN INTERVAL '60 seconds' PRECEDING AND CURRENT ROW
            EXCLUDE CURRENT ROW) AS rapid_login_rate,
        ROW_NUMBER() OVER (
            PARTITION BY p.user_id, CAST(p.ts AS DATE)
            ORDER BY p.ts, p.row_id) - 1 AS login_frequency_today,
        ROW_NUMBER() OVER (
            PARTITION BY p.user_id, p.ip
            ORDER BY p.ts, p.row_id) > 1 AS ip_seen_before,
        ROW_NUMBER() OVER (
            PARTITION BY p.user_id, p.country
            ORDER BY p.ts, p.row_id) > 1 AS country_seen_before,
        ROW_NUMBER() OVER (
            PARTITION BY p.user_id, p.asn
            ORDER BY p.ts, p.row_id) > 1 AS asn_seen_before,
        ROW_NUMBER() OVER (
            PARTITION BY p.user_id, p.device_type, p.os_family, p.browser_family
            ORDER BY p.ts, p.row_id) > 1 AS device_seen_before,
        ROW_NUMBER() OVER (
            PARTITION BY p.user_id, p.os_family
            ORDER BY p.ts, p.row_id) > 1 AS os_seen_before,
        ROW_NUMBER() OVER (
            PARTITION BY p.user_id, p.browser_family
            ORDER BY p.ts, p.row_id) > 1 AS browser_seen_before
    FROM prior_fail p
    WINDOW w AS (PARTITION BY p.user_id ORDER BY p.ts, p.row_id)
    """


def run_gates(con: duckdb.DuckDBPyConnection, out: Path, expected_rows: int) -> list:
    failures = []
    row = con.execute(f"""
        SELECT COUNT(*) AS n,
               COUNT(*) FILTER (WHERE hour IS NULL) AS null_hour,
               COUNT(*) FILTER (WHERE country_change IS NULL) AS null_cc,
               COUNT(*) FILTER (WHERE device_change IS NULL) AS null_dc,
               COUNT(*) FILTER (WHERE rn = 1 AND country_change) AS first_cc,
               COUNT(*) FILTER (WHERE rn = 1 AND device_change) AS first_dc,
               COUNT(*) FILTER (WHERE failed_recently IS NULL) AS null_fr,
               COUNT(*) FILTER (WHERE rapid_login_rate IS NULL) AS null_rlr,
               COUNT(*) FILTER (WHERE login_frequency_today IS NULL) AS null_lft,
               COUNT(*) FILTER (WHERE ip_seen_before IS NULL) AS null_isb,
               COUNT(*) FILTER (WHERE country_seen_before IS NULL) AS null_csb,
               COUNT(*) FILTER (WHERE asn_seen_before IS NULL) AS null_ab,
               COUNT(*) FILTER (WHERE device_seen_before IS NULL) AS null_dsb,
               COUNT(*) FILTER (WHERE os_seen_before IS NULL) AS null_osb,
               COUNT(*) FILTER (WHERE browser_seen_before IS NULL) AS null_bsb,
               COUNT(*) FILTER (WHERE rn = 1 AND ip_seen_before) AS first_isb,
               COUNT(*) FILTER (WHERE rn = 1 AND country_seen_before) AS first_csb,
               COUNT(*) FILTER (WHERE rn = 1 AND asn_seen_before) AS first_ab,
               COUNT(*) FILTER (WHERE rn = 1 AND device_seen_before) AS first_dsb,
               COUNT(*) FILTER (WHERE rn = 1 AND os_seen_before) AS first_osb,
               COUNT(*) FILTER (WHERE rn = 1 AND browser_seen_before) AS first_bsb
        FROM read_parquet('{out}')
    """).fetchone()
    (n, null_hour, null_cc, null_dc, first_cc, first_dc, null_fr, null_rlr, null_lft,
     null_isb, null_csb, null_ab, null_dsb, null_osb, null_bsb,
     first_isb, first_csb, first_ab, first_dsb, first_osb, first_bsb) = row
    if n != expected_rows:
        failures.append(f"rows = {n}, expected {expected_rows}")
    if (null_hour or null_cc or null_dc or null_fr or null_rlr or null_lft
            or null_isb or null_csb or null_ab or null_dsb or null_osb or null_bsb):
        failures.append(f"NULLs: hour={null_hour} cc={null_cc} dc={null_dc} fr={null_fr} "
                        f"rlr={null_rlr} lft={null_lft} isb={null_isb} csb={null_csb} "
                        f"ab={null_ab} dsb={null_dsb} osb={null_osb} bsb={null_bsb}")
    if first_cc or first_dc or first_isb or first_csb or first_ab or first_dsb or first_osb or first_bsb:
        failures.append(f"first events flagged: country_change={first_cc} device_change={first_dc} "
                        f"ip_seen_before={first_isb} country_seen_before={first_csb} "
                        f"asn_seen_before={first_ab} device_seen_before={first_dsb} "
                        f"os_seen_before={first_osb} browser_seen_before={first_bsb}")
    return failures


def check_columns(con: duckdb.DuckDBPyConnection, out: Path) -> list:
    """Schema contract: no intermediate/artifact columns, renamed feature present."""
    cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{out}')").fetchall()}
    failures = []
    for forbidden in ("prior_fail_ts", "failed_before_success", "is_robot_sampled"):
        if forbidden in cols:
            failures.append(f"forbidden column present: {forbidden}")
    for required in ("failed_recently", "hour", "is_night", "is_weekend", "country_change",
                     "device_change", "rapid_login_rate", "login_frequency_today",
                     "ip_seen_before", "country_seen_before", "asn_seen_before",
                     "device_seen_before", "os_seen_before", "browser_seen_before"):
        if required not in cols:
            failures.append(f"required feature column missing: {required}")
    return failures


def feature_report(con: duckdb.DuckDBPyConnection, out: Path) -> dict:
    dist = con.execute(f"""
        SELECT 'country_change' AS f, COUNT(*) FILTER (WHERE country_change) AS true_n, COUNT(*) AS total,
               MIN(country_change) AS mn, MAX(country_change) AS mx FROM read_parquet('{out}')
        UNION ALL
        SELECT 'device_change', COUNT(*) FILTER (WHERE device_change), COUNT(*), MIN(device_change), MAX(device_change) FROM read_parquet('{out}')
        UNION ALL
        SELECT 'failed_recently', COUNT(*) FILTER (WHERE failed_recently), COUNT(*), MIN(failed_recently), MAX(failed_recently) FROM read_parquet('{out}')
        UNION ALL
        SELECT 'is_night', COUNT(*) FILTER (WHERE is_night), COUNT(*), MIN(is_night), MAX(is_night) FROM read_parquet('{out}')
        UNION ALL
        SELECT 'is_weekend', COUNT(*) FILTER (WHERE is_weekend), COUNT(*), MIN(is_weekend), MAX(is_weekend) FROM read_parquet('{out}')
        UNION ALL
        SELECT 'ip_seen_before', COUNT(*) FILTER (WHERE ip_seen_before), COUNT(*), MIN(ip_seen_before), MAX(ip_seen_before) FROM read_parquet('{out}')
        UNION ALL
        SELECT 'country_seen_before', COUNT(*) FILTER (WHERE country_seen_before), COUNT(*), MIN(country_seen_before), MAX(country_seen_before) FROM read_parquet('{out}')
        UNION ALL
        SELECT 'asn_seen_before', COUNT(*) FILTER (WHERE asn_seen_before), COUNT(*), MIN(asn_seen_before), MAX(asn_seen_before) FROM read_parquet('{out}')
        UNION ALL
        SELECT 'device_seen_before', COUNT(*) FILTER (WHERE device_seen_before), COUNT(*), MIN(device_seen_before), MAX(device_seen_before) FROM read_parquet('{out}')
        UNION ALL
        SELECT 'os_seen_before', COUNT(*) FILTER (WHERE os_seen_before), COUNT(*), MIN(os_seen_before), MAX(os_seen_before) FROM read_parquet('{out}')
        UNION ALL
        SELECT 'browser_seen_before', COUNT(*) FILTER (WHERE browser_seen_before), COUNT(*), MIN(browser_seen_before), MAX(browser_seen_before) FROM read_parquet('{out}')
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
    ap.add_argument("-v", "--verbose", action="count", default=0,
                    help="verbosity: -v progress bar + phase banners, -vv adds row counts, -vvv prints the feature SQL")
    args = ap.parse_args()

    def banner(msg: str) -> None:
        if args.verbose:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    con = duckdb.connect(":memory:")
    con.execute("SET threads=8")
    if args.verbose:
        con.execute("PRAGMA enable_progress_bar")

    t0 = time.time()
    banner(f"counting input rows in {args.input} ...")
    expected_rows = con.execute(f"SELECT COUNT(*) FROM read_parquet('{args.input}')").fetchone()[0]
    banner(f"input rows: {expected_rows:,} ({time.time() - t0:.1f}s)")

    sql = feature_sql(f"read_parquet('{args.input}')")
    if args.verbose >= 3:
        print("--- feature SQL ---", flush=True)
        print(sql, flush=True)
        print("------------------", flush=True)

    t1 = time.time()
    banner(f"computing features over {expected_rows:,} rows (window + ASOF passes)...")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE feat AS
        SELECT * EXCLUDE (rn, prior_fail_ts), rn FROM ({sql})
    """)
    if args.verbose >= 2:
        feat_rows = con.execute("SELECT COUNT(*) FROM feat").fetchone()[0]
        banner(f"feat table rows: {feat_rows:,}")
    banner(f"feature pass done ({time.time() - t1:.1f}s)")

    t2 = time.time()
    banner(f"writing parquet -> {args.output} ...")
    con.execute(f"COPY feat TO '{args.output}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    banner(f"copy done ({time.time() - t2:.1f}s)")
    print(f"wrote {args.output} ({expected_rows:,} rows)")

    t3 = time.time()
    banner("running gates + column checks...")
    report = feature_report(con, args.output)
    report["rows"] = expected_rows
    report["gates"] = "PASS"
    failures = run_gates(con, args.output, expected_rows)
    failures += check_columns(con, args.output)
    if failures:
        report["gates"] = failures
    banner(f"gates done ({time.time() - t3:.1f}s)")

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
