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
    decision VARCHAR
);
"""


def get_con(db_path: str = DB_PATH) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(db_path)
    con.execute("SET threads=4")
    return con


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA_SQL)
    con.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS asn TEXT")


def next_event_id(con: duckdb.DuckDBPyConnection) -> int:
    return int(con.execute("SELECT COALESCE(MAX(row_id), 0) + 1 FROM events").fetchone()[0])
