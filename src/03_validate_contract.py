#!/usr/bin/env python3
"""Pipeline contract validation (regression protection).

Runs schema and cross-column invariant checks against every pipeline
artifact. This is the check layer that was missing when four bugs slipped
through (Aug 8 2026) — the per-script gates validated *values* only:

  1. geo_unreliable was a byte-identical duplicate of is_private_ip
     -> schema check cannot see it; needs a VALUE invariant  (check 2)
  2. prior_fail_ts leaked into features.parquet              -> check 4
  3. failed_before_success was misnamed (never renamed)      -> check 4
  4. fixed_rows hardcoded in sampling                        -> check 7

Every check FAILS on the pre-fix artifacts and PASSES on the fixed ones,
so a stale artifact (or a regression) shows up as a nonzero exit.

Usage:
  python src/03_validate_contract.py
  python src/03_validate_contract.py --sample 1000000  # any artifact set
"""
import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CLEAN = ROOT / "data" / "processed" / "rba_clean.parquet"
DEFAULT_FEATURES_FULL = ROOT / "data" / "processed" / "rba_features.parquet"
DEFAULT_SAMPLE = ROOT / "data" / "processed" / "sample.parquet"
DEFAULT_FEATURES = ROOT / "data" / "processed" / "features.parquet"
DEFAULT_BASELINES = ROOT / "data" / "processed" / "user_baselines.parquet"
DEFAULT_REPORT = ROOT / "data" / "processed" / "sampling_report.json"

ROBOT_USER_ID = -4324475583306591935
USER_CAP = 10_000

CLEAN_COLS = [
    "row_id", "ts", "user_id", "rtt", "ip", "country", "region", "city", "asn",
    "user_agent", "browser_raw", "os_raw", "device_raw", "login_success",
    "is_attack_ip", "is_ato", "os_family", "browser_family", "device_type",
    "is_private_ip", "geo_unreliable", "rtt_missing", "rtt_outlier",
    "ua_os_conflict", "version_stripped", "is_generator_bot", "is_vlc",
]
FEATURE_COLS = [
    "hour", "is_night", "is_weekend", "country_change", "device_change",
    "failed_recently", "rapid_login_rate", "login_frequency_today",
    "ip_seen_before", "country_seen_before", "asn_seen_before",
    "device_seen_before", "os_seen_before", "browser_seen_before",
]
ARTIFACT_COLS = ["rn", "is_robot_sampled"]
FORBIDDEN_COLS = ["prior_fail_ts", "failed_before_success"]


