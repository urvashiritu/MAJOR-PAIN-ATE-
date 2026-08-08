#!/usr/bin/env python3
"""Clean the RBA dataset.

Fixes documented in dataset_scan_report.md (full-scan findings, Aug 2 2026):
  3.1 browser<->OS contradictions   -> os_family re-derived from User Agent
  3.2 mobile device, desktop marker -> device_type re-derived from User Agent
   3.3 private IPs geo/label noise   -> is_private_ip flag + geo_unreliable flag
        (geo_unreliable = private IP OR region/city NULL; a real, distinct
        signal — it is NOT a duplicate of is_private_ip)
   3.4 RTT 96% missing / outliers    -> rtt_missing + rtt_outlier flags
   3.5 '-' vs NULL geo placeholders  -> unified to NULL
   3.6 unknown/bot device            -> kept, preserved in device_raw
   3.7 ATO label quirks              -> kept, documented
   3.12 iOS-token substring false positives (AwarioSmartBot 'ioS',
        CriOS-on-Android spoofs)     -> token-boundary iOS detection
   3.13 'Mobile' substring in desktop UAs ('Mobile Safari' suffix)
        -> token-boundary Mobile detection
   3.14 device_raw 'unknown'/NULL short-circuit before UA checks
        -> UA checks now run first; NULL device_raw -> 'unknown' (was 'desktop')
   3.15 'Andorid' typo in MQQBrowser UAs -> mapped to Android

Principles:
  - Raw values are always preserved (raw_* columns) for auditability.
  - No rows are deleted; row count must not change.
  - Runs fully inside DuckDB (the 8.5 GB CSV is streamed, never loaded whole).

Usage:
  python src/00_clean_dataset.py                      # full clean -> data/processed/rba_clean.parquet
  python src/00_clean_dataset.py --sample 100000      # small dev run
  python src/00_clean_dataset.py --verify             # compare checks raw vs cleaned
  python src/00_clean_dataset.py --output out.parquet
"""
import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data" / "raw" / "rba-dataset.csv"
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "rba_clean.parquet"
DEFAULT_SUMMARY = ROOT / "data" / "processed" / "cleaning_summary.json"

