#!/usr/bin/env python3
"""Rule-based risk baseline (Phase 5).

Explainable pre-ML scoring over the sampled features table. Points are
initial values from PROJECT_ROADMAP.md Phase 5 and are tuned against the
validation split in Phase 6; every point lives in one place (RULE_POINTS)
so the model comparison can reuse them unchanged.

Rules (higher total = more suspicious). Weights follow the validated ATO
ordering from the RBA follow-up implementations (new country > failed login >
new device > rapid activity), NOT the raw attack-IP correlation — device
changes are actually NEGATIVELY associated with is_attack_ip (10% vs 24.6%),
so a heavy device weight hurts. The new-IP / new-ASN / new-OS / new-browser
rules use the seen-before features (Phase 4 rebuild, item B): a first-time
IP, ASN, OS or browser for this user is a takeover-style signal.
  country_change          +30  new country vs the user's previous event
  device_change           +10  new (device_type, os_family, browser_family)
  unusual hour            +15  is_night (UTC hours 22-23, 0-5)
  failed_recently         +20  failed login within the last 5 minutes
  rapid login activity    +15  >= 1 event in the prior 60 seconds
  daily frequency bonus   +10  >= 10 events earlier today (initial value)
  new_ip                  +25  this user has never logged in from this IP
  new_asn                 +15  this user has never used this ASN
  new_os                  +7   this user has never used this OS family
  new_browser             +7   this user has never used this browser family

Risk levels (evaluated for tuning in Phase 6, kept at the initial cutoffs):
  low < 30, medium 30-64, high 65-89, critical >= 90.
The gold-tuned optimum (score 77, FPR 4.7%) was rejected: it triples the
FPR versus critical >= 90 (1.8%) for +0.15% gold recall — the critical band
stays the ATO-catching tail and medium/high remain monitoring bands.

Writes reports/rule_baseline_scores.parquet (row_id, user_id, ts, score
components, rule_score, risk_level, reasons, labels) and
reports/rule_baseline_report.json.

Usage:
  python src/04_rule_baseline.py
  python src/04_rule_baseline.py --input data/processed/features.parquet
"""
import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data" / "processed" / "features.parquet"
DEFAULT_OUTPUT = ROOT / "reports" / "rule_baseline_scores.parquet"
DEFAULT_REPORT = ROOT / "reports" / "rule_baseline_report.json"

RULE_POINTS = {
    "country": 30,
    "device": 10,
    "hour": 15,
    "failed": 20,
    "rapid": 15,
    "freq": 10,
    "new_ip": 25,
    "new_asn": 15,
    "new_os": 7,
    "new_browser": 7,
}
LEVEL_BOUNDS = {"low": 0, "medium": 30, "high": 65, "critical": 90}
FREQ_BONUS_AT = 10


def score_sql(src: str) -> str:
    """Rule scoring over a table with the behavioral + seen-before features.

    One component column per rule + a summed rule_score, risk level, and
    comma-joined human-readable reasons. Labels ride along for Phase 6.
    """
    score_exprs = " + ".join(
        f"s.score_{k}" for k in ("country", "device", "hour", "failed",
                                 "rapid", "freq", "new_ip", "new_asn",
                                 "new_os", "new_browser"))
    return f"""
    WITH scored AS (
        SELECT row_id, user_id, ts, is_attack_ip, is_ato, login_success,
            country_change, device_change, is_night, failed_recently,
            rapid_login_rate, login_frequency_today,
            ip_seen_before, asn_seen_before, os_seen_before, browser_seen_before,
            CASE WHEN country_change THEN {RULE_POINTS['country']} ELSE 0 END AS score_country,
            CASE WHEN device_change THEN {RULE_POINTS['device']} ELSE 0 END AS score_device,
            CASE WHEN is_night THEN {RULE_POINTS['hour']} ELSE 0 END AS score_hour,
            CASE WHEN failed_recently THEN {RULE_POINTS['failed']} ELSE 0 END AS score_failed,
            CASE WHEN rapid_login_rate >= 1 THEN {RULE_POINTS['rapid']} ELSE 0 END AS score_rapid,
            CASE WHEN login_frequency_today >= {FREQ_BONUS_AT} THEN {RULE_POINTS['freq']} ELSE 0 END AS score_freq,
            CASE WHEN NOT ip_seen_before THEN {RULE_POINTS['new_ip']} ELSE 0 END AS score_new_ip,
            CASE WHEN NOT asn_seen_before THEN {RULE_POINTS['new_asn']} ELSE 0 END AS score_new_asn,
            CASE WHEN NOT os_seen_before THEN {RULE_POINTS['new_os']} ELSE 0 END AS score_new_os,
            CASE WHEN NOT browser_seen_before THEN {RULE_POINTS['new_browser']} ELSE 0 END AS score_new_browser,
            CASE WHEN country_change THEN 'new country' END AS r_country,
            CASE WHEN device_change THEN 'new device' END AS r_device,
            CASE WHEN is_night THEN 'unusual hour' END AS r_hour,
            CASE WHEN failed_recently THEN 'recent failed login' END AS r_failed,
            CASE WHEN rapid_login_rate >= 1 THEN 'rapid login activity' END AS r_rapid,
            CASE WHEN login_frequency_today >= {FREQ_BONUS_AT} THEN 'high daily frequency' END AS r_freq,
            CASE WHEN NOT ip_seen_before THEN 'new ip' END AS r_new_ip,
            CASE WHEN NOT asn_seen_before THEN 'new asn' END AS r_new_asn,
            CASE WHEN NOT os_seen_before THEN 'new os' END AS r_new_os,
            CASE WHEN NOT browser_seen_before THEN 'new browser' END AS r_new_browser
        FROM {src}
    )
    SELECT s.*,
        {score_exprs} AS rule_score,
        CASE WHEN {score_exprs} >= {LEVEL_BOUNDS['critical']} THEN 'critical'
             WHEN {score_exprs} >= {LEVEL_BOUNDS['high']} THEN 'high'
             WHEN {score_exprs} >= {LEVEL_BOUNDS['medium']} THEN 'medium'
             ELSE 'low' END AS risk_level,
        concat_ws(', ', s.r_country, s.r_device, s.r_hour, s.r_failed,
                  s.r_rapid, s.r_freq, s.r_new_ip, s.r_new_asn, s.r_new_os,
                  s.r_new_browser) AS reasons
    FROM scored s
    """


