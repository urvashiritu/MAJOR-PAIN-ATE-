#!/usr/bin/env python3
"""LANL live demo storage (DuckDB).

One database file holds everything the demo needs:
  users      demo accounts (personas from LANL)
  events     every auth event: history plus live events
  alerts     events that tripped the gate

The events table carries LANL-native columns so the feature SQL
computes features from raw history using fixed time windows.
"""
import duckdb
from pathlib import Path

DB_PATH = str(Path(__file__).parent / "live.duckdb")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    raw_id TEXT NOT NULL,
    persona TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS events (
    row_id BIGINT PRIMARY KEY,
    ts TIMESTAMP,
    time INTEGER,
    user_id BIGINT NOT NULL,
    src_computer VARCHAR,
    dst_computer VARCHAR,
    auth_type VARCHAR,
    logon_type VARCHAR,
    orientation VARCHAR,
    result VARCHAR,
    -- features (matching original 8-feature training)
    dst_first BOOLEAN,
    src_first BOOLEAN,
    hour_ratio DOUBLE,
    dst_prior_events BIGINT,
    vel_1h BIGINT,
    fail_1h DOUBLE,
    hour_sin DOUBLE,
    hour_cos DOUBLE,
    -- scores
    lgb_score DOUBLE,
    if_score DOUBLE,
    combined_score DOUBLE,
    dev_points INTEGER,
    dev_reasons TEXT,
    risk_level VARCHAR,
    reasons VARCHAR,
    decision VARCHAR
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id BIGINT PRIMARY KEY,
    event_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    ts TIMESTAMP,
    level VARCHAR NOT NULL,
    combined_score DOUBLE,
    reasons VARCHAR,
    decision VARCHAR,
    acked_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_profile (
    user_id BIGINT PRIMARY KEY,
    typical_src_computers TEXT,
    typical_dst_computers TEXT,
    typical_hours TEXT,
    typical_auth_types TEXT,
    avg_events_per_hour DOUBLE,
    total_events INTEGER,
    failure_rate DOUBLE,
    profile_status TEXT DEFAULT 'ACTIVE',
    updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS demo_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_con(db_path: str = DB_PATH) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(db_path)
    con.execute("SET threads=4")
    return con


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA_SQL)
    # Migration for DBs created before the deviation columns existed
    cols = {r[0] for r in con.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'events'
    """).fetchall()}
    if "dev_points" not in cols:
        con.execute("ALTER TABLE events ADD COLUMN dev_points INTEGER")
    if "dev_reasons" not in cols:
        con.execute("ALTER TABLE events ADD COLUMN dev_reasons TEXT")


def next_event_id(con: duckdb.DuckDBPyConnection) -> int:
    return int(con.execute("SELECT COALESCE(MAX(row_id), 0) + 1 FROM events").fetchone()[0])


def refresh_profile(con: duckdb.DuckDBPyConnection, user_id: int) -> None:
    """Rebuild user_profile from event history.

    Learns from HISTORY and ALLOW rows only — flagged/blocked events must
    never teach the baseline what 'normal' looks like.
    """
    df = con.execute("""
        SELECT ts, time, src_computer, dst_computer, auth_type, result
        FROM events WHERE user_id = ? AND decision IN ('history', 'allow')
        ORDER BY time
    """, [user_id]).fetchdf()

    con.execute("INSERT OR REPLACE INTO user_profile (user_id) VALUES (?)", [user_id])
    if df.empty:
        return

    src_counts = df["src_computer"].value_counts()
    top_src = ",".join(src_counts.head(10).index.tolist())

    dst_counts = df["dst_computer"].value_counts()
    top_dst = ",".join(dst_counts.head(10).index.tolist())

    hours = ((df["time"] % 86400) // 3600).astype(int)
    top_hours = ",".join(str(h) for h in hours.value_counts().head(3).index)

    auth_counts = df["auth_type"].value_counts()
    top_auth = ",".join(auth_counts.head(3).index.tolist())

    total = len(df)
    failures = int((df["result"] == "Fail").sum())
    failure_rate = round(failures / total, 4) if total else 0.0

    if total > 1:
        time_span_hours = (df["time"].max() - df["time"].min()) / 3600.0
        avg_per_hour = round(total / max(time_span_hours, 1), 2)
    else:
        avg_per_hour = 0.0

    con.execute("""
        UPDATE user_profile SET
            typical_src_computers = ?, typical_dst_computers = ?,
            typical_hours = ?, typical_auth_types = ?,
            avg_events_per_hour = ?, total_events = ?,
            failure_rate = ?, profile_status = 'ACTIVE',
            updated_at = now()
        WHERE user_id = ?
    """, (top_src, top_dst, top_hours, top_auth,
          avg_per_hour, total, failure_rate, user_id))


def set_seed_anchor(con: duckdb.DuckDBPyConnection,
                    shifted_history_end: int, wallclock_at_seed: int) -> None:
    """Record the demo time frame.

    Live events are stamped as:  frame_time = shifted_history_end
                                 + (now - wallclock_at_seed)
    so they continue organically after history end (pseudo-hours stay near
    user habits, and vel/fail windows see both history tail and session).
    """
    con.executemany(
        "INSERT OR REPLACE INTO demo_meta (key, value) VALUES (?, ?)",
        [("seed_anchor", str(int(shifted_history_end))),
         ("seed_wallclock", str(int(wallclock_at_seed)))])


def get_seed_anchor(con: duckdb.DuckDBPyConnection):
    """Returns (frame_anchor, wallclock_at_seed) or None."""
    rows = dict(con.execute(
        "SELECT key, value FROM demo_meta WHERE key IN "
        "('seed_anchor', 'seed_wallclock')"
    ).fetchall())
    if "seed_anchor" not in rows or "seed_wallclock" not in rows:
        return None
    return int(rows["seed_anchor"]), int(rows["seed_wallclock"])