TRANSFORM = """
WITH raw AS (
    SELECT
        column00 AS idx,
        column01 AS ts_str,
        column02 AS user_id_str,
        column03 AS rtt_str,
        column04 AS ip,
        column05 AS country,
        column06 AS region,
        column07 AS city,
        column08 AS asn_str,
        column09 AS ua,
        column10 AS browser_raw,
        column11 AS os_raw,
        column12 AS device_raw,
        column13 AS success_str,
        column14 AS attack_str,
        column15 AS ato_str
    FROM {source}
)
SELECT
    try_cast(idx AS BIGINT)                                        AS row_id,
    COALESCE(try_strptime(ts_str, '%Y-%m-%d %H:%M:%S.%f'),
             try_strptime(ts_str, '%Y-%m-%d %H:%M:%S'))            AS ts,
    try_cast(user_id_str AS BIGINT)                                AS user_id,
    CASE WHEN rtt_str = '' THEN NULL
         WHEN try_cast(rtt_str AS DOUBLE) > 60000 THEN NULL
         ELSE try_cast(rtt_str AS DOUBLE) END                      AS rtt,
    ip,
    country,
    NULLIF(NULLIF(region, ''), '-')                                AS region,
    NULLIF(NULLIF(city, ''), '-')                                  AS city,
    try_cast(asn_str AS BIGINT)                                    AS asn,
    ua                                                                   AS user_agent,
    browser_raw,
    os_raw,
    device_raw,
    success_str = 'True'                                           AS login_success,
    attack_str = 'True'                                            AS is_attack_ip,
    ato_str = 'True'                                               AS is_ato,
    -- 3.1 + 3.2: derive truth from the User Agent string
    -- (Windows Phone UAs contain an 'Android' token AND a 'like iPhone OS' spoof
    --  token -> check Windows Phone BEFORE iOS/Android so both are ignored)
    CASE
        -- KaiOS devices report a spoofed Chrome/CriOS UA template (with an
        -- ';Android;' and 'CriOS/..' token) but the OS column genuinely says
        -- KaiOS -> os_raw is authoritative, checked BEFORE the UA branches
        WHEN regexp_matches(os_raw, '(?i)KaiOS') OR regexp_matches(ua, '(?i)KaiOS') THEN 'KaiOS'
        WHEN regexp_matches(ua, '(?i)Windows Phone') THEN 'Windows Phone'
        -- token-boundary iOS: bare substring matches poison the class
        -- (AwarioSmartBot/1.0 contains 'ioS'); CriOS/EdgiOS/FxiOS are real
        -- iOS-WebKit tokens but the generator injects them into Android and
        -- Windows Phone UA templates, so the branch yields when the UA or
        -- os_raw carries an Android/WP platform token (see scan 5 findings)
        WHEN regexp_matches(ua, '(?i)CriOS|EdgiOS|FxiOS|(^|[^A-Za-z0-9])(iPhone|iPad|iPod|iOS)($|[^A-Za-z0-9])')
             AND NOT regexp_matches(ua, '(?i)(Android|Andorid)([^@]|$)|Windows Phone')
             AND NOT regexp_matches(os_raw, '(?i)(Android|Andorid)|Windows Phone') THEN 'iOS'
        WHEN regexp_matches(ua, '(?i)(Android|Andorid)([^@]|$)') THEN 'Android'
        WHEN regexp_matches(ua, '(?i)Windows') THEN 'Windows'
        WHEN regexp_matches(ua, '(?i)X11; CrOS') THEN 'ChromeOS'
        WHEN regexp_matches(ua, '(?i)Mac OS X|Macintosh|Mac_PowerPC') THEN 'macOS'
        WHEN regexp_matches(ua, '(?i)Linux|X11') THEN 'Linux'
        -- UA silent on platform -> fall back to the OS column's keyword
        -- (KaiOS contains the substring 'iOS' -> must be checked BEFORE iOS)
        -- generator-bot UAs are excluded: AwarioSmartBot etc. carry a
        -- fabricated os_raw ('iOS 2.x' etc.) with no platform token in the UA
        -- (scan 5: 1,993 rows were mislabeled iOS via this branch)
        WHEN regexp_matches(os_raw, '(?i)KaiOS') THEN 'KaiOS'
        WHEN regexp_matches(os_raw, '(?i)CriOS|EdgiOS|FxiOS|(^|[^A-Za-z0-9])(iPhone|iPad|iPod|iOS)($|[^A-Za-z0-9])')
             AND NOT regexp_matches(ua, '(?i)ZipppBot|startmebot|ZoomBot|MetaJobBot|das-group|AwarioSmartBot') THEN 'iOS'
        WHEN regexp_matches(os_raw, '(?i)Windows Phone') THEN 'Windows Phone'
        WHEN regexp_matches(os_raw, '(?i)(Android|Andorid)([^@]|$)') THEN 'Android'
        WHEN regexp_matches(os_raw, '(?i)Windows') THEN 'Windows'
        WHEN regexp_matches(os_raw, '(?i)Mac OS X|macOS|Macintosh') THEN 'macOS'
        WHEN regexp_matches(os_raw, '(?i)Chrome ?OS') THEN 'ChromeOS'
        WHEN regexp_matches(os_raw, '(?i)Linux|Unix') THEN 'Linux'
        -- legacy OS families the generator stores in os_raw (UA-silent rows)
        -- (scan 4 coverage audit, Aug 8: these were falling to 'unknown')
        WHEN regexp_matches(os_raw, '(?i)BlackBerry') THEN 'BlackBerry'
        WHEN regexp_matches(os_raw, '(?i)MeeGo') THEN 'MeeGo'
        WHEN regexp_matches(os_raw, '(?i)Symbian') THEN 'Symbian'
        WHEN regexp_matches(os_raw, '(?i)Roku') THEN 'Roku'
        WHEN regexp_matches(os_raw, '(?i)WebTV') THEN 'WebTV'
        WHEN regexp_matches(os_raw, '(?i)Firefox OS') THEN 'Firefox OS'
        ELSE 'unknown'
    END                                                              AS os_family,
    array_to_string(
        list_filter(string_split(browser_raw, ' '),
            x -> x != ''
             AND NOT regexp_matches(x, '(?i)^[0-9]+([._-][0-9]+)*(-git)?$')
             AND NOT regexp_matches(x, '(?i)^variation/[0-9]+$')),
        ' ')                                                             AS browser_family,
    CASE
        WHEN device_raw = 'bot' THEN 'bot'
        WHEN regexp_matches(ua, '(?i)iPad')                THEN 'tablet'
        -- explicit tablet markers checked BEFORE Mobile (tablet UAs carry "Mobile")
        WHEN regexp_matches(ua, '(?i)Tablet|SM-T|Tab S|Tab A|Galaxy Tab|Nexus (7|9|10)|Xoom|KFAPWI|Lenovo TAB') THEN 'tablet'
        -- token-boundary Mobile: the generator appends 'Mobile Safari/537.36'
        -- to DESKTOP UAs too, so 'Mobile' counts only when the UA carries no
        -- desktop-OS token (Mac/Windows/X11/CrOS)
        -- (scan 5: the previous OR-group quoted this AND-clause inside the regex
        --  string, making it dead text — Mobile never classified anything)
        WHEN regexp_matches(ua, '(?i)iPhone|iPod|Windows Phone|(Android|Andorid)([^@]|$)')
             OR (regexp_matches(ua, '(^|[^A-Za-z0-9])Mobile([^A-Za-z0-9]|$)')
                 AND NOT regexp_matches(ua, '(?i)Mac OS X|Macintosh|Windows NT|X11;|CrOS')) THEN 'mobile'
        -- UA has no device marker -> trust the raw Device Type
        WHEN device_raw = 'tablet'                         THEN 'tablet'
        WHEN device_raw = 'mobile'                         THEN 'mobile'
        -- UA silent AND raw unknown/NULL -> genuinely unknown (was 'desktop' for NULL)
        WHEN device_raw = 'unknown' OR device_raw IS NULL  THEN 'unknown'
        ELSE 'desktop'
    END                                                              AS device_type,
    -- 3.3: RFC1918 / loopback / link-local
    regexp_matches(ip, '^(10\\.|127\\.|192\\.168\\.|169\\.254\\.|172\\.(1[6-9]|2[0-9]|3[01])\\.)') AS is_private_ip,
    -- 3.3 (revised): geo metadata (country/region/city) cannot be trusted when
    -- the IP is private OR region/city are missing — a real, distinct signal,
    -- NOT a duplicate of is_private_ip. NOTE: 'region'/'city' inside this
    -- expression bind to the RAW columns (pre-NULLIF), so the NULLIF must be
    -- repeated explicitly (verified against a minimal DuckDB repro).
    is_private_ip
        OR NULLIF(NULLIF(region, ''), '-') IS NULL
        OR NULLIF(NULLIF(city, ''), '-') IS NULL                         AS geo_unreliable,
    -- 3.4: RTT flags (empty CSV cells arrive as NULL)
    rtt_str IS NULL                                                   AS rtt_missing,
    rtt_str IS NOT NULL AND try_cast(rtt_str AS DOUBLE) > 60000       AS rtt_outlier,
    -- 3.1: was the raw OS column contradicted by the UA?
    -- (token-boundary iOS/Android, same as os_family; CriOS/EdgiOS/FxiOS are
    --  honored only without an Android/WP platform token — see 3.12)
    CASE
        WHEN regexp_matches(ua, '(?i)CriOS|EdgiOS|FxiOS|(^|[^A-Za-z0-9])(iPhone|iPad|iPod|iOS)($|[^A-Za-z0-9])')
             AND NOT regexp_matches(ua, '(?i)(Android|Andorid)([^@]|$)|Windows Phone')
             AND NOT regexp_matches(os_raw, '(?i)(Android|Andorid)|Windows Phone')
             AND regexp_matches(os_raw, '(?i)(Android|Andorid)([^@]|$)') THEN TRUE
        WHEN regexp_matches(ua, '(?i)(Android|Andorid)([^@]|$)')
             AND regexp_matches(os_raw, '(?i)CriOS|EdgiOS|FxiOS|(^|[^A-Za-z0-9])(iPhone|iPad|iPod|iOS)($|[^A-Za-z0-9])|Mac OS') THEN TRUE
        WHEN regexp_matches(ua, '(?i)Windows')
             AND regexp_matches(os_raw, '(?i)(Android|Andorid)([^@]|$)|CriOS|EdgiOS|FxiOS|(^|[^A-Za-z0-9])(iPhone|iPad|iPod|iOS)($|[^A-Za-z0-9])|Mac') THEN TRUE
        WHEN regexp_matches(ua, '(?i)(Android|Andorid)([^@]|$)|(^|[^A-Za-z0-9])(iPhone|iPad|iPod|iOS)($|[^A-Za-z0-9])')
             AND regexp_matches(os_raw, '(?i)Windows') THEN TRUE
        ELSE FALSE
    END                                                              AS ua_os_conflict,
    browser_raw != array_to_string(
        list_filter(string_split(browser_raw, ' '),
            x -> x != ''
             AND NOT regexp_matches(x, '(?i)^[0-9]+([._-][0-9]+)*(-git)?$')
             AND NOT regexp_matches(x, '(?i)^variation/[0-9]+$')),
        ' ')                                                       AS version_stripped,
    -- 3.9: the dataset generator's own traffic (UA carries its repo URL)
    -- 3.12: AwarioSmartBot (a Linux crawler whose name contains 'ioS',
    --        previously mislabeled iOS)
    regexp_matches(ua, '(?i)ZipppBot|startmebot|ZoomBot|MetaJobBot|das-group|AwarioSmartBot') AS is_generator_bot,
    -- 3.11: VLC media player rows (cannot do SSO -> synthetic noise)
    regexp_matches(ua, '(?i)VLC')                                    AS is_vlc
FROM raw
"""

