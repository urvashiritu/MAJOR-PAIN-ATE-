#!/usr/bin/env python3
"""LANL feature parity contract: template output must equal feat.parquet.

The training features (feat.parquet, produced by src/lanl_features.sql) and
the live-scoring features (src/lanl_features.lanl_feature_sql over the live
user's events) must be the same code. Every window partition is per-user, so
computing features for one user's events yields values identical to the
full-slice computation.

Checks:
  1. Golden case: U748@DOM1, t=155591, C17693 -> C332 must yield
     dst_first=1, src_first=0, dst_prior_events=0, fail_1h=0, vel_1h=148,
     hour ~ 19.2197  (and feat.parquet must store exactly that).
  2. Per-column diff of the template vs feat.parquet over every U748 event:
     0 mismatches in hour, dst_first, src_first, hour_events, user_events,
     dst_prior_events, fail_1h, vel_1h.

Usage: venv/bin/python src/test_lanl_features.py
"""
import sys

import duckdb

from lanl_features import DEFAULT_DB, DEFAULT_FEATURES, lanl_feature_sql

USER = "U748@DOM1"
GOLDEN_TIME = 155591
GOLDEN_DST = "C332"
GOLDEN = {"dst_first": 1, "src_first": 0, "dst_prior_events": 0,
          "fail_1h": 0.0, "vel_1h": 148, "hour": 19.2197}

COLS = ["hour", "dst_first", "src_first", "hour_events", "user_events",
        "dst_prior_events", "fail_1h", "vel_1h"]

KEY = ["time", "src_user", "dst_user", "src_computer", "dst_computer",
       "auth_type", "logon_type", "orientation", "result"]


def main() -> int:
    con = duckdb.connect(str(DEFAULT_DB), read_only=True)
    tpl = f"""
        WITH tpl AS (
            SELECT * FROM ({lanl_feature_sql(
                f"SELECT * FROM auth_slice WHERE src_user = '{USER}'")})
        )
        SELECT * FROM tpl
    """
    tpl_rows = int(con.execute(f"SELECT COUNT(*) FROM ({tpl})").fetchone()[0])
    feat_rows = int(con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{DEFAULT_FEATURES}') "
        f"WHERE src_user = '{USER}'").fetchone()[0])
    print(f"template rows (U748): {tpl_rows:,} | feat.parquet rows: {feat_rows:,}")

    failures = []
    if tpl_rows != feat_rows:
        failures.append(f"row count mismatch: template {tpl_rows} vs feat {feat_rows}")

    mismatches = con.execute(f"""
        WITH tpl AS (
            SELECT * FROM ({lanl_feature_sql(
                f"SELECT * FROM auth_slice WHERE src_user = '{USER}'")})
        )
        SELECT COUNT(*) AS n
        FROM tpl t
        JOIN read_parquet('{DEFAULT_FEATURES}') f
          ON {" AND ".join(f"t.{k} = f.{k}" for k in KEY)}
        WHERE {" OR ".join(
            f"t.{c} <> f.{c}" for c in
            ["hour", "dst_first", "src_first", "hour_events", "user_events",
             "dst_prior_events", "vel_1h"])}
           OR CAST(t.fail_1h AS DOUBLE) <> CAST(f.fail_1h AS DOUBLE)
    """).fetchone()[0]
    print(f"feature mismatches over all U748 events: {mismatches}")
    if mismatches:
        failures.append(f"{mismatches} feature mismatches vs feat.parquet")

    g = con.execute(f"""
        WITH tpl AS (
            SELECT * FROM ({lanl_feature_sql(
                f"SELECT * FROM auth_slice WHERE src_user = '{USER}'")})
        )
        SELECT hour, dst_first, src_first, dst_prior_events,
               CAST(fail_1h AS DOUBLE) AS fail_1h, vel_1h
        FROM tpl WHERE time = {GOLDEN_TIME} AND dst_computer = '{GOLDEN_DST}'
    """).fetchone()
    gcols = ["hour", "dst_first", "src_first", "dst_prior_events", "fail_1h", "vel_1h"]
    got = dict(zip(gcols, g))
    print(f"golden row t={GOLDEN_TIME} {USER} C17693 -> {GOLDEN_DST}: {got}")
    for c, want in GOLDEN.items():
        if c == "hour":
            ok = abs(got[c] - want) < 1e-3
        else:
            ok = got[c] == want
        if not ok:
            failures.append(f"golden {c}: got {got[c]} want {want}")

    f = con.execute(f"""
        SELECT hour, dst_first, src_first, dst_prior_events,
               CAST(fail_1h AS DOUBLE) AS fail_1h, vel_1h
        FROM read_parquet('{DEFAULT_FEATURES}')
        WHERE src_user = '{USER}' AND time = {GOLDEN_TIME}
          AND dst_computer = '{GOLDEN_DST}'
    """).fetchone()
    stored = dict(zip(gcols, f))
    print(f"stored feat.parquet golden row:            {stored}")
    if stored != got:
        failures.append(f"template != stored for golden row: {got} vs {stored}")

    if failures:
        for msg in failures:
            print(f"FAIL: {msg}")
        return 1
    print("PASS: template == feat.parquet (feature parity contract holds)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())