def failures_run(con: duckdb.DuckDBPyConnection, paths: dict, report: dict) -> list:
    failures = []
    report["rows"] = {}

    def schema_contract(path: Path, expected: list, label: str) -> None:
        cols = [(r[0], r[1]) for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()]
        got = [c for c, _ in cols]
        if got != expected:
            missing = [c for c in expected if c not in got]
            extra = [c for c in got if c not in expected]
            failures.append(f"{label} schema mismatch: missing={missing} extra={extra}")

    def count(path: Path, where: str) -> int:
        return con.execute(f"SELECT COUNT(*) FROM read_parquet('{path}') WHERE {where}").fetchone()[0]

    # 1. exact column contracts (name + order)
    schema_contract(paths["clean"], CLEAN_COLS, "rba_clean")
    schema_contract(paths["features_full"], CLEAN_COLS + FEATURE_COLS + ["rn"], "rba_features")
    schema_contract(paths["sample"], CLEAN_COLS + FEATURE_COLS + ["rn", "is_robot_sampled"], "sample")
    schema_contract(paths["features"], CLEAN_COLS + FEATURE_COLS, "features")

    # 2. geo semantics: geo_unreliable is NOT a duplicate of is_private_ip
    n = count(paths["clean"],
              "geo_unreliable != (is_private_ip OR region IS NULL OR city IS NULL)")
    if n:
        failures.append(f"geo_unreliable semantics violated on {n:,} rows (was a duplicate of is_private_ip)")
    report["geo_semantics_violations"] = n

    # 3. flag invariants on clean
    for name, where in (
        ("geo_private_contradiction", "geo_unreliable AND NOT is_private_ip AND region IS NOT NULL AND city IS NOT NULL"),
        ("rtt_both_flags", "rtt_missing AND rtt_outlier"),
        ("ios_spoof_label", "os_family='iOS' AND ((regexp_matches(user_agent, '(?i)AwarioSmartBot') AND NOT regexp_matches(user_agent, '(?i)(^|[^A-Za-z0-9])(iPhone|iPad|iPod|iOS)($|[^A-Za-z0-9])|CriOS|EdgiOS|FxiOS')) "
                             "OR (regexp_matches(user_agent, '(?i)CriOS') AND regexp_matches(os_raw, '(?i)Android')))"),
        # 3.12 bug signature only: desktop rows reclassified mobile by a bare
        #    'Mobile' token on a desktop-OS UA. A desktop platform marker +
        #    mobile classification is only legitimate when the UA carries a
        #    genuine mobile token (Android/iPhone/WP — e.g. YaApp_Android
        #    webviews send 'X11; Linux armv7l ... Mobile Safari'); those rows
        #    have a lying device_raw='desktop' column and are CORRECT.
        ("desktop_reclass_mobile", "device_raw='desktop' AND device_type='mobile' "
         "AND regexp_matches(user_agent, '(?i)Mobile') "
         "AND regexp_matches(user_agent, '(?i)Mac OS X|Macintosh|Windows NT|X11;|CrOS') "
         "AND NOT regexp_matches(user_agent, '(?i)(Android|Andorid)([^@]|$)|iPhone|iPod|Windows Phone')"),
        ("null_device_desktop", "device_raw IS NULL AND device_type='desktop'"),
    ):
        n = count(paths["clean"], where)
        if n:
            failures.append(f"{name}: {n:,} rows")
        report[name] = n

    # 4. features output contract
    for col in FORBIDDEN_COLS:
        cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{paths['features']}')").fetchall()}
        if col in cols:
            failures.append(f"forbidden column in features.parquet: {col}")
    for col in FEATURE_COLS:
        if col not in {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{paths['features']}')").fetchall()}:
            failures.append(f"required feature column missing in features.parquet: {col}")

    # 5. event-set integrity: features == sample rows (same events, no artifacts)
    row_id_equal = con.execute(f"""
        SELECT (SELECT COUNT(*) FROM read_parquet('{paths['sample']}'))
             - (SELECT COUNT(*) FROM read_parquet('{paths['features']}')) AS diff,
               (SELECT COUNT(*) FROM (
                   SELECT row_id FROM read_parquet('{paths['sample']}')
                   EXCEPT
                   SELECT row_id FROM read_parquet('{paths['features']}'))
               ) AS missing_rows
    """).fetchone()
    if row_id_equal[0]:
        failures.append(f"features.parquet row count differs from sample by {row_id_equal[0]}")
    if row_id_equal[1]:
        failures.append(f"{row_id_equal[1]} sample row_ids missing from features.parquet")
    report["sample_minus_features_rows"] = row_id_equal[0]

    # 6. baseline coverage + sampling report cross-checks
    missing_baseline = con.execute(f"""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT user_id FROM read_parquet('{paths['sample']}')
            EXCEPT
            SELECT user_id FROM read_parquet('{paths['baselines']}'))
    """).fetchone()[0]
    if missing_baseline:
        failures.append(f"{missing_baseline} sampled users missing from user_baselines")
    report["sample_users_missing_baseline"] = missing_baseline

    # 7. fixed-rows cross-check: recomputed tiers == report composition
    try:
        rep = json.loads(Path(paths["report"]).read_text())
    except (OSError, json.JSONDecodeError) as e:
        failures.append(f"cannot read sampling_report.json: {e}")
        return failures
    tier_rows = {t: r for t, r, _ in rep.get("tier_rows", [])}
    report["report_tier_rows"] = tier_rows
    computed_fixed = con.execute(f"""
        WITH src AS (SELECT * FROM read_parquet('{paths['clean']}')),
        user_stats AS (
            SELECT user_id,
                   COUNT(*) AS n_rows,
                   COUNT(*) FILTER (WHERE is_attack_ip) AS attack_rows,
                   COUNT(*) FILTER (WHERE is_ato) AS ato_rows
            FROM src GROUP BY user_id),
        tiers AS (
            SELECT user_id, n_rows,
                   CASE WHEN ato_rows > 0 THEN 'ato'
                        WHEN user_id = {ROBOT_USER_ID} THEN 'robot'
                        WHEN attack_rows >= 10 THEN 'heavy'
                        WHEN attack_rows BETWEEN 1 AND 9 THEN 'light'
                        ELSE 'normal' END AS tier
            FROM user_stats)
        SELECT COALESCE(SUM(LEAST(n_rows, {USER_CAP})), 0)
        FROM tiers WHERE tier IN ('ato', 'heavy')
    """).fetchone()[0]
    report_computed = rep.get("fixed_rows") or (tier_rows.get("ato", 0) + tier_rows.get("heavy", 0))
    if computed_fixed != report_computed:
        failures.append(f"fixed-rows drift: recomputed {computed_fixed:,} vs report {report_computed:,}")

    # 8. feature sanity on the sampled features table (no NULLs, first-event policy)
    sample_cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{paths['sample']}')").fetchall()}
    if set(FEATURE_COLS + ["rn"]) <= sample_cols:
        row = con.execute(f"""
            SELECT COUNT(*) FILTER (WHERE failed_recently IS NULL) AS null_fr,
                   COUNT(*) FILTER (WHERE country_change IS NULL) AS null_cc,
                   COUNT(*) FILTER (WHERE device_change IS NULL) AS null_dc,
                   COUNT(*) FILTER (WHERE rapid_login_rate IS NULL) AS null_rlr,
                   COUNT(*) FILTER (WHERE rn = 1 AND country_change) AS first_cc,
                   COUNT(*) FILTER (WHERE rn = 1 AND device_change) AS first_dc
            FROM read_parquet('{paths['sample']}')
        """).fetchone()
        for name, v in zip(("null_fr", "null_cc", "null_dc", "null_rlr", "first_cc", "first_dc"), row):
            if v:
                failures.append(f"features sanity: {name} = {v}")
            report[name] = v
    else:
        failures.append("features sanity skipped: sample schema missing required feature columns")

    report["rows"] = {
        "clean": con.execute(f"SELECT COUNT(*) FROM read_parquet('{paths['clean']}')").fetchone()[0],
        "rba_features": con.execute(f"SELECT COUNT(*) FROM read_parquet('{paths['features_full']}')").fetchone()[0],
        "sample": con.execute(f"SELECT COUNT(*) FROM read_parquet('{paths['sample']}')").fetchone()[0],
        "features": con.execute(f"SELECT COUNT(*) FROM read_parquet('{paths['features']}')").fetchone()[0],
    }
    return failures


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clean", type=Path, default=DEFAULT_CLEAN)
    ap.add_argument("--features-full", type=Path, default=DEFAULT_FEATURES_FULL)
    ap.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    ap.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    ap.add_argument("--baselines", type=Path, default=DEFAULT_BASELINES)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = ap.parse_args()

    con = duckdb.connect(":memory:")
    con.execute("SET threads=8")

    report = {"contract": "PASS"}
    failures = failures_run(con, vars(args), report)
    if failures:
        report["contract"] = failures

    for key, value in report.items():
        if key in ("rows", "report_tier_rows"):
            print(f"{key}: {value}")
        elif key == "contract":
            print(f"contract: {'PASS' if value == 'PASS' else 'FAIL'}")
        else:
            print(f"  {key:<38}{value:>12,}")

    if failures:
        print("CONTRACT FAILURES:", *failures, sep="\n  - ")
        con.close()
        sys.exit(1)
    con.close()
    print("all contract checks PASS")


if __name__ == "__main__":
    sys.exit(main())
