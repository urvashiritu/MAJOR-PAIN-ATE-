#!/usr/bin/env python3
"""Phase 7c — seed the live demo database from real sample data.

Creates a handful of demo personas:
  - normal users (alice, bob, carol): real history copied from
    data/processed/sample.parquet so their profiles (countries, devices,
    seen-before state) look like real people
  - attacker: a fresh account with *no* history, backed by a blocklisted IP
    and a foreign country — the live engine should flag every attempt

History events keep their original timestamps; row_ids are reassigned in
chronological order so the (ts, row_id) windows in feature_sql behave
identically to the offline run.
"""
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "live"))

import db as db  # noqa: E402

SAMPLE = ROOT / "data" / "processed" / "sample.parquet"
DB_PATH = ROOT / "data" / "live.duckdb"

PERSONAS = [
    {"name": "alice", "persona": "normal"},
    {"name": "bob", "persona": "normal"},
    {"name": "carol", "persona": "normal"},
    {"name": "attacker", "persona": "attacker"},
]


def _pick_normal_users(con: duckdb.DuckDBPyConnection, n: int = 3) -> list:
    rows = con.execute("""
        SELECT user_id, COUNT(*) n,
               COUNT(*) FILTER (WHERE login_success) ok,
               COUNT(DISTINCT country) countries,
               COUNT(DISTINCT ip) ips
        FROM read_parquet('%s')
        WHERE NOT is_robot_sampled AND is_ato = FALSE
        GROUP BY user_id
        HAVING COUNT(*) BETWEEN 20 AND 100 AND COUNT(*) FILTER (WHERE login_success) >= 15
        ORDER BY user_id
    """ % SAMPLE).fetchall()
    return [r[0] for r in rows[:n]]


def _attack_ip(con: duckdb.DuckDBPyConnection) -> str:
    row = con.execute("""
        SELECT ip, COUNT(*) n
        FROM read_parquet('%s')
        WHERE is_attack_ip AND is_ato AND login_success = FALSE
          AND country NOT IN ('IN', 'US', 'GB')
        GROUP BY ip ORDER BY n DESC LIMIT 1
    """ % SAMPLE).fetchone()
    return row[0] if row else "45.155.205.233"


def _typical(con: duckdb.DuckDBPyConnection, user_id: int) -> dict:
    """Most common country / device / os / browser / ip / asn for a user."""
    q = f"""
        SELECT country, device_type, os_family, browser_family, ip, asn
        FROM read_parquet('{SAMPLE}')
        WHERE user_id = {user_id} AND login_success
        GROUP BY 1, 2, 3, 4, 5, 6
        ORDER BY COUNT(*) DESC LIMIT 1
    """
    row = con.execute(q).fetchone()
    return dict(zip(("country", "device_type", "os_family", "browser_family", "ip", "asn"), row))


def main() -> None:
    con = duckdb.connect(str(DB_PATH))
    con.execute("SET threads=4")
    db.init_schema(con)

    users = _pick_normal_users(con)
    if len(users) < 3:
        raise SystemExit("sample.parquet missing eligible normal users")
    attack_ip = _attack_ip(con)

    con.execute("DELETE FROM events")
    con.execute("DELETE FROM alerts")
    con.execute("DELETE FROM users")

    for i, persona in enumerate(PERSONAS):
        if persona["persona"] == "attacker":
            con.execute("""
                INSERT INTO users (user_id, name, persona, country, device_type,
                                   os_family, browser_family, ip, asn)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (-1, "attacker", "attacker", "RU", "desktop", "Windows", "Chrome",
                  attack_ip, "AS56813"))
        else:
            uid = users[i]
            t = _typical(con, uid)
            con.execute("""
                INSERT INTO users (user_id, name, persona, country, device_type,
                                   os_family, browser_family, ip, asn)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (uid, persona["name"], "normal", t["country"], t["device_type"],
                  t["os_family"], t["browser_family"], t["ip"], t["asn"]))

    history = con.execute(f"""
        SELECT ts, user_id, ip, country, asn, device_type, os_family,
               browser_family, login_success, is_attack_ip, is_ato,
               is_private_ip, geo_unreliable, rtt_missing, ua_os_conflict,
               is_generator_bot, is_vlc
        FROM read_parquet('{SAMPLE}')
        WHERE NOT is_robot_sampled
          AND user_id IN ({users[0]}, {users[1]}, {users[2]})
        ORDER BY ts, row_id
    """).fetchall()

    for i, row in enumerate(history, start=1):
        con.execute("""
            INSERT INTO events (row_id, ts, user_id, ip, country, asn,
                device_type, os_family, browser_family, login_success,
                is_attack_ip, is_ato, is_private_ip, geo_unreliable,
                rtt_missing, ua_os_conflict, is_generator_bot, is_vlc,
                decision)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'history')
        """, (i, *row))

    for uid in users + [-1]:
        db.refresh_profile(con, uid)

    n_events = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    print(f"seeded {DB_PATH}: {len(PERSONAS)} users, {n_events} history events, "
          f"attacker ip={attack_ip}")


if __name__ == "__main__":
    main()
