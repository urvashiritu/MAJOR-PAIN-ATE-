#!/usr/bin/env python3
"""5-min timing probe for LANL training.

Samples N rows from feat.parquet, fits each of the 4 anomaly models on that
sample, times fit+score, and projects to 5M / 20.9M to decide A vs C.
No threshold tuning, no ensembles — pure timing.
"""
import argparse
import json
import math
import time
import warnings
from pathlib import Path

import duckdb
import numpy as np
from sklearn.covariance import EllipticEnvelope
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import SGDOneClassSVM
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEATURES = ROOT / "data" / "raw" / "lanl" / "feat.parquet"
SEED = 42


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    ap.add_argument("--sample", type=int, default=1_000_000, help="sample rows for timing")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    con = duckdb.connect(":memory:")
    con.execute("SET threads=8")
    # seeded random sample — ORDER BY random() is slow but fine for 1M; use reservoir via USING SAMPLE instead for speed
    # Use TABLESAMPLE for speed with seed, fallback to random() if needed
    t0 = time.time()
    print(f"sampling {args.sample:,} rows from {args.features} ...", flush=True)
    # DuckDB TABLESAMPLE is fast: 1M / 29.9M ≈ 3.34%
    pct = max(1, math.ceil(args.sample / 29_905_488 * 100))
    # Try Bernoulli sample then limit — seeded via random() with setseed if available
    try:
        df = con.execute(
            f"SELECT * FROM read_parquet('{args.features}') USING SAMPLE {pct}% (bernoulli, {args.seed}) LIMIT {args.sample}"
        ).df()
    except Exception:
        df = con.execute(
            f"SELECT * FROM read_parquet('{args.features}') ORDER BY random() LIMIT {args.sample}"
        ).df()
    # If Bernoulli gave slightly fewer, top up with random
    if len(df) < args.sample:
        need = args.sample - len(df)
        extra = con.execute(
            f"SELECT * FROM read_parquet('{args.features}') ORDER BY random() LIMIT {need}"
        ).df()
        df = df if len(df) == 0 else __import__("pandas").concat([df, extra], ignore_index=True)
    print(f"sampled {len(df):,} rows in {time.time()-t0:.1f}s (is_red={df['is_red'].sum()})", flush=True)

    # features
    df["hour_ratio"] = df["hour_events"] / df["user_events"].replace(0, 1)
    h = df["hour"].to_numpy() / 24.0 * 2 * np.pi
    df["hour_sin"] = np.sin(h)
    df["hour_cos"] = np.cos(h)
    FEATURE_COLS = ["dst_first", "src_first", "hour_ratio", "dst_prior_events", "fail_1h", "vel_1h", "hour_sin", "hour_cos"]
    X = df[FEATURE_COLS].to_numpy(dtype=np.float64)
    contamination = float(df["is_red"].mean())
    if contamination == 0:
        contamination = 0.0001
        print("warning: sample has 0 reds, using contamination=0.0001", flush=True)
    print(f"contamination (sample red rate) = {contamination:.6f}", flush=True)

    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)

    models = {
        "isolation_forest": IsolationForest(contamination=contamination, random_state=SEED, n_jobs=-1),
        "local_outlier_factor": LocalOutlierFactor(novelty=True, n_neighbors=35, contamination=contamination, n_jobs=-1),
        "one_class_svm": SGDOneClassSVM(nu=contamination, shuffle=True, tol=1e-4, random_state=SEED),
        "elliptic_envelope": EllipticEnvelope(contamination=contamination, random_state=SEED),
    }

    results = {}
    for name, est in models.items():
        t1 = time.time()
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore")
                est.fit(Xs)
            t_fit = time.time() - t1
            t2 = time.time()
            scores = -est.decision_function(Xs)
            t_score = time.time() - t2
            t_total = t_fit + t_score
            latency_us = t_score / len(Xs) * 1e6
            print(f"{name:<22} fit {t_fit:6.1f}s  score {t_score:5.1f}s  total {t_total:6.1f}s  latency {latency_us:.1f}us", flush=True)
            results[name] = {"fit_s": round(t_fit, 2), "score_s": round(t_score, 2), "total_s": round(t_total, 2), "latency_us": round(latency_us, 2), "status": "ok"}
        except Exception as exc:
            t_total = time.time() - t1
            print(f"{name:<22} FAILED after {t_total:.1f}s: {exc}", flush=True)
            results[name] = {"total_s": round(t_total, 2), "status": f"failed: {exc}"}

    # projections: linear for IF/SGD/EE, n log n for LOF
    n0 = len(Xs)
    for target in [5_000_000, 20_900_000]:
        for name, r in results.items():
            if r.get("status") != "ok":
                continue
            if name == "local_outlier_factor":
                # kd-tree ~ n log n
                factor = (target / n0) * (math.log(target) / math.log(n0))
            else:
                factor = target / n0
            proj = r["total_s"] * factor
            r[f"proj_{target//1_000_000}M_s"] = round(proj, 1)
            r[f"proj_{target//1_000_000}M_min"] = round(proj / 60, 1)

    total_1m = sum(r["total_s"] for r in results.values() if r.get("status") == "ok")
    proj_5m = sum(r.get("proj_5M_s", 0) for r in results.values() if r.get("status") == "ok")
    proj_20m = sum(r.get("proj_20M_s", 0) for r in results.values() if r.get("status") == "ok")
    print(f"\n1M total: {total_1m:.1f}s ({total_1m/60:.1f} min)", flush=True)
    print(f"proj 5M total: {proj_5m:.1f}s ({proj_5m/60:.1f} min)", flush=True)
    print(f"proj 20.9M total: {proj_20m:.1f}s ({proj_20m/60:.1f} min / {proj_20m/3600:.1f} hr)", flush=True)

    out = {
        "sample_rows": n0,
        "contamination": contamination,
        "per_model": results,
        "totals": {"1M_s": round(total_1m, 1), "proj_5M_s": round(proj_5m, 1), "proj_5M_min": round(proj_5m/60, 1), "proj_20M_s": round(proj_20m, 1), "proj_20M_min": round(proj_20m/60, 1), "proj_20M_hr": round(proj_20m/3600, 2)},
        "recommendation": "A1 (full 20.9M)" if proj_20m <= 7200 else ("C (5M)" if proj_5m <= 3600 else "A2 optimized or C 2M"),
    }
    out_path = ROOT / "reports" / "lanl_benchmark.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(f"wrote {out_path}", flush=True)
    print(f"recommendation: {out['recommendation']}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