CHECKS_RAW = {
    "total_rows": "COUNT(*)",
    "browser_android_os_ios": "COUNT(*) FILTER (WHERE regexp_matches(column10, 'Android') AND regexp_matches(column11, 'iOS'))",
    "browser_ios_os_android": "COUNT(*) FILTER (WHERE regexp_matches(column10, 'iPhone|iPad') AND regexp_matches(column11, 'Android'))",
    "browser_win_os_mobile": "COUNT(*) FILTER (WHERE regexp_matches(column10, 'Windows') AND regexp_matches(column11, 'Android|iOS|Mac'))",
    "browser_mobile_os_win": "COUNT(*) FILTER (WHERE regexp_matches(column10, 'Android|iPhone|iPad') AND regexp_matches(column11, 'Windows'))",
    "mobile_desktop_marker": "COUNT(*) FILTER (WHERE column12='mobile' AND NOT regexp_matches(column10, 'Mobile|Android|iPhone|iPad'))",
    "private_ips": "COUNT(*) FILTER (WHERE regexp_matches(column04, '^(10\\.|127\\.|192\\.168\\.|169\\.254\\.|172\\.(1[6-9]|2[0-9]|3[01])\\.)'))",
    "private_ip_foreign": "COUNT(*) FILTER (WHERE regexp_matches(column04, '^10\\.') AND column05 != 'NO')",
    "attack_on_private": "COUNT(*) FILTER (WHERE regexp_matches(column04, '^(10\\.|127\\.|192\\.168\\.|169\\.254\\.|172\\.(1[6-9]|2[0-9]|3[01])\\.)') AND column14='True')",
    "rtt_missing": "COUNT(*) FILTER (WHERE column03 IS NULL)",
    "rtt_over_60s": "COUNT(*) FILTER (WHERE column03 IS NOT NULL AND try_cast(column03 AS DOUBLE) > 60000)",
    "genbot_rows": "COUNT(*) FILTER (WHERE regexp_matches(column09, '(?i)ZipppBot|startmebot|ZoomBot|MetaJobBot|das-group'))",
    "vlc_rows": "COUNT(*) FILTER (WHERE regexp_matches(column09, '(?i)VLC'))",
    "region_dash": "COUNT(*) FILTER (WHERE column06 = '-')",
    "city_dash": "COUNT(*) FILTER (WHERE column07 = '-')",
}

