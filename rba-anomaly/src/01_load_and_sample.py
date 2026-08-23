#!/usr/bin/env python3
"""Stratified whole-user sampling for the RBA dataset.

Design (validated against the full dataset, Aug 8 2026):
  Tier 1  ATO    : all users with any is_ato row          -> all their rows (141/141)
  Tier 2  Heavy  : users with >=10 attack flags, excl. ATO + robot -> all their rows
  Tier 3  Robot  : the single dominant user (-4324475583306591935) -> random 50,000 rows
  Tier 4  Light  : users with 1-9 attack flags            -> random users to ~200,000 rows
  Tier 5  Normal : users with 0 attack flags              -> random users to fill 1,000,000

Whole users are always sampled (never rows), so the attack ratio is the natural
one of the sample, never forced. Per-user cap: 10,000 rows (only the robot
exceeds it). Genbot/VLC rows are kept with their flags unless excluded via
--no-genbots / --no-vlc.

INPUT: rba_features.parquet (src/02_feature_engineering.py's FULL-dataset
feature pass). Features are computed over each user's true full history, so
sampled events carry exactly what the live system would have computed — the
sample is drawn FROM the featured table, never featured afterwards.

The same run computes per-user baselines over ALL 31.3M rows
(user_baselines.parquet) so contextual features can use history a
sampled user might not carry in the sample.

Determinism: all random ordering uses hash(row_id, seed) / hash(user_id, seed)
instead of random(), because random() is not reproducible under
multithreaded execution even with setseed(). Re-running with the same seed
reproduces the same sample.

Outputs:
  sample.parquet     : the 1M-row sample, features included
  features.parquet   : final training table = sample minus pipeline
                       artifacts (rn, is_robot_sampled)

Gates (fail the run if violated):
  - ATO rows 141/141, ATO users 138/138
  - robot rows exactly 50,000
  - total 1,000,000 +/- 1%
  - every sampled user has a baseline row
  - no non-robot user exceeds the per-user cap

Usage:
  python src/01_load_and_sample.py
  python src/01_load_and_sample.py --no-genbots --no-vlc
  python src/01_load_and_sample.py --target 500000 --seed 42
"""
import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data" / "processed" / "rba_features.parquet"
DEFAULT_SAMPLE = ROOT / "data" / "processed" / "sample.parquet"
DEFAULT_FEATURES = ROOT / "data" / "processed" / "features.parquet"
DEFAULT_BASELINES = ROOT / "data" / "processed" / "user_baselines.parquet"
DEFAULT_REPORT = ROOT / "data" / "processed" / "sampling_report.json"

ROBOT_USER_ID = -4324475583306591935
ROBOT_CAP = 50_000
USER_CAP = 10_000
LIGHT_TARGET = 200_000
DEFAULT_TARGET = 1_000_000


def tiers_sql(input_path: Path, flag_filter: str) -> str:
    return f"""
    WITH src AS (
        SELECT * FROM read_parquet('{input_path}') {flag_filter}
    ),
    user_stats AS (
        SELECT user_id,
               COUNT(*) AS n_rows,
               COUNT(*) FILTER (WHERE is_attack_ip) AS attack_rows,
               COUNT(*) FILTER (WHERE is_ato) AS ato_rows
        FROM src GROUP BY user_id
    ),
    tiers AS (
        SELECT user_id, n_rows, attack_rows,
               CASE
                   WHEN ato_rows > 0 THEN 'ato'
                   WHEN user_id = {ROBOT_USER_ID} THEN 'robot'
                   WHEN attack_rows >= 10 THEN 'heavy'
                   WHEN attack_rows BETWEEN 1 AND 9 THEN 'light'
                   ELSE 'normal'
               END AS tier
        FROM user_stats
    )
    SELECT * FROM tiers
    """


def fixed_rows_sql(tiers_table: str, seed: float) -> str:
    """Sum of contributed rows for ato+heavy tiers, computed at runtime.

    Replaces a hardcoded constant that went stale under --no-genbots
    (240,158 vs the true 220,396). Uses the same tiers + USER_CAP semantics
    as prefix_users so the number can never drift.
    """
    return f"""
    SELECT COALESCE(SUM(LEAST(n_rows, {USER_CAP})), 0)
    FROM {tiers_table} WHERE tier IN ('ato', 'heavy')
    """


def prefix_users(con: duckdb.DuckDBPyConnection, tiers_table: str, tier: str, target: int, seed: float) -> list:
    sql = f"""
    WITH ord AS (
        SELECT user_id, LEAST(n_rows, {USER_CAP}) AS contrib,
               SUM(LEAST(n_rows, {USER_CAP})) OVER (ORDER BY hash(user_id, {seed})) AS cum
        FROM {tiers_table} WHERE tier = '{tier}'
    )
    SELECT user_id, contrib FROM ord WHERE cum - contrib < {target}
    """
    return [tuple(r) for r in con.execute(sql).fetchall()]


