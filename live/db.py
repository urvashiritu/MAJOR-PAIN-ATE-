#!/usr/bin/env python3
"""Phase 7a — live demo storage (DuckDB).

One database file holds everything the demo needs:
  users      demo accounts (a handful of personas)
  events     every login event: the user's history plus new live events
  alerts     events that tripped the rule/ML gate (for the admin panel)

The events table carries the same clean columns the training pipeline used
(see data/processed/sample.parquet), so feature_sql / score_sql from
src/02 and src/04 run against live rows exactly as they did offline.
"""
import duckdb
import pandas as pd

DB_PATH = "data/live.duckdb"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    persona TEXT NOT NULL,            -- 'normal' | 'attacker' (demo guidance)
    country TEXT,                     -- attacker's usual country
    device_type TEXT,                 -- attacker's usual device
    os_family TEXT,
    browser_family TEXT,
    ip TEXT,                          -- attacker's usual ip
    asn TEXT,                         -- usual asn
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS events (
    row_id BIGINT,
    ts TIMESTAMP NOT NULL,
    user_id BIGINT NOT NULL,
    ip VARCHAR,
    country VARCHAR,
    device_type VARCHAR,
    os_family VARCHAR,
    browser_family VARCHAR,
    login_success BOOLEAN NOT NULL,
    is_attack_ip BOOLEAN,
    is_ato BOOLEAN,
    is_private_ip BOOLEAN,
    geo_unreliable BOOLEAN,
    rtt_missing BOOLEAN,
    ua_os_conflict BOOLEAN,
    is_generator_bot BOOLEAN,
    is_vlc BOOLEAN,
    asn VARCHAR,
    rule_score INTEGER,
    ml_score DOUBLE,
    risk_level VARCHAR,
    reasons VARCHAR,
    decision VARCHAR,                 -- 'allow' | 'flag' | 'block' | 'history'
    PRIMARY KEY (row_id)
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id BIGINT PRIMARY KEY,
    event_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    ts TIMESTAMP NOT NULL,
    level VARCHAR NOT NULL,           -- low | medium | high | critical
    rule_score INTEGER,
    ml_score DOUBLE,
    reasons VARCHAR,
    decision VARCHAR,
    acked_at TIMESTAMP                -- set when an analyst acknowledges
);

CREATE TABLE IF NOT EXISTS user_profile (
    user_id BIGINT PRIMARY KEY,
    usual_country TEXT,               -- mode over successful logins
    usual_device_type TEXT,
    usual_os_family TEXT,
    usual_browser_family TEXT,
    usual_ip TEXT,
    usual_asn TEXT,
    top_hours TEXT,                   -- CSV of top-3 hour buckets, e.g. "8,17,21"
    avg_logins_per_day DOUBLE,        -- over the user's active days
    failed_24h INTEGER,               -- failed logins in the last 24 hours
    updated_at TIMESTAMP DEFAULT now()
);
"""


def get_con(db_path: str = DB_PATH) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(db_path)
    con.execute("SET threads=4")
    return con


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA_SQL)
    con.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS asn TEXT")
    con.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS acked_at TIMESTAMP")


def next_event_id(con: duckdb.DuckDBPyConnection) -> int:
    return int(con.execute("SELECT COALESCE(MAX(row_id), 0) + 1 FROM events").fetchone()[0])


def refresh_profile(con: duckdb.DuckDBPyConnection, user_id: int) -> None:
    """Rebuild the user_profile row from the user's event history.

    Called only after an *accepted* (allowed) event: the profile must
    describe verified normal behavior, never attacker attempts.
    "Usual" fields are the mode over successful logins; failed_24h counts
    any failure in the last 24 hours.
    """
    df = con.execute("""
        SELECT ts, country, device_type, os_family, browser_family, ip, asn,
               login_success
        FROM events WHERE user_id = ? ORDER BY ts
    """, [user_id]).fetchdf()

    con.execute("INSERT OR REPLACE INTO user_profile (user_id) VALUES (?)", [user_id])
    if df.empty:
        return

    ts = df["ts"]
    if ts.dt.tz is not None:
        ts = ts.dt.tz_localize(None)
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)

    def mode(col):
        vc = df.loc[df["login_success"] & df[col].notna(), col].value_counts()
        return vc.index[0] if len(vc) else None

    top_hours = ",".join(str(h) for h in ts.dt.hour.value_counts().head(3).index)
    days = ts.dt.date.nunique()
    failed_24h = int((~df.loc[ts >= now - pd.Timedelta(hours=24), "login_success"]).sum())

    con.execute("""
        UPDATE user_profile SET usual_country = ?, usual_device_type = ?,
            usual_os_family = ?, usual_browser_family = ?, usual_ip = ?,
            usual_asn = ?, top_hours = ?, avg_logins_per_day = ?,
            failed_24h = ?, updated_at = now()
        WHERE user_id = ?
    """, (mode("country"), mode("device_type"), mode("os_family"),
          mode("browser_family"), mode("ip"), mode("asn"), top_hours,
          round(len(df) / days, 2) if days else None, failed_24h, user_id))
