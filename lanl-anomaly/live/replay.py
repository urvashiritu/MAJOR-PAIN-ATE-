"""Real LANL event replay.

Streams genuine scored authentication events out of the precomputed parquet
instead of synthesising them. Every event carries its real model score and its
real ground-truth label, so the dashboard can be checked against reality.

The demo window (WINDOW_START..WINDOW_END) was picked because it contains a
genuine lateral-movement burst: source machine C17693 authenticating as many
different users against many unseen destinations. RUN 14 scored the full
dataset at 590/702 attacks caught for 349 false positives.
"""
import os
import threading

import duckdb

from db import LANL_DB, SCORES_PARQUET

# Demo window. 9,954 real events, 20 of them confirmed red-team attacks.
WINDOW_START = 765000
WINDOW_END = 767000

# scorer.py derives FLAG at THRESHOLD * 0.7. The parquet decision column uses
# the same two-tier rule, so we carry it through untouched.
FLAG_FLOOR_RATIO = 0.7

_events = None
_load_lock = threading.Lock()
_meta = {}


def load_window(lo=WINDOW_START, hi=WINDOW_END):
    """Load real scored events for a time window, joined with auth metadata.

    The parquet has no auth_type, so it is joined from lanl.duckdb. The join
    key (src_user, src_computer, dst_computer, time) is not unique in feat, so
    the right side is aggregated first. Without that the join fans out and
    inflates the event count.
    """
    con = duckdb.connect(':memory:')
    con.execute("SET threads = 1")
    con.execute(f"ATTACH '{os.path.abspath(LANL_DB)}' AS lanl (READ_ONLY)")

    rows = con.execute(f"""
        SELECT s.time, s.hour, s.src_user, s.dst_user,
               s.src_computer, s.dst_computer,
               s.anomaly_score, s.decision, s.is_red, s.threshold,
               f.auth_type, f.logon_type, f.result
        FROM read_parquet('{os.path.abspath(SCORES_PARQUET)}') s
        LEFT JOIN (
            SELECT src_user, src_computer, dst_computer, time,
                   MIN(auth_type) AS auth_type,
                   MIN(logon_type) AS logon_type,
                   MIN(result) AS result
            FROM lanl.feat
            WHERE time BETWEEN {lo} AND {hi}
            GROUP BY 1, 2, 3, 4
        ) f ON f.src_user = s.src_user
           AND f.src_computer = s.src_computer
           AND f.dst_computer = s.dst_computer
           AND f.time = s.time
        WHERE s.time BETWEEN {lo} AND {hi}
        ORDER BY s.time, s.src_user, s.src_computer, s.dst_computer
    """).fetchall()

    con.close()

    events = []
    for i, r in enumerate(rows, 1):
        score = float(r[6])
        decision = str(r[7]).lower()
        events.append({
            'id': i,
            'replay': True,
            'user_id': r[2],
            'dst_user': r[3],
            'src_computer': r[4],
            'dst_computer': r[5],
            'auth_type': r[10] or 'Unknown',
            'logon_type': r[11] or 'Unknown',
            'result': r[12] or 'Success',
            'anomaly_score': round(score, 6),
            'combined_score': round(score, 6),
            'decision': decision,
            'threshold': float(r[9]),
            'hour': float(r[1]),
            'time': int(r[0]),
            'offset': int(r[0]) - lo,
            'is_red': bool(r[8]),
            'features': {},
        })

    _meta.update({
        'window_start': lo,
        'window_end': hi,
        'total': len(events),
        'attacks': sum(1 for e in events if e['is_red']),
        'blocked': sum(1 for e in events if e['decision'] == 'block'),
        'flagged': sum(1 for e in events if e['decision'] == 'flag'),
        'attacks_caught': sum(1 for e in events
                              if e['is_red'] and e['decision'] in ('block', 'flag')),
        'attacks_missed': sum(1 for e in events
                              if e['is_red'] and e['decision'] == 'allow'),
        'false_positives': sum(1 for e in events
                               if not e['is_red'] and e['decision'] in ('block', 'flag')),
        'source': os.path.relpath(SCORES_PARQUET),
    })
    return events


def get_events():
    """Return the cached replay window, loading it on first use."""
    global _events
    if _events is None:
        with _load_lock:
            if _events is None:
                _events = load_window()
    return _events


def get_meta():
    """Return summary counts for the replay window."""
    get_events()
    return dict(_meta)


def next_attack_index(events, from_index):
    """Index of the next ground-truth attack at or after from_index, else None."""
    for i in range(max(0, from_index), len(events)):
        if events[i]['is_red']:
            return i
    return None