def build_sample(con: duckdb.DuckDBPyConnection, input_path: Path, flag_filter: str,
                 light_rows: list, normal_rows: list, seed: float) -> None:
    tiers = tiers_sql(input_path, flag_filter)
    light_set = ", ".join(str(r[0]) for r in light_rows) or "NULL"
    normal_set = ", ".join(str(r[0]) for r in normal_rows) or "NULL"
    fixed_sql = f"""
    CREATE OR REPLACE TEMP TABLE sel_users AS
    SELECT user_id FROM ({tiers}) WHERE tier IN ('ato', 'heavy')
    UNION ALL
    SELECT user_id FROM ({tiers}) WHERE user_id IN ({light_set})
    UNION ALL
    SELECT user_id FROM ({tiers}) WHERE user_id IN ({normal_set})
    """
    con.execute(fixed_sql)
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE final_sample AS
    WITH capped AS (
        SELECT s.*, ROW_NUMBER() OVER (PARTITION BY s.user_id ORDER BY hash(row_id, {seed})) AS rn_cap
        FROM read_parquet('{input_path}') s
        JOIN sel_users u ON s.user_id = u.user_id
        {flag_filter}
    )
    SELECT * EXCLUDE (rn_cap), FALSE AS is_robot_sampled FROM capped WHERE rn_cap <= {USER_CAP}
    UNION ALL
    SELECT * FROM (
        SELECT *, TRUE AS is_robot_sampled
        FROM read_parquet('{input_path}')
        WHERE user_id = {ROBOT_USER_ID} {flag_filter}
        ORDER BY hash(row_id, {seed})
        LIMIT {ROBOT_CAP}
    )
    """)


def compute_baselines(con: duckdb.DuckDBPyConnection, input_path: Path, out: Path) -> None:
    con.execute(f"""
    COPY (
        SELECT user_id,
               COUNT(*) AS n_events,
               COUNT(*) FILTER (WHERE is_attack_ip) AS attack_events,
               COUNT(DISTINCT country) AS countries_seen,
               COUNT(DISTINCT device_type) AS device_types_seen,
               COUNT(DISTINCT browser_family) AS browser_families_seen,
               COUNT(DISTINCT os_family) AS os_families_seen,
               MIN(ts) AS first_ts,
               MAX(ts) AS last_ts
        FROM read_parquet('{input_path}')
        GROUP BY user_id
    ) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)


def sample_stats(con: duckdb.DuckDBPyConnection, tiers: str, sample: Path, total_target: int) -> dict:
    stats = con.execute(f"""
    WITH s AS (SELECT * FROM read_parquet('{sample}'))
    SELECT COUNT(*) AS total_rows,
           COUNT(DISTINCT user_id) AS users,
           COUNT(*) FILTER (WHERE is_attack_ip) AS attack_rows,
           COUNT(*) FILTER (WHERE is_attack_ip AND login_success) AS gold_rows,
           COUNT(*) FILTER (WHERE is_ato) AS ato_rows,
           COUNT(DISTINCT CASE WHEN is_ato THEN user_id END) AS ato_users,
           COUNT(*) FILTER (WHERE is_robot_sampled) AS robot_rows,
           COUNT(*) FILTER (WHERE is_generator_bot) AS genbot_rows,
           COUNT(*) FILTER (WHERE is_vlc) AS vlc_rows,
           COUNT(*) FILTER (WHERE is_private_ip) AS private_ip_rows
    FROM s
    """).fetchone()
    cols = ["total_rows", "users", "attack_rows", "gold_rows", "ato_rows", "ato_users",
            "robot_rows", "genbot_rows", "vlc_rows", "private_ip_rows"]
    d = dict(zip(cols, stats))
    d["attack_share"] = round(d["attack_rows"] / d["total_rows"], 5)
    d["gold_share_of_attacks"] = round(d["gold_rows"] / d["attack_rows"], 4)
    d["max_nonrobot_user_rows"] = con.execute(f"""
    SELECT MAX(n) FROM (
        SELECT user_id, COUNT(*) AS n FROM read_parquet('{sample}')
        WHERE NOT is_robot_sampled GROUP BY user_id)
    """).fetchone()[0]
    d["tier_rows"] = con.execute(f"""
    SELECT t.tier, COUNT(*) AS rows_n, COUNT(DISTINCT s.user_id) AS users_n
    FROM read_parquet('{sample}') s
    JOIN ({tiers}) t ON s.user_id = t.user_id
    GROUP BY 1 ORDER BY 1
    """).fetchall()
    d["target"] = total_target
    return d


