# Identity Anomaly Detection System

**This system catches hackers logging into accounts they shouldn't have access to.**

Trained on 600K+ authentication events from 6 sources. Runs live. Flags intruders in real time.

---

## How It Works (3 steps)

```
  RAW LOGS              FEATURES             MODEL              DASHBOARD
┌──────────┐      ┌──────────────┐     ┌───────────┐     ┌──────────────┐
│ SSH logs │      │ fail_1h      │     │ Isolation │     │              │
│ AWS logs │ ───► │ vel_1h       │ ──► │ Forest  + │ ──► │ Flask Web UI │
│ MySQL    │      │ fail_24h     │     │ LightGBM  │     │ Live scoring │
│ Windows  │      │ ... 9 total  │     │ Ensemble  │     │ Risk levels  │
│ Web auth │      └──────────────┘     └───────────┘     └──────────────┘
│ Entra ID │
└──────────┘
```

1. **Parse** — raw auth logs from 6 sources get normalized into one schema
2. **Features** — 9 behavioral features extracted per event (failure rates, velocity, temporal patterns)
3. **Score** — IF + LightGBM ensemble classifies each event as Critical / High / Medium / Low

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/urvashiritu/MAJOR-PAIN-ATE-
cd MAJOR-PAIN-ATE-

# 2. Install deps
pip install flask joblib numpy pandas scikit-learn lightgbm duckdb pyarrow

# 3. Run
python3 app.py
```

Open `http://localhost:5001` — that's it.

---

## What's Under the Hood

| Component | What | Why |
|---|---|---|
| **DuckDB** | 600K event database | Fast SQL on local files, no server needed |
| **Isolation Forest** | Anomaly detector | Finds outliers without needing labeled attacks |
| **LightGBM** | Gradient boosting classifier | Learns attack patterns from labeled data |
| **Ensemble** | 50% IF + 50% LGB | Combines unsupervised + supervised signals |
| **Flask** | Web server + API | Serves the dashboard + REST endpoints |
| **Chart.js** | Dashboard charts | Doughnut charts for source distribution + success/failure |

---

## The Dataset

603,291 authentication events from 6 sources:

| Source | Events | What It Is |
|---|---|---|
| SSH | 100,569 | Linux login attempts |
| AWS CloudTrail | 100,944 | Console login events |
| Windows Security | 100,260 | Kerberos/NTLM/Negotiate auth |
| MySQL Audit | 100,262 | Database login logs |
| Web Auth | 100,188 | Application authentication |
| Entra ID | 100,916 | Azure/M365 sign-in logs |

**10 attack IPs** embedded in the data:
- 5 obvious brute-forcers (400+ failures/day) — `185.220.101.17`, `45.155.205.233`, etc.
- 5 stealthy attackers (low failure volume, harder to detect) — `10.20.99.101` through `10.20.99.105`

---

## Live Demo (Multi-Laptop)

```
┌─────────────┐    SSH attempts    ┌─────────────────┐
│  Laptop B   │ ─────────────────► │  Laptop A       │
│  (attacker) │    UDP syslog      │  Flask server   │
│             │    port 1514       │  Dashboard :5001│
└─────────────┘                    └─────────────────┘
```

1. Start the SSH listener from the dashboard (click "Start")
2. From another machine, run: `ssh fakeuser@<LAPTOP_A_IP>`
3. Watch events appear live with risk scores

The model needs ~10-15 failed attempts from a new IP before classifying it as an attack (cold-start behavior — this is realistic, not a bug).

---

## Model Performance

| Metric | Value | What It Means |
|---|---|---|
| ROC-AUC | 0.9999 | Near-perfect separation of attack vs normal |
| F1 Score | 0.9992 | Balanced precision + recall |
| PR-AUC | 0.9997 | Excellent even with 8.2% attack rate |
| Baseline (threshold) | 0.6324 | Model adds massive lift over simple counting |

**Honest caveat:** The 5 original attack IPs are extremely aggressive (hundreds of failures/day). The model is genuinely good, but part of the high score is because brute-force is inherently detectable via failure counts. Stealthy attacks with low volume are harder.

---

## Project Structure

```
.
├── app.py                     # Flask server + SSH listener + API
├── templates/
│   └── dashboard.html         # Web dashboard (Chart.js)
├── src/
│   ├── 01_parse_all.py        # DuckDB ingestion for all 6 sources
│   ├── 02_build_features.py   # 9 feature engineering pipeline
│   ├── 03_train_models.py     # IF + LGB training with honest evaluation
│   ├── generate_stealthy_attacks.py  # Synthetic stealthy attack generator
│   └── xml_to_json.py         # Windows XML → JSONL converter
├── data/
│   ├── auth.duckdb            # 603K events database
│   └── stealthy_attacks.jsonl # 3,139 stealthy attack events
├── models/
│   ├── multi_if.joblib        # Trained Isolation Forest
│   ├── multi_lgb.joblib       # Trained LightGBM
│   └── multi_meta.joblib      # Model metadata + thresholds
├── outputs/
│   └── features_lanl.parquet  # 603K rows × 9 features
└── scripts/
    └── oclog.sh               # Session logging script
```

---

## Features (what the model looks at)

| Feature | What It Measures | Why It Matters |
|---|---|---|
| `fail_1h` | Failed logins from this IP in last hour | Primary brute-force signal |
| `vel_1h` | Total events from this IP in last hour | Traffic volume spike detection |
| `fail_24h` | Failed logins from this IP in last 24 hours | Slow-drip attack detection |
| `vel_24h` | Total events from this IP in last 24 hours | Sustained activity tracking |
| `user_fail_rate` | Historical failure rate for this user | Compromised credential signal |
| `src_ip_fail_rate` | Historical failure rate for this IP | Known bad actor signal |
| `hour_ratio` | Time of day (normalized 0-1) | Night attacks are suspicious |
| `hour_sin` / `hour_cos` | Cyclical time encoding | Preserves 23:00 is close to 00:00 |

---

## Risk Levels

| Level | Score Range | What Happens |
|---|---|---|
| Critical | >= 0.75 | Almost certainly an attack |
| High | >= 0.50 | Strong attack indicators |
| Medium | >= threshold | Suspicious, needs investigation |
| Low | < threshold | Normal behavior |