def run_gates(con: duckdb.DuckDBPyConnection, out: Path, expected_rows: int) -> list:
    failures = []
    row = con.execute(f"""
        SELECT COUNT(*) AS n,
               COUNT(*) FILTER (WHERE country_change AND score_country = 0) AS cc_zero,
               COUNT(*) FILTER (WHERE NOT country_change AND score_country != 0) AS cc_bad,
               COUNT(*) FILTER (WHERE device_change AND score_device = 0) AS dc_zero,
               COUNT(*) FILTER (WHERE NOT device_change AND score_device != 0) AS dc_bad,
               COUNT(*) FILTER (WHERE is_night AND score_hour = 0) AS hr_zero,
               COUNT(*) FILTER (WHERE NOT is_night AND score_hour != 0) AS hr_bad,
               COUNT(*) FILTER (WHERE failed_recently AND score_failed = 0) AS fa_zero,
               COUNT(*) FILTER (WHERE NOT failed_recently AND score_failed != 0) AS fa_bad,
               COUNT(*) FILTER (WHERE rapid_login_rate >= 1 AND score_rapid = 0) AS rp_zero,
               COUNT(*) FILTER (WHERE rapid_login_rate = 0 AND score_rapid != 0) AS rp_bad,
               COUNT(*) FILTER (WHERE login_frequency_today >= {FREQ_BONUS_AT} AND score_freq = 0) AS fq_zero,
               COUNT(*) FILTER (WHERE login_frequency_today < {FREQ_BONUS_AT} AND score_freq != 0) AS fq_bad,
               COUNT(*) FILTER (WHERE NOT ip_seen_before AND score_new_ip = 0) AS nip_zero,
               COUNT(*) FILTER (WHERE ip_seen_before AND score_new_ip != 0) AS nip_bad,
               COUNT(*) FILTER (WHERE NOT asn_seen_before AND score_new_asn = 0) AS nasn_zero,
               COUNT(*) FILTER (WHERE asn_seen_before AND score_new_asn != 0) AS nasn_bad,
               COUNT(*) FILTER (WHERE NOT os_seen_before AND score_new_os = 0) AS nos_zero,
               COUNT(*) FILTER (WHERE os_seen_before AND score_new_os != 0) AS nos_bad,
               COUNT(*) FILTER (WHERE NOT browser_seen_before AND score_new_browser = 0) AS nb_zero,
               COUNT(*) FILTER (WHERE browser_seen_before AND score_new_browser != 0) AS nb_bad,
               COUNT(*) FILTER (WHERE rule_score = 0 AND risk_level != 'low') AS clean_not_low,
               COUNT(*) FILTER (WHERE rule_score = 0 AND reasons != '') AS clean_reasons,
               COUNT(*) FILTER (WHERE rule_score > 0 AND reasons = '') AS scored_no_reasons
        FROM read_parquet('{out}')
    """).fetchone()
    n = row[0]
    if n != expected_rows:
        failures.append(f"rows = {n}, expected {expected_rows}")
    for label, v in zip(("cc", "dc", "hr", "fa", "rp", "fq", "nip", "nasn", "nos", "nb"),
                        row[1:21]):
        if v:
            failures.append(f"component gate {label}: {v} rows inconsistent")
    if row[21]:
        failures.append(f"clean rows (score 0) not low: {row[21]}")
    if row[22] or row[23]:
        failures.append(f"reasons mismatch: clean_with_reasons={row[22]} scored_without_reasons={row[23]}")

    level_gate = con.execute(f"""
        SELECT COUNT(*) FILTER (WHERE risk_level = 'low' AND rule_score >= {LEVEL_BOUNDS['medium']}),
               COUNT(*) FILTER (WHERE risk_level = 'medium' AND rule_score < {LEVEL_BOUNDS['medium']}),
               COUNT(*) FILTER (WHERE risk_level = 'medium' AND rule_score >= {LEVEL_BOUNDS['high']}),
               COUNT(*) FILTER (WHERE risk_level = 'high' AND rule_score < {LEVEL_BOUNDS['high']}),
               COUNT(*) FILTER (WHERE risk_level = 'high' AND rule_score >= {LEVEL_BOUNDS['critical']}),
               COUNT(*) FILTER (WHERE risk_level = 'critical' AND rule_score < {LEVEL_BOUNDS['critical']})
        FROM read_parquet('{out}')
    """).fetchone()
    if any(level_gate):
        failures.append(f"risk level boundaries violated: low_lo={level_gate[0]} med_lo={level_gate[1]} "
                        f"med_hi={level_gate[2]} high_lo={level_gate[3]} high_hi={level_gate[4]} crit_lo={level_gate[5]}")
    null_gate = con.execute(f"""
        SELECT COUNT(*) FROM read_parquet('{out}')
        WHERE country_change IS NULL OR device_change IS NULL OR is_night IS NULL
           OR failed_recently IS NULL OR rapid_login_rate IS NULL
           OR login_frequency_today IS NULL OR ip_seen_before IS NULL
           OR asn_seen_before IS NULL OR os_seen_before IS NULL
           OR browser_seen_before IS NULL
           OR rule_score IS NULL OR risk_level IS NULL OR reasons IS NULL
    """).fetchone()[0]
    if null_gate:
        failures.append(f"{null_gate} rows with NULL flags/score/level/reasons")
    return failures


def rule_report(con: duckdb.DuckDBPyConnection, out: Path) -> dict:
    levels = con.execute(f"""
        SELECT risk_level, COUNT(*), ROUND(AVG(rule_score), 2), MIN(rule_score), MAX(rule_score)
        FROM read_parquet('{out}') GROUP BY risk_level ORDER BY MIN(rule_score)
    """).fetchall()
    normal = con.execute(f"""
        SELECT COUNT(*), ROUND(AVG(rule_score), 2), MAX(rule_score)
        FROM read_parquet('{out}')
        WHERE NOT country_change AND NOT device_change AND NOT is_night
          AND NOT failed_recently AND rapid_login_rate = 0
          AND login_frequency_today < {FREQ_BONUS_AT}
          AND ip_seen_before AND asn_seen_before
          AND os_seen_before AND browser_seen_before
    """).fetchone()
    return {
        "levels": [dict(zip(["level", "rows", "avg_score", "min_score", "max_score"], r)) for r in levels],
        "normal_events": {"rows": normal[0], "avg_score": normal[1], "max_score": normal[2]},
        "rule_points": RULE_POINTS,
        "level_bounds": LEVEL_BOUNDS,
        "freq_bonus_at": FREQ_BONUS_AT,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = ap.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(":memory:")
    con.execute("SET threads=8")

    expected_rows = con.execute(f"SELECT COUNT(*) FROM read_parquet('{args.input}')").fetchone()[0]
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE scored AS
        SELECT * FROM ({score_sql(f"read_parquet('{args.input}')")})
    """)
    con.execute(f"COPY scored TO '{args.output}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    print(f"wrote {args.output} ({expected_rows:,} rows)")

    report = rule_report(con, args.output)
    report["rows"] = expected_rows
    report["gates"] = "PASS"
    failures = run_gates(con, args.output, expected_rows)
    if failures:
        report["gates"] = failures

    for l in report["levels"]:
        print(f"{l['level']:<10}{l['rows']:>10,}  avg={l['avg_score']:>6}  [{l['min_score']}..{l['max_score']}]")
    print(f"normal events: {report['normal_events']['rows']:,} rows, max score {report['normal_events']['max_score']}")
    print(f"gates: {report['gates']}")

    args.report.write_text(json.dumps(report, indent=2, default=str))
    print(f"report -> {args.report}")

    con.close()
    if failures:
        print("GATE FAILURES:", *failures, sep="\n  - ")
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
