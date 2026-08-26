#!/usr/bin/env python3
"""Build per-event windowed features for auth anomaly detection.

All features are computed from the event's PAST only (no future leakage).
No IP-level aggregates — everything must be computable from event context.

Features (9):
  fail_1h: failed attempts by src_ip in last 1 hour
  vel_1h: event count by src_ip in last 1 hour
  fail_24h: failed attempts by src_ip in last 24 hours
  vel_24h: event count by src_ip in last 24 hours
  user_fail_rate: historical failure rate for this src_user (all past events)
  src_ip_fail_rate: historical failure rate for this src_ip (all past events)
  hour_ratio, hour_sin, hour_cos: temporal features
"""

import duckdb
from pathlib import Path

DB_PATH = Path("data/auth.duckdb")
OUT_PATH = Path("outputs/features_lanl.parquet")

ATTACK_IPS = [
    "185.220.101.17", "45.155.205.233", "91.240.118.172",
    "103.75.201.44", "194.26.135.119",
    "10.20.99.101", "10.20.99.102", "10.20.99.103",
    "10.20.99.104", "10.20.99.105",
]

FEATURE_COLS = [
    "fail_1h", "vel_1h", "fail_24h", "vel_24h",
    "user_fail_rate", "src_ip_fail_rate",
    "hour_ratio", "hour_sin", "hour_cos",
]


