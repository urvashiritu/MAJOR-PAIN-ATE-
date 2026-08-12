#!/usr/bin/env python3
"""Phase 8.5 — one-time ML scoring of the whole 1M-row sample.

Runs the supervised HGB model (models/supervised_hgb.joblib) over
data/processed/features.parquet — the same 21 FEATURE_COLS the live
scoring path uses — and writes data/processed/sample_ml_scores.parquet
(row_id, ml_score). The dashboard's Dataset browser shows this score
next to the rule score for every row.

Idempotent: skips the predict pass when the cache parquet already exists.
"""
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live"))

from scoring import FEATURE_COLS, load_model  # noqa: E402

FEATURES = ROOT / "data" / "processed" / "features.parquet"
OUT = ROOT / "data" / "processed" / "sample_ml_scores.parquet"

CHUNK = 200_000


def main() -> None:
    if OUT.exists():
        print(f"exists: {OUT} — delete it to re-score")
        return

    model = load_model()
    pipe = model["model"]
    threshold = model["threshold"]

    print(f"scoring {FEATURES.name} with HGB (threshold {threshold:.3f}) ...")
    out_chunks = []
    con = duckdb.connect()
    total = 0
    for start in range(0, 1_000_000, CHUNK):
        df = con.execute(f"""
            SELECT row_id, hour, {", ".join(c for c in FEATURE_COLS if c not in ("hour_sin", "hour_cos"))}
            FROM read_parquet('{FEATURES}')
            ORDER BY row_id LIMIT {CHUNK} OFFSET {start}
        """).fetchdf()
        h = df["hour"] / 24.0 * 2 * np.pi
        df["hour_sin"] = np.sin(h)
        df["hour_cos"] = np.cos(h)
        X = df[FEATURE_COLS].to_numpy(dtype=float)
        prob = pipe.predict_proba(X)[:, 1]
        out_chunks.append(df[["row_id"]].assign(ml_score=prob))
        total += len(df)
        print(f"  {total:,} rows")

    merged = pd.concat(out_chunks, ignore_index=True)
    merge = duckdb.connect()
    merge.execute(f"""
        CREATE OR REPLACE TABLE ml AS
        SELECT s.row_id, m.ml_score
        FROM read_parquet('{ROOT}/data/processed/sample.parquet') s
        LEFT JOIN merged m USING (row_id)
    """)
    merge.execute(f"COPY ml TO '{OUT}' (FORMAT PARQUET)")
    n = merge.execute(f"SELECT COUNT(*) FROM read_parquet('{OUT}')").fetchone()[0]
    n_ml = merge.execute(f"""
        SELECT COUNT(*) FROM read_parquet('{OUT}') WHERE ml_score IS NOT NULL
    """).fetchone()[0]
    print(f"wrote {OUT}: {n:,} rows, {n_ml:,} with ml_score")


if __name__ == "__main__":
    main()