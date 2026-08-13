#!/usr/bin/env python3
"""Logs-Lab explainable UI — a standalone, self-contained page.

Shows, in plain English, what the logs-lab synthetic experiment did:
  - what the dataset is (6 auth-log sources parsed into one table)
  - how we split it into train / validation / test
  - how the 3 models compare
  - WHY the model scored a specific login the way it did (perturbation
    explanation: re-score the event with each feature set to its baseline
    value, so the score change = that feature's contribution)
  - a side-by-side comparison with the main RBA model

Run:  venv/bin/python logs-lab/ui/app.py   (http://127.0.0.1:5001)
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, send_from_directory

ROOT = Path(__file__).resolve().parent
LABS = ROOT.parent
PROJECT = LABS.parent

FEATURED = LABS / "featured_events.parquet"
MODEL = LABS / "models" / "best_model.joblib"
EVAL = LABS / "reports" / "evaluation.json"
RBA_EVAL = PROJECT / "reports" / "supervised_evaluation.json"

app = Flask(__name__)

# Friendly feature labels for the explanation panel.
FEATURE_LABELS = {
    "hour": ("Hour of day", "numeric"),
    "day_of_week": ("Day of week", "numeric"),
    "rapid_login_rate_10m": ("Logins in last 10 min", "numeric"),
    "login_frequency_today": ("Logins today so far", "numeric"),
    "prior_failure_rate": ("Share of past logins that failed", "numeric"),
    "minutes_since_prev": ("Minutes since previous login", "numeric"),
    "is_night": ("Night login (10pm-6am)", "bool"),
    "is_weekend": ("Weekend login", "bool"),
    "country_missing": ("No country recorded", "bool"),
    "device_missing": ("No device recorded", "bool"),
    "os_missing": ("No OS recorded", "bool"),
    "browser_missing": ("No browser recorded", "bool"),
    "ip_missing": ("No IP recorded", "bool"),
    "country_change": ("Country changed vs previous login", "bool"),
    "device_change": ("Device changed vs previous", "bool"),
    "os_change": ("OS changed vs previous", "bool"),
    "browser_change": ("Browser changed vs previous", "bool"),
    "source_change": ("Different system vs previous", "bool"),
    "failed_recently_30m": ("A login failed in last 30 min", "bool"),
    "ip_seen_before": ("This IP seen for this user before", "bool"),
    "country_seen_before": ("This country seen before", "bool"),
    "device_seen_before": ("This device seen before", "bool"),
    "os_seen_before": ("This OS seen before", "bool"),
    "browser_seen_before": ("This browser seen before", "bool"),
    "source_seen_before": ("This system seen before", "bool"),
    "source": ("System (AWS/Entra/...)", "cat"),
    "country": ("Country", "cat"),
    "device": ("Device type", "cat"),
    "os": ("Operating system", "cat"),
    "browser": ("Browser", "cat"),
}

_model = None
_baselines: dict | None = None
_split: pd.DataFrame | None = None
_cached_events: list[dict] = []


def load_model():
    global _model
    if _model is None:
        _model = joblib.load(MODEL)
    return _model


def compute_split() -> pd.DataFrame:
    """Recompute the per-user chronological train/val/test split (same rule
    as train_models.py) so the UI's numbers always match the artifacts."""
    global _split
    if _split is not None:
        return _split
    con = duckdb.connect(":memory:")
    con.execute("SET threads=2")
    _split = con.execute(f"""
        WITH ev AS (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY ts, row_id) AS rn,
                   COUNT(*) OVER (PARTITION BY user_id) AS n_events
            FROM read_parquet('{FEATURED}')
        )
        SELECT row_id,
               CASE
                   WHEN rn <= CEIL(0.55 * n_events) THEN 'train'
                   WHEN rn <= CEIL(0.70 * n_events) THEN 'val'
                   ELSE 'test'
               END AS split
        FROM ev
    """).df()
    return _split


def compute_baselines() -> dict:
    """'Typical' value per feature, from the TRAIN split only, used as the
    neutral reference in the explanation (never from test)."""
    global _baselines
    if _baselines is not None:
        return _baselines
    art = load_model()
    features = art["features"]
    split = compute_split()
    con = duckdb.connect(":memory:")
    con.execute("SET threads=2")
    feat = con.execute(f"""
        SELECT * FROM read_parquet('{FEATURED}')
    """).df()
    train = feat.merge(split, on="row_id", how="inner")
    train = train[train["split"] == "train"]

    out: dict = {}
    for f in features:
        kind = FEATURE_LABELS.get(f, (f, "numeric"))[1]
        if kind == "numeric":
            out[f] = float(train[f].median())
        elif kind == "bool":
            out[f] = bool(train[f].mode().iloc[0])
        else:
            out[f] = str(train[f].mode().iloc[0])
    _baselines = out
    return out


def _jsonable(v):
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v


