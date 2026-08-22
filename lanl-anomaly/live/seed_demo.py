#!/usr/bin/env python3
"""LANL live demo seeder — reads raw events from slice.parquet.

Creates demo personas from real LANL data:
  - 3 normal users with full history
  - 1 attacker user (U748@DOM1) with C17693 source computer

History events are stored with raw LANL columns. Features are computed
LIVE when events are scored by the scoring engine.
"""
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live"))

import db as db  # noqa: E402

SLICE = ROOT / "data" / "raw" / "lanl" / "slice.parquet"
DB_PATH = ROOT / "data" / "live.duckdb"

NORMAL_USERS = [
    {"raw_id": "U10059@DOM1", "name": "alice"},
    {"raw_id": "U10158@DOM1", "name": "bob"},
    {"raw_id": "U10500@DOM1", "name": "carol"},
]

ATTACKER = {"raw_id": "U748@DOM1", "name": "attacker", "src_computer": "C17693"}


def _user_events(con: duckdb.DuckDBPyConnection, raw_id: str) -> list:
    return con.execute(f"""
        SELECT time, src_user, dst_user, src_computer, dst_computer,
               auth_type, logon_type, orientation, result
        FROM read_parquet('{SLICE}')
        WHERE src_user = '{raw_id}'
        ORDER BY time, src_computer, dst_computer
    """).fetchall()


def main() -> None:
    con = db.get_con(str(DB_PATH))
    db.init_schema(con)

    con.execute("DELETE FROM events")
    con.execute("DELETE FROM alerts")
    con.execute("DELETE FROM users")
    con.execute("DELETE FROM user_profile")

    row_counter = 1
    for i, user in enumerate(NORMAL_USERS):
        user_id = i + 1
        con.execute("""
            INSERT INTO users (user_id, name, raw_id, persona)
            VALUES (?, ?, ?, 'normal')
        """, (user_id, user["name"], user["raw_id"]))

        events = _user_events(con, user["raw_id"])
        for j, row in enumerate(events):
            time_int = row[0]
            con.execute("""
                INSERT INTO events (row_id, time, user_id, src_computer, dst_computer,
                    auth_type, logon_type, orientation, result, decision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'history')
            """, (row_counter, time_int, user_id, row[3], row[4],
                  row[5], row[6], row[7], row[8]))
            row_counter += 1

        print(f"  seeded {user['name']} ({user['raw_id']}): {len(events)} history events")

    attacker_id = -1
    con.execute("""
        INSERT INTO users (user_id, name, raw_id, persona)
        VALUES (?, ?, ?, 'attacker')
    """, (attacker_id, ATTACKER["name"], ATTACKER["raw_id"]))

    attacker_events = _user_events(con, ATTACKER["raw_id"])
    for j, row in enumerate(attacker_events):
        time_int = row[0]
        con.execute("""
            INSERT INTO events (row_id, time, user_id, src_computer, dst_computer,
                auth_type, logon_type, orientation, result, decision)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'history')
        """, (row_counter, time_int, attacker_id, row[3], row[4],
              row[5], row[6], row[7], row[8]))
        row_counter += 1

    print(f"  seeded attacker ({ATTACKER['raw_id']}): {len(attacker_events)} history events "
          f"({sum(1 for e in attacker_events if e[3] == ATTACKER['src_computer'])} from {ATTACKER['src_computer']})")

    for user_id in [1, 2, 3, attacker_id]:
        db.refresh_profile(con, user_id)

    n_events = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    n_users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"\nseeded {DB_PATH}: {n_users} users, {n_events} history events")


if __name__ == "__main__":
    main()
