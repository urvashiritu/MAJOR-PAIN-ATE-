#!/usr/bin/env python3
"""LANL live demo storage (DuckDB).

One database file holds everything the demo needs:
  users      demo accounts (a handful of personas from LANL)
  events     every auth event: the user's history plus new live events
  alerts     events that tripped the gate (for the admin panel)

The events table carries LANL-native columns (src_computer, dst_computer,
auth_type, etc.) so the feature SQL computes features from raw history.
"""
import duckdb
import pandas as pd

DB_PATH = "data/live.duckdb"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    raw_id TEXT NOT NULL,            -- "U748@DOM1"
    persona TEXT NOT NULL,           -- 'normal' | 'attacker'
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS events (
    row_id BIGINT PRIMARY KEY,
    ts TIMESTAMP,
    time INTEGER,                    -- LANL seconds from epoch (for window functions)
    user_id BIGINT NOT NULL,
    src_computer VARCHAR,
    dst_computer VARCHAR,
    auth_type VARCHAR,
    logon_type VARCHAR,
    orientation VARCHAR,
    result VARCHAR,
    -- computed features
    dst_first BOOLEAN,
    src_first BOOLEAN,
    hour_ratio DOUBLE,
    dst_prior_events BIGINT,
    fail_1h DOUBLE,
    vel_1h BIGINT,
    hour_sin DOUBLE,
    hour_cos DOUBLE,
    -- scores
    lgb_score DOUBLE,
    if_score DOUBLE,
    combined_score DOUBLE,
    risk_level VARCHAR,
    reasons VARCHAR,
    decision VARCHAR                 -- 'allow' | 'flag' | 'block' | 'history' | 'pending'
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id BIGINT PRIMARY KEY,
    event_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    ts TIMESTAMP,
    level VARCHAR NOT NULL,           -- low | medium | high | critical
    combined_score DOUBLE,
    reasons VARCHAR,
    decision VARCHAR,
    acked_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_profile (
    user_id BIGINT PRIMARY KEY,
    typical_src_computers TEXT,       -- CSV of top src computers
    typical_dst_computers TEXT,       -- CSV of top dst computers
    typical_hours TEXT,               -- CSV of top hour buckets
    typical_auth_types TEXT,          -- CSV of top auth types
    avg_events_per_hour DOUBLE,
    total_events INTEGER,
    failure_rate DOUBLE,
    profile_status TEXT DEFAULT 'ACTIVE',
    updated_at TIMESTAMP DEFAULT now()
);
"""


def get_con(db_path: str = DB_PATH) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(db_path)
    con.execute("SET threads=4")
    return con


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA_SQL)


def next_event_id(con: duckdb.DuckDBPyConnection) -> int:
    return int(con.execute("SELECT COALESCE(MAX(row_id), 0) + 1 FROM events").fetchone()[0])


def refresh_profile(con: duckdb.DuckDBPyConnection, user_id: int) -> None:
    """Rebuild the user_profile row from the user's event history.

    Called only after an *accepted* (allowed) event: the profile must
    describe verified normal behavior, never attacker attempts.
    """
    df = con.execute("""
        SELECT ts, time, src_computer, dst_computer, auth_type, result
        FROM events WHERE user_id = ? AND decision != 'pending' ORDER BY time
    """, [user_id]).fetchdf()

    con.execute("INSERT OR REPLACE INTO user_profile (user_id) VALUES (?)", [user_id])
    if df.empty:
        return

    def mode(col):
        vc = df.loc[df[col].notna(), col].value_counts()
        return vc.index[0] if len(vc) else None

    # Top source computers
    src_counts = df["src_computer"].value_counts()
    top_src = ",".join(src_counts.head(5).index.tolist())

    # Top destination computers
    dst_counts = df["dst_computer"].value_counts()
    top_dst = ",".join(dst_counts.head(5).index.tolist())

    # Top hours (from time integer)
    hours = ((df["time"] % 86400) // 3600).astype(int)
    top_hours = ",".join(str(h) for h in hours.value_counts().head(3).index)

    # Top auth types
    auth_counts = df["auth_type"].value_counts()
    top_auth = ",".join(auth_counts.head(3).index.tolist())

    # Stats
    total = len(df)
    failures = int((df["result"] == "Fail").sum())
    failure_rate = round(failures / total, 4) if total else 0.0

    # Events per hour (using time span)
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