CHECKS_CLEAN = {
    "total_rows": "COUNT(*)",
    "ua_os_conflict": "COUNT(*) FILTER (WHERE ua_os_conflict)",
    "mobile_desktop_marker": "COUNT(*) FILTER (WHERE device_raw='mobile' AND device_type != 'mobile')",
    "private_ips": "COUNT(*) FILTER (WHERE is_private_ip)",
    "private_ip_foreign": "COUNT(*) FILTER (WHERE is_private_ip AND country != 'NO')",
    "attack_on_private": "COUNT(*) FILTER (WHERE is_private_ip AND is_attack_ip)",
    "rtt_missing": "COUNT(*) FILTER (WHERE rtt_missing)",
    "rtt_over_60s": "COUNT(*) FILTER (WHERE rtt_outlier)",
    "genbot_rows": "COUNT(*) FILTER (WHERE is_generator_bot)",
    "vlc_rows": "COUNT(*) FILTER (WHERE is_vlc)",
    "digit_family_rows": "COUNT(*) FILTER (WHERE regexp_matches(browser_family, '[0-9]'))",
    "geo_null_now": "COUNT(*) FILTER (WHERE region IS NULL AND city IS NULL)",
    "wp_as_ios": "COUNT(*) FILTER (WHERE os_family='iOS' AND regexp_matches(os_raw, '(?i)Windows Phone'))",
    "kaios_as_ios": "COUNT(*) FILTER (WHERE os_family='iOS' AND regexp_matches(os_raw, '(?i)KaiOS'))",
    "cros_as_android": "COUNT(*) FILTER (WHERE os_family='Android' AND regexp_matches(user_agent, '(?i)X11; CrOS'))",
    "kaios_rows": "COUNT(*) FILTER (WHERE os_family='KaiOS')",
    "null_device_rows": "COUNT(*) FILTER (WHERE device_raw IS NULL)",
    "other_os_unknown": "COUNT(*) FILTER (WHERE os_raw='Other ' AND os_family='unknown')",
    "legacy_os_rows": "COUNT(*) FILTER (WHERE os_family IN ('BlackBerry','MeeGo','Symbian','Roku','WebTV','Firefox OS'))",
    "geo_unreliable_without_private": "COUNT(*) FILTER (WHERE geo_unreliable AND NOT is_private_ip)",
    "genbot_as_ios": "COUNT(*) FILTER (WHERE os_family='iOS' AND ((regexp_matches(user_agent, '(?i)AwarioSmartBot') AND NOT regexp_matches(user_agent, '(?i)(^|[^A-Za-z0-9])(iPhone|iPad|iPod|iOS)($|[^A-Za-z0-9])|CriOS|EdgiOS|FxiOS')) OR (regexp_matches(user_agent, '(?i)CriOS') AND regexp_matches(os_raw, '(?i)Android'))))",
    # 3.13 bug signature only (same definition as src/03_validate_contract.py):
    # desktop rows reclassified mobile by a bare 'Mobile' token on a
    # desktop-OS UA. Genuine mobile UAs (Android/iPhone/WP — e.g.
    # YaApp_Android webviews send 'X11; Linux armv7l ... Mobile Safari')
    # with a lying device_raw='desktop' column are CORRECT.
    "desktop_reclass_mobile": "COUNT(*) FILTER (WHERE device_raw='desktop' AND device_type='mobile' "
                               "AND regexp_matches(user_agent, '(?i)Mobile') "
                               "AND regexp_matches(user_agent, '(?i)Mac OS X|Macintosh|Windows NT|X11;|CrOS') "
                               "AND NOT regexp_matches(user_agent, '(?i)(Android|Andorid)([^@]|$)|iPhone|iPod|Windows Phone'))",
    "null_device_unknown": "COUNT(*) FILTER (WHERE device_raw IS NULL AND device_type != 'unknown')",
}


