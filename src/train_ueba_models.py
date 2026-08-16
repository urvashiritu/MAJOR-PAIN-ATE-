"""Train scalable UEBA anomaly models and write dashboard-ready results.

The source has 31M events.  Models are fit on a reproducible normal-event
baseline because robust covariance methods cannot fit all rows in laptop RAM.
All source events are still counted and reported in the dashboard.
"""
import json
from glob import glob
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.covariance import EllipticEnvelope
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.preprocessing import RobustScaler

DATA = "rba_dataset/processed/ueba_model_training_events/*.parquet"
OUT = Path("rba_dataset/models")
OUT.mkdir(parents=True, exist_ok=True)
FEATURES = [
    "login_hour_sin", "login_hour_cos", "weekday", "is_weekend", "night_login",
    "is_first_login", "time_gap_missing", "time_since_last_login_log1p",
    "failed_before_success_log1p", "country_change", "device_change", "new_browser",
    "new_os", "browser_os_mismatch", "is_bot_browser", "device_missing",
    "is_private_ip", "is_synthetic_asn",
]

files = sorted(glob(DATA))
if len(files) != 13:
    raise RuntimeError(f"Expected 13 monthly Parquet files; found {len(files)}. Build the complete dataset first.")
source = "read_parquet([" + ",".join(repr(file) for file in files) + "])"
con = duckdb.connect()

summary = con.execute(f"""
    SELECT count(*) AS total_events, count(distinct user_id) AS unique_users,
           min(event_timestamp) AS first_event, max(event_timestamp) AS last_event,
           sum(eval_is_attack_ip) AS attack_ip_events,
           sum(eval_is_account_takeover) AS ato_events
    FROM {source}
""").df().iloc[0].to_dict()

# Chronological split: baseline only sees early legitimate behaviour.
fit = con.execute(f"""
    SELECT * FROM (
        SELECT * FROM {source}
        WHERE event_timestamp < TIMESTAMP '2020-11-01'
          AND eval_is_attack_ip = 0 AND eval_is_account_takeover = 0
    ) USING SAMPLE reservoir(40000 ROWS) REPEATABLE (42)
""").df()
test = con.execute(f"""
    SELECT * FROM (
        SELECT * FROM {source}
        WHERE event_timestamp >= TIMESTAMP '2020-11-01'
    ) USING SAMPLE reservoir(100000 ROWS) REPEATABLE (42)
""").df()
con.close()

scaler = RobustScaler().fit(fit[FEATURES])
x_fit, x_test = scaler.transform(fit[FEATURES]), scaler.transform(test[FEATURES])
models = {
    "Isolation Forest": (
        IsolationForest(n_estimators=400, max_samples=256, contamination=0.01, random_state=42, n_jobs=-1),
        "Recommended operational model: scalable, robust to non-linear behaviours, and efficient for real-time scoring.",
    ),
    "Elliptic Envelope": (
        EllipticEnvelope(contamination=0.01, random_state=42, support_fraction=0.8),
        "Statistical benchmark: works best when normal activity has an approximately elliptical distribution.",
    ),
}

y = test.eval_is_attack_ip.astype(int).to_numpy()
results, scores = [], {}
for name, (model, explanation) in models.items():
    model.fit(x_fit)
    score = -model.decision_function(x_test)  # higher = more anomalous
    scores[name] = score
    threshold = float(np.quantile(score, 0.99))
    precision, recall, _ = precision_recall_curve(y, score)
    results.append({
        "model": name,
        "fit_rows": len(fit), "test_rows": len(test),
        "attack_ip_roc_auc": round(float(roc_auc_score(y, score)), 4),
        "attack_ip_avg_precision": round(float(average_precision_score(y, score)), 4),
        "precision_at_1pct_alerts": round(float(y[score >= threshold].mean()), 4),
        "alert_rate": round(float((score >= threshold).mean()), 4),
        "why": explanation,
        "pr_curve": {"precision": precision[::max(1, len(precision)//200)].round(5).tolist(),
                     "recall": recall[::max(1, len(recall)//200)].round(5).tolist()},
    })

# Average precision is the appropriate ranking metric for rare attack events.
best = max(results, key=lambda result: result["attack_ip_avg_precision"])
best_name = best["model"]
alerts = test[["event_timestamp", "user_id", "eval_is_attack_ip", "eval_is_account_takeover"]].copy()
alerts["anomaly_score"] = scores[best_name]
alerts["risk_level"] = pd.cut(alerts["anomaly_score"],
                                bins=[-np.inf, np.quantile(scores[best_name], .90), np.quantile(scores[best_name], .99), np.inf],
                                labels=["Low", "Medium", "High"])
alerts.nlargest(250, "anomaly_score").to_csv(OUT / "top_anomalous_events.csv", index=False)

# Transparent, model-agnostic explanation: robust deviation from normal baseline.
median = fit[FEATURES].median()
mad = (fit[FEATURES] - median).abs().median().replace(0, 1e-6)
feature_impact = ((test[FEATURES] - median).abs() / mad).mean().sort_values(ascending=False)

payload = {
    "dataset": DATA, "dataset_summary": summary, "features": FEATURES,
    "results": results, "best_model": best_name,
    "selection_metric": "Attack-IP average precision", "feature_impact": feature_impact.round(3).to_dict(),
    "explanation_method": "Robust baseline deviation. Higher-impact features are those that differ most from normal training behaviour; this method is model-agnostic and is consistent across both models.",
    "method_note": "The full cleaned dataset is 31M events. Fit/test rows are representative, chronological samples required because Elliptic Envelope cannot be trained on every event in typical laptop memory.",
}
(OUT / "ueba_model_results.json").write_text(json.dumps(payload, indent=2, default=str))
print(json.dumps(payload, indent=2, default=str))
