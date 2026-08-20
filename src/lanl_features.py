#!/usr/bin/env python3
"""LANL behavioral feature template — the single source of truth.

One parametrized SQL template computes the LANL per-event features for any
event set: offline training (over auth_slice / feat.parquet) and live scoring
(over the user's stored events) use the exact same code, so features can
never drift between training and the live demo.

`lanl_feature_sql(src)` takes a table expression returning columns:
  time (INTEGER seconds), src_user, dst_user, src_computer, dst_computer,
  auth_type, logon_type, orientation, result
and returns SQL producing those columns plus:

  hour             float hour-of-day in [0, 24)          -> hour_sin/hour_cos
  dst_first        first visit to this destination (1/0)
  src_first        first time from this source computer (1/0)
  hour_events      events of this user at this hour
  user_events      total events of this user
  dst_prior_events prior visits to this destination
  fail_1h          failures by this user in the preceding 3600 s
  vel_1h           events by this user in the preceding 3600 s

The arithmetic matches src/lanl_features.sql exactly (verified by
src/test_lanl_features.py). `hour_ratio` (hour_events/user_events) and
`hour_sin`/`hour_cos` are derived in Python from the template's output —
they are not stored columns.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "raw" / "lanl" / "lanl.duckdb"
DEFAULT_FEATURES = ROOT / "data" / "raw" / "lanl" / "feat.parquet"

FEATURE_COLS = [
    "dst_first", "src_first", "hour_ratio", "dst_prior_events",
    "fail_1h", "vel_1h", "hour_sin", "hour_cos",
]


def lanl_feature_sql(src: str) -> str:
    """Feature SQL for any event source; identical offline and live."""
    return f"""
    WITH base AS (
        SELECT *,
               (time % 86400) / 3600 AS hour
        FROM ({src})
    )
    SELECT
        b.*,
        CASE WHEN min(b.time) OVER (PARTITION BY b.src_user, b.dst_computer) = b.time
             THEN 1 ELSE 0 END AS dst_first,
        CASE WHEN min(b.time) OVER (PARTITION BY b.src_user, b.src_computer) = b.time
             THEN 1 ELSE 0 END AS src_first,
        count(*) OVER (PARTITION BY b.src_user, b.hour) AS hour_events,
        count(*) OVER (PARTITION BY b.src_user) AS user_events,
        count(*) OVER (PARTITION BY b.src_user, b.dst_computer
                       ORDER BY b.time
                       RANGE BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
            AS dst_prior_events,
        coalesce(sum(CASE WHEN b.result = 'Fail' THEN 1 ELSE 0 END)
                 OVER (PARTITION BY b.src_user
                       ORDER BY b.time
                       RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING), 0)
            AS fail_1h,
        count(*) OVER (PARTITION BY b.src_user
                       ORDER BY b.time
                       RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING)
            AS vel_1h
    FROM base b
    """