def read_checks(path: Path, clean: bool, sample: int | None) -> dict:
    con = duckdb.connect(":memory:")
    con.execute("SET threads=8")
    if path.suffix == ".parquet":
        table = f"read_parquet('{path}')"
    elif clean:
        table = TRANSFORM.format(source=f"read_csv('{path}', header=false, skip=1, ignore_errors=true, all_varchar=true)")
    else:
        table = f"read_csv('{path}', header=false, skip=1, ignore_errors=true, all_varchar=true)"
    checks = CHECKS_CLEAN if clean else CHECKS_RAW
    if sample:
        table = f"(SELECT * FROM {table} LIMIT {sample})"
    exprs = ",\n    ".join(f"{expr} AS {name}" for name, expr in checks.items())
    row = con.execute(f"SELECT {exprs} FROM {table}").fetchone()
    con.close()
    return dict(zip(checks.keys(), row))


def clean(input_path: Path, output_path: Path, sample: int | None) -> None:
    con = duckdb.connect(":memory:")
    con.execute("SET threads=8")
    source = f"read_csv('{input_path}', header=false, skip=1, ignore_errors=true, all_varchar=true)"
    if sample:
        source = f"(SELECT * FROM {source} LIMIT {sample})"
    sql = f"COPY ({TRANSFORM.format(source=source)}) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    con.execute(sql)
    con.close()
    print(f"wrote {output_path}")