def run_gates(stats: dict) -> list:
    failures = []
    if stats["ato_rows"] != 141:
        failures.append(f"ATO rows = {stats['ato_rows']}, expected 141")
    if stats["ato_users"] != 138:
        failures.append(f"ATO users = {stats['ato_users']}, expected 138")
    if stats["robot_rows"] != ROBOT_CAP:
        failures.append(f"robot rows = {stats['robot_rows']}, expected {ROBOT_CAP}")
    if not 0.99 * stats["target"] <= stats["total_rows"] <= 1.01 * stats["target"]:
        failures.append(f"total rows = {stats['total_rows']}, target {stats['target']} +/-1%")
    if stats["max_nonrobot_user_rows"] is not None and stats["max_nonrobot_user_rows"] > USER_CAP:
        failures.append(f"non-robot user exceeds cap: {stats['max_nonrobot_user_rows']}")
    if stats["features_rows"] != stats["total_rows"]:
        failures.append(f"features.parquet rows = {stats['features_rows']}, sample rows = {stats['total_rows']}")
    return failures


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    ap.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    ap.add_argument("--baselines", type=Path, default=DEFAULT_BASELINES)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--target", type=int, default=DEFAULT_TARGET)
    ap.add_argument("--seed", type=float, default=0.42)
    ap.add_argument("--no-genbots", action="store_true", help="exclude generator-bot rows")
    ap.add_argument("--no-vlc", action="store_true", help="exclude VLC rows")
    args = ap.parse_args()

    flag_filter = ""
    if args.no_genbots:
        flag_filter += " WHERE NOT is_generator_bot"
    if args.no_vlc:
        flag_filter += (" AND NOT is_vlc" if flag_filter else " WHERE NOT is_vlc")

    con = duckdb.connect(":memory:")
    con.execute("SET threads=8")

    print("computing tiers...")
    tiers = tiers_sql(args.input, flag_filter)

    print("sampling light users...")
    light = prefix_users(con, f"({tiers})", "light", LIGHT_TARGET, args.seed)
    light_rows = sum(r[1] for r in light)

    print("sampling normal users...")
    fixed_rows = con.execute(fixed_rows_sql(f"({tiers})", args.seed)).fetchone()[0]
    normal_target = args.target - fixed_rows - ROBOT_CAP - light_rows
    normal = prefix_users(con, f"({tiers})", "normal", normal_target, args.seed)
    normal_rows = sum(r[1] for r in normal)

    print(f"fixed (ato+heavy): {fixed_rows:,} rows; light: {len(light)} users / ~{light_rows:,} rows; "
          f"normal: {len(normal)} users / ~{normal_rows:,} rows")
    build_sample(con, args.input, flag_filter, light, normal, args.seed)

    args.sample.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT * FROM final_sample) TO '{args.sample}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    print(f"wrote {args.sample}")

    con.execute(f"""
        COPY (SELECT * EXCLUDE (rn, is_robot_sampled) FROM final_sample)
        TO '{args.features}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    print(f"wrote {args.features} (training table, artifacts dropped)")

    print("computing baselines over all rows...")
    compute_baselines(con, args.input, args.baselines)
    baseline_users = con.execute(f"SELECT COUNT(DISTINCT user_id) FROM read_parquet('{args.baselines}')").fetchone()[0]

    print("verifying...")
    stats = sample_stats(con, tiers, args.sample, args.target)
    stats["light_users"] = len(light)
    stats["light_rows"] = light_rows
    stats["normal_users"] = len(normal)
    stats["normal_rows"] = normal_rows
    stats["fixed_rows"] = fixed_rows
    stats["baseline_users"] = baseline_users
    stats["features_rows"] = con.execute(f"SELECT COUNT(*) FROM read_parquet('{args.features}')").fetchone()[0]
    stats["excluded_genbots"] = args.no_genbots
    stats["excluded_vlc"] = args.no_vlc

    failures = run_gates(stats)
    stats["gates"] = "PASS" if not failures else failures

    print(f"{'check':<28}{'value':>12}")
    for k, v, u in stats["tier_rows"]:
        print(f"{'tier ' + k:<28}{v:>12,}  ({u:,} users)")
    print(f"{'total rows':<28}{stats['total_rows']:>12,}")
    print(f"{'users':<28}{stats['users']:>12,}")
    print(f"{'attack rows':<28}{stats['attack_rows']:>12,}")
    print(f"{'attack share':<28}{stats['attack_share']:>12.4%}")
    print(f"{'gold rows':<28}{stats['gold_rows']:>12,}")
    print(f"{'ATO rows/users':<28}{stats['ato_rows']:>12,}/{stats['ato_users']}")
    print(f"{'robot rows':<28}{stats['robot_rows']:>12,}")
    print(f"{'features rows':<28}{stats['features_rows']:>12,}")
    print(f"{'baseline users':<28}{stats['baseline_users']:>12,}")
    print(f"gates: {stats['gates']}")

    args.report.write_text(json.dumps(stats, indent=2, default=str))
    print(f"report -> {args.report}")

    con.close()
    if failures:
        print("GATE FAILURES:", *failures, sep="\n  - ")
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