def _sample_events(n: int = 30, seed: int = 7) -> list[dict]:
    """Deterministic sample of TEST events with their model score."""
    global _cached_events
    if _cached_events:
        return _cached_events[:n]

    art = load_model()
    features = art["features"]
    threshold = float(art["threshold"])
    split = compute_split()
    con = duckdb.connect(":memory:")
    con.execute("SET threads=2")
    feat = con.execute(f"SELECT * FROM read_parquet('{FEATURED}')").df()
    test = feat.merge(split, on="row_id", how="inner")
    test = test[test["split"] == "test"].reset_index(drop=True)

    rng = random.Random(seed)
    idx = rng.sample(range(len(test)), min(n * 3, len(test)))

    X = test.iloc[idx][features]
    probs = art["pipeline"].predict_proba(X)[:, 1]

    events = []
    for pos, i in enumerate(idx):
        row = test.iloc[i]
        p = float(probs[pos])
        events.append({
            "row_id": int(row["row_id"]),
            "user_id": str(row["user_id"]),
            "source": str(row["source"]),
            "country": str(row["country"]),
            "device": str(row["device"]),
            "os": str(row["os"]),
            "browser": str(row["browser"]),
            "hour": int(row["hour"]),
            "success": bool(row["success"]),
            "score": round(p, 4),
            "threshold": round(threshold, 4),
            "decision": "Suspicious" if p >= threshold else "Normal",
            "truth": "Failed" if not row["success"] else "Success",
        })
    events.sort(key=lambda e: e["score"], reverse=True)
    _cached_events = events
    return events[:n]


def explain_event(row_id: int) -> dict | None:
    art = load_model()
    features = art["features"]
    baselines = compute_baselines()
    split = compute_split()
    con = duckdb.connect(":memory:")
    feat = con.execute(f"SELECT * FROM read_parquet('{FEATURED}')").df()
    ev = feat[feat["row_id"] == row_id]
    if ev.empty:
        return None
    row = ev.iloc[0]
    sp = split[split["row_id"] == row_id]["split"].iloc[0]

    X = row[features].to_frame().T
    base = float(art["pipeline"].predict_proba(X)[:, 1][0])

    contribs = []
    for f in features:
        Xv = X.copy()
        Xv[f] = baselines[f]
        s = float(art["pipeline"].predict_proba(Xv)[:, 1][0])
        contribs.append({"feature": f, "label": FEATURE_LABELS.get(f, (f, "?"))[0],
                         "value": base - s})
    contribs.sort(key=lambda c: abs(c["value"]), reverse=True)

    return {
        "row_id": int(row["row_id"]),
        "split": sp,
        "user_id": str(row["user_id"]),
        "source": str(row["source"]),
        "country": str(row["country"]),
        "device": str(row["device"]),
        "os": str(row["os"]),
        "browser": str(row["browser"]),
        "success": bool(row["success"]),
        "score": round(base, 4),
        "threshold": round(float(art["threshold"]), 4),
        "decision": "Suspicious" if base >= float(art["threshold"]) else "Normal",
        "contributions": contribs,
    }


@app.route("/")
def index():
    return send_from_directory(ROOT / "templates", "explain.html")


@app.route("/api/overview")
def api_overview():
    con = duckdb.connect(":memory:")
    con.execute("SET threads=2")
    total = con.execute(f"SELECT COUNT(*) FROM read_parquet('{FEATURED}')").fetchone()[0]
    by_source = con.execute(f"""
        SELECT source, COUNT(*) n, SUM(success::int) ok
        FROM read_parquet('{FEATURED}')
        GROUP BY 1 ORDER BY 2 DESC
    """).fetchdf()

    split = compute_split()
    split_counts = split["split"].value_counts().to_dict()
    eval_data = json.load(open(EVAL))

    rba = {}
    if RBA_EVAL.exists():
        d = json.load(open(RBA_EVAL))
        rba = {
            "hgb_gold_f1": d.get("supervised_hgb", {}).get("gold", {}).get("f1"),
            "hgb_gold_roc": d.get("supervised_hgb", {}).get("roc_auc_gold"),
            "hgb_threshold": d.get("supervised_hgb", {}).get("tuned_threshold"),
            "train_rows": d.get("split", {}).get("train_rows"),
            "ip_blocklist_f1": None,
        }
        # ip_reputation_baseline lives in model_evaluation.json
        me = PROJECT / "reports" / "model_evaluation.json"
        if me.exists():
            m = json.load(open(me))
            ipr = m.get("ip_reputation_baseline", {}).get("gold", {}).get("f1")
            rba["ip_blocklist_f1"] = ipr

    return jsonify({
        "total": total,
        "users": int(con.execute(f"SELECT COUNT(DISTINCT user_id) FROM read_parquet('{FEATURED}')").fetchone()[0]),
        "sources": [{"name": r["source"], "events": int(r["n"]), "ok": int(r["ok"]),
                     "fail": int(r["n"] - r["ok"]),
                     "successRate": round(100 * int(r["ok"]) / int(r["n"]), 1)}
                    for _, r in by_source.iterrows()],
        "split": {k: int(v) for k, v in split_counts.items()},
        "trainRows": int(split_counts.get("train", 0)),
        "valRows": int(split_counts.get("val", 0)),
        "testRows": int(split_counts.get("test", 0)),
        "models": eval_data.get("models", []),
        "winner": eval_data.get("winner"),
        "rba": rba,
    })


@app.route("/api/events")
def api_events():
    n = min(50, max(5, int(__import__("flask").request.args.get("n", 20))))
    return jsonify({"events": _sample_events(n)})


@app.route("/api/explain/<int:row_id>")
def api_explain(row_id: int):
    ev = explain_event(row_id)
    if ev is None:
        return jsonify({"error": "event not found"}), 404
    return jsonify(ev)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)