def summarize(input_path: Path, output_path: Path, sample: int | None) -> None:
    before = read_checks(input_path, clean=False, sample=sample)
    after = read_checks(output_path, clean=True, sample=None)
    summary = {
        "input": str(input_path),
        "output": str(output_path),
        "rows": after["total_rows"],
        "checks": {
            name: {"before": before.get(name), "after": after.get(name)}
            for name in CHECKS_CLEAN if name in before
        },
    }
    if sample:
        print("sample run; not writing summary file")
        return
    summary_path = DEFAULT_SUMMARY
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"summary -> {summary_path}")
    if before.get("total_rows") != after.get("total_rows"):
        print("WARNING: row count changed during cleaning!")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--sample", type=int, default=None, help="dev mode: clean only N rows")
    ap.add_argument("--verify", action="store_true", help="run checks on raw vs cleaned and print table")
    args = ap.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.verify:
        before = read_checks(args.input, clean=False, sample=args.sample)
        after = read_checks(args.output, clean=True, sample=None)
        print(f"{'check':<22}{'raw':>14}{'cleaned':>14}")
        for name in before:
            a = after.get(name)
            av = f"{a:>14,}" if isinstance(a, int) else f"{str(a):>14}"
            print(f"{name:<22}{before[name]:>14,}{av}")
        for name in ("ua_os_conflict", "geo_null_now", "wp_as_ios", "kaios_as_ios",
                     "cros_as_android", "kaios_rows", "null_device_rows", "other_os_unknown",
                     "legacy_os_rows", "geo_unreliable_without_private", "genbot_as_ios",
                     "desktop_reclass_mobile", "null_device_unknown"):
            if name in after:
                print(f"{name:<22}{'-':>14}{after[name]:>14,}")
        return

    clean(args.input, args.output, args.sample)
    summarize(args.input, args.output, args.sample)


if __name__ == "__main__":
    sys.exit(main())
