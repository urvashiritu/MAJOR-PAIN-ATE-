"""SQLite persistence for live-scored events.

The live feed used to be a deque in memory, so every restart erased it. This
module keeps the same event shape but writes it to disk. The Flask API reads
from here, so a scored event survives a process restart.

One table, one writer lock. At demo rates (a handful of events/second) SQLite
is more than enough and adds no service to run.
"""
import json
import os
import sqlite3
import threading

DB_PATH = os.environ.get(
    'LANL_LIVE_DB',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'live_events.db'))

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    simulated      INTEGER NOT NULL,
    source         TEXT NOT NULL DEFAULT 'employee-demo',
    user_id        TEXT NOT NULL,
    name           TEXT,
    src_computer   TEXT,
    dst_computer   TEXT,
    auth_type      TEXT,
    anomaly_score  REAL,
    combined_score REAL,
    decision       TEXT,
    is_red         INTEGER,
    ts             TEXT,
    time           INTEGER,
    reasons        TEXT,
    baseline       TEXT,
    history_events INTEGER,
    features       TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_id ON events(id);

-- Analyst decisions. Kept in a second table because a verdict belongs to an
-- alert, and an alert id is only unique within its source: replay ids come
-- from the replay window, live ids from the events table above, and those id
-- spaces overlap. (source, event_id) is the real key.
CREATE TABLE IF NOT EXISTS verdicts (
    source     TEXT NOT NULL,
    event_id   INTEGER NOT NULL,
    verdict    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (source, event_id)
);
"""

# Columns stored as JSON and parsed back on read.
_JSON_COLS = ('baseline', 'features')


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def init():
    """Create the table if needed. Safe to call on every boot."""
    os.makedirs(os.path.dirname(DB_PATH) or '.', exist_ok=True)
    with _lock:
        con = _connect()
        try:
            con.executescript(_SCHEMA)
            con.commit()
        finally:
            con.close()


def insert_event(event):
    """Persist one event and return its database id.

    `event` uses the same keys the API already serves. baseline/features are
    dicts and are stored as JSON.
    """
    row = (
        1 if event.get('simulated') else 0,
        event.get('source') or 'employee-demo',
        event.get('user_id'),
        event.get('name'),
        event.get('src_computer'),
        event.get('dst_computer'),
        event.get('auth_type'),
        event.get('anomaly_score'),
        event.get('combined_score'),
        event.get('decision'),
        None if event.get('is_red') is None else (1 if event['is_red'] else 0),
        event.get('ts'),
        event.get('time'),
        event.get('reasons'),
        json.dumps(event.get('baseline') or {}),
        event.get('history_events'),
        json.dumps(event.get('features') or {}),
    )
    with _lock:
        con = _connect()
        try:
            cur = con.execute(
                "INSERT INTO events (simulated, source, user_id, name, src_computer,"
                " dst_computer, auth_type, anomaly_score, combined_score, decision,"
                " is_red, ts, time, reasons, baseline, history_events, features)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
            con.commit()
            return int(cur.lastrowid)
        finally:
            con.close()


def _row_to_event(row):
    event = dict(row)
    event['simulated'] = bool(event['simulated'])
    event['is_red'] = None if event['is_red'] is None else bool(event['is_red'])
    for col in _JSON_COLS:
        try:
            event[col] = json.loads(event[col]) if event[col] else {}
        except (TypeError, ValueError):
            event[col] = {}
    event.pop('created_at', None)
    return event


def list_events(limit=500):
    """Most recent `limit` events, oldest first (same order as the old deque)."""
    with _lock:
        con = _connect()
        try:
            rows = con.execute(
                "SELECT * FROM (SELECT * FROM events ORDER BY id DESC LIMIT ?)"
                " ORDER BY id ASC", (int(limit),)).fetchall()
        finally:
            con.close()
    return [_row_to_event(r) for r in rows]


def count(source=None):
    """Total stored events, optionally filtered by source."""
    sql = "SELECT COUNT(*) FROM events"
    args = ()
    if source:
        sql += " WHERE source = ?"
        args = (source,)
    with _lock:
        con = _connect()
        try:
            return int(con.execute(sql, args).fetchone()[0])
        finally:
            con.close()


def clear():
    """Delete every stored live event. Used by the reset button."""
    with _lock:
        con = _connect()
        try:
            con.execute("DELETE FROM events")
            con.commit()
        finally:
            con.close()


def set_verdict(source, event_id, verdict):
    """Record an analyst decision for one alert.

    Repeat calls overwrite, so an analyst can change their mind without
    creating a second row for the same alert.
    """
    with _lock:
        con = _connect()
        try:
            con.execute(
                "INSERT INTO verdicts (source, event_id, verdict) VALUES (?,?,?)"
                " ON CONFLICT(source, event_id) DO UPDATE SET"
                " verdict=excluded.verdict, created_at=datetime('now')",
                (str(source), int(event_id), str(verdict)))
            con.commit()
        finally:
            con.close()


def get_verdicts(source):
    """Map event_id -> verdict for one source. Empty dict when none exist."""
    with _lock:
        con = _connect()
        try:
            rows = con.execute(
                "SELECT event_id, verdict FROM verdicts WHERE source = ?",
                (str(source),)).fetchall()
        finally:
            con.close()
    return {int(r['event_id']): r['verdict'] for r in rows}


def clear_verdicts(source=None):
    """Delete stored decisions, optionally only for one source.

    Called with source='live' by /api/reset, which wipes the live events but
    deliberately leaves replay state alone.
    """
    with _lock:
        con = _connect()
        try:
            if source:
                con.execute("DELETE FROM verdicts WHERE source = ?", (str(source),))
            else:
                con.execute("DELETE FROM verdicts")
            con.commit()
        finally:
            con.close()