def main():
    con = duckdb.connect(str(DB_PATH))

    # Normalize timestamps
    con.execute("""
        CREATE OR REPLACE VIEW auth_norm AS
        SELECT
            CASE
                WHEN source = 'SSH' AND timestamp LIKE '2026-__-__ %' THEN strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                WHEN source = 'SSH' THEN strptime(timestamp, '%Y-%b %d %H:%M:%S')
                WHEN source = 'WEB' AND timestamp LIKE '%,%' THEN strptime(replace(timestamp, ',', '.'), '%Y-%m-%d %H:%M:%S.%f')
                WHEN source = 'WEB' THEN strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                WHEN source = 'WINDOWS' THEN cast(timestamp AS TIMESTAMP)
                ELSE strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            END AS ts,
            src_user,
            src_ip,
            success,
            source,
            auth_type
        FROM auth_events
    """)

    print("Building per-event windowed features ...")

    # Step 1: Number rows
    con.execute("""
        CREATE OR REPLACE VIEW auth_numbered AS
        SELECT *,
            ROW_NUMBER() OVER (ORDER BY ts, src_ip, src_user) AS row_id,
            EXTRACT(HOUR FROM ts) AS hour
        FROM auth_norm
    """)

    # Step 2: fail_1h, vel_1h (1-hour window)
    print("  fail_1h, vel_1h ...")
    con.execute("""
        CREATE OR REPLACE VIEW auth_basic AS
        SELECT a.*,
            (SELECT count(*) FROM auth_norm f
             WHERE f.src_ip = a.src_ip AND NOT f.success
               AND f.ts > a.ts - INTERVAL '1 hour' AND f.ts <= a.ts
            ) AS fail_1h,
            (SELECT count(*) FROM auth_norm v
             WHERE v.src_ip = a.src_ip
               AND v.ts > a.ts - INTERVAL '1 hour' AND v.ts <= a.ts
            ) AS vel_1h
        FROM auth_numbered a
    """)

    # Step 3: fail_24h, vel_24h (24-hour window)
    print("  fail_24h, vel_24h ...")
    con.execute("""
        CREATE OR REPLACE VIEW auth_24h AS
        SELECT a.*,
            (SELECT count(*) FROM auth_norm f
             WHERE f.src_ip = a.src_ip AND NOT f.success
               AND f.ts > a.ts - INTERVAL '24 hours' AND f.ts <= a.ts
            ) AS fail_24h,
            (SELECT count(*) FROM auth_norm v
             WHERE v.src_ip = a.src_ip
               AND v.ts > a.ts - INTERVAL '24 hours' AND v.ts <= a.ts
            ) AS vel_24h
        FROM auth_basic a
    """)

    # Step 4: user_fail_rate (historical failure rate for this user BEFORE this event)
    print("  user_fail_rate ...")
    con.execute("""
        CREATE OR REPLACE VIEW user_rates AS
        SELECT
            src_ip,
            src_user,
            ts,
            CASE WHEN (SELECT count(*) FROM auth_norm f
                       WHERE f.src_user = a.src_user AND f.ts < a.ts) > 0
            THEN (SELECT count(*) FROM auth_norm f
                  WHERE f.src_user = a.src_user AND f.ts < a.ts AND NOT f.success)::FLOAT /
                 (SELECT count(*) FROM auth_norm f
                  WHERE f.src_user = a.src_user AND f.ts < a.ts)
            ELSE 0.5 END AS user_fail_rate
        FROM auth_norm a
    """)

    # Step 5: src_ip_fail_rate (historical failure rate for this IP BEFORE this event)
    print("  src_ip_fail_rate ...")
    con.execute("""
        CREATE OR REPLACE VIEW ip_rates AS
        SELECT
            src_ip,
            ts,
            CASE WHEN (SELECT count(*) FROM auth_norm f
                       WHERE f.src_ip = a.src_ip AND f.ts < a.ts) > 0
            THEN (SELECT count(*) FROM auth_norm f
                  WHERE f.src_ip = a.src_ip AND f.ts < a.ts AND NOT f.success)::FLOAT /
                 (SELECT count(*) FROM auth_norm f
                  WHERE f.src_ip = a.src_ip AND f.ts < a.ts)
            ELSE 0.0 END AS src_ip_fail_rate
        FROM auth_norm a
    """)

    # Step 6: Combine
    print("  Combining ...")
    con.execute("""
        CREATE OR REPLACE VIEW features AS
        SELECT
            a.src_user,
            a.src_ip,
            a.source,
            a.auth_type,
            a.success,
            a.ts,
            a.fail_1h,
            a.vel_1h,
            a.fail_24h,
            a.vel_24h,
            COALESCE(ur.user_fail_rate, 0.5) AS user_fail_rate,
            COALESCE(ir.src_ip_fail_rate, 0.0) AS src_ip_fail_rate,
            a.hour / 24.0 AS hour_ratio,
            sin(2.0 * 3.14159265 * a.hour / 24.0) AS hour_sin,
            cos(2.0 * 3.14159265 * a.hour / 24.0) AS hour_cos,
            (a.src_ip IN ({attack_ips}))::INT AS is_attack
        FROM auth_24h a
        LEFT JOIN user_rates ur ON a.src_ip = ur.src_ip AND a.src_user = ur.src_user AND a.ts = ur.ts
        LEFT JOIN ip_rates ir ON a.src_ip = ir.src_ip AND a.ts = ir.ts
    """.format(attack_ips=", ".join(f"'{ip}'" for ip in ATTACK_IPS)))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT * FROM features) TO '{OUT_PATH}' (FORMAT PARQUET)")

    total = con.execute("SELECT count(*) FROM features").fetchone()[0]
    attacks = con.execute("SELECT count(*) FROM features WHERE is_attack = 1").fetchone()[0]
    print(f"\nFeatures: {total} rows, {attacks} attacks ({100*attacks/total:.1f}%)")
    print(f"Saved → {OUT_PATH}")

    print("\nFeature stats (attack vs normal):")
    stats = con.execute("""
        SELECT is_attack,
            round(avg(fail_1h), 2), round(avg(vel_1h), 2),
            round(avg(fail_24h), 1), round(avg(vel_24h), 1),
            round(avg(user_fail_rate), 3), round(avg(src_ip_fail_rate), 3)
        FROM features GROUP BY is_attack
    """).fetchall()
    labels = ["fail_1h", "vel_1h", "fail_24h", "vel_24h", "user_fail_rate", "src_ip_fail_rate"]
    for row in stats:
        tag = "ATTACK" if row[0] else "NORMAL"
        vals = ", ".join(f"{n}={v}" for n, v in zip(labels, row[1:]))
        print(f"  {tag}: {vals}")

    con.close()


if __name__ == "__main__":
    main()
