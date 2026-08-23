# AI-Based Identity Anomaly Detection System

**Team:** Hemanth Kumar KS (1SK23CS020) | Urvashi Tanwar (1SK23CS055) | Veenashree S T (1SK23CS057) | Vishwanath Sanapur (1SK23CS059)
**Guide:** Dr. Anitha A C -- Government Sri Krishnarajendra Silver Jubilee Technological Institute, CSE

---

## What this project does

Every time someone logs in, the system asks: "Is this how this user normally behaves?"

A normal login (usual time, usual machine, familiar destination) gets allowed. A strange
login (new machine, unfamiliar destination, unusual hour, repeated failures) gets flagged
or blocked, with an explanation of why.

The system is trained on the **LANL Cyber1 dataset** -- real network authentication
logs from Los Alamos National Laboratory with red-team ground truth. During the live
demo, login events are scored in real time and appear on a dashboard as allowed (green),
flagged (yellow), or blocked (red), with the reasoning shown for every decision.

---

## Why this approach (and what we tried before)

We went through three earlier paths before arriving here. Each one taught us something
useful about why ML fails or succeeds on different datasets.

### Path 1: RBA + 4-model ensemble (F1 0.11)

We trained Isolation Forest, LOF, OCSVM, and Elliptic Envelope on the RBA dataset
(31M login events from a Norwegian ISP). The best model (trimmed ensemble) scored
F1 0.11 on the "gold label" (successful login from a blocked IP).

The problem was the label itself. RBA's attack label is an IP blocklist -- a static
list of bad IPs. The same IP always gets the same label. A model that studies behavior
can never learn to predict a list. A simple IP lookup (no ML needed) scored 0.75 F1,
beating every model by a wide margin. ML was the wrong tool for a blocklist problem.

### Path 2: RBA + XGBoost (same result, different model)

We tried XGBoost on the same RBA data. Same label, same problem. The model learned
some behavioral patterns but still couldn't beat the blocklist shortcut. Changing
the model doesn't fix a broken label.

### Path 3: LANL + 4-model ensemble (ROC-AUC 0.99, but impractical)

We moved to the LANL Cyber1 dataset (1B auth events from a national lab) and
trained the same 4-model ensemble. Isolation Forest hit ROC-AUC 0.99 on the test
set. But the 4-model approach had problems:

- Elliptic Envelope caught only 1 true positive out of 4 red-team events
- LOF took 910 seconds to fit on 7M rows
- Combining 4 models added complexity without proportional benefit
- The ensemble scores were hard to interpret in the demo

### Path 4 (current): LANL + IF + habit deviation (ROC-AUC 0.92 combined)

The current approach uses a single Isolation Forest model plus a simple habit
deviation layer. Here's why it works better:

**1. No shortcut possible.** LANL's auth data has no IPs, no geolocation, no
device IDs, no browser signatures. The only signal is behavior. This is why ML
can win here when it couldn't on RBA.

**2. Per-user baseline.** The habit deviation compares each event to the user's
own history, not a global average. "Alice has never visited C9999 before" is a
stronger signal than "most users don't visit C9999."

**3. 8 features, not 21.** We use dst_first, src_first, hour_ratio,
dst_prior_events, fail_1h, vel_1h, hour_sin, hour_cos. Each one maps to a
concrete behavioral question: "Is this destination new? Is this source new?
Is this hour unusual? How many times has the user been here before?"

**4. Interpretable decisions.** The scoring formula is:
`if_score + 0.10 * min(dev_points, 3)`. The habit deviation adds at most
0.3 points, acting as a tiebreaker. The IF model does the heavy lifting;
the deviation layer adds per-user context.

**5. Fast enough for real time.** IF scores one event in ~1.58 microseconds
on the demo scale. The habit deviation query runs in milliseconds against
DuckDB. The combined path is well under 1ms per event.

### Results comparison

| Approach | Dataset | Best model | F1 | ROC-AUC | Notes |
|----------|---------|-----------|-----|---------|-------|
| RBA + 4 ensemble | RBA (31M) | ensemble_trimmed | 0.111 | 0.536 | IP blocklist label; ML can't beat lookup |
| RBA + XGBoost | RBA (31M) | XGBoost | 0.111 | 0.536 | Same label, same problem |
| LANL + 4 ensemble | LANL (7M train) | isolation_forest | 0.0005 | 0.994 | High ROC-AUC but impractical ensemble |
| LANL + IF + habit | LANL (demo) | combined | -- | 0.916 | 8 features, interpretable, real-time |

The LANL + IF + habit approach trades a small amount of ROC-AUC (0.92 vs 0.99)
for practical benefits: fewer features, interpretable decisions, per-user context,
and a scoring path fast enough for live demo use.

---

## Architecture

```
data/raw/lanl/slice.parquet     LANL Cyber1 authentication logs
         |
    seed_demo.py                Seeds 4 users + history into DuckDB
         |
    data/live.duckdb            Live demo database
         |
    app.py (Flask)              Backend: scoring, API, SSE
    scoring.py                  IF + habit deviation scoring
    db.py                       DuckDB storage, profiles
         |
    live/web/ (React + Vite)    Dashboard SPA
    templates/login.html        Login page (generates test events)
```

Backend: Flask on port 5000
Frontend: React + Vite, proxied through Flask
Database: DuckDB
Models: Isolation Forest + LightGBM (pretrained, stored in `models/`)

---

## How to run

### Prerequisites

- Python 3.10+ with venv set up at `../venv/`
- Node.js 18+ with npm

### 1. Seed the database

```bash
venv/bin/python live/seed_demo.py
```

This reads `data/raw/lanl/slice.parquet` and creates `data/live.duckdb` with
4 user profiles and their login history.

### 2. Start the backend

```bash
venv/bin/python live/app.py
```

The server starts on `http://0.0.0.0:5000`. Models are loaded at startup --
you should see "MODELS LOADED" in the health endpoint.

### 3. Start the frontend (for dashboard)

```bash
cd live/web
npm install
npm run dev
```

The dev server starts on `http://localhost:5173/dashboard/`. In production,
build with `npm run build` and Flask serves the static files.

### 4. Open the login page

Open `http://<backend-ip>:5000` on a second laptop or phone. Pick a scenario,
fill in the form, and submit. The event is scored and appears on the dashboard.

---

## Login scenarios

The login page has 5 preset scenarios to test different detection cases:

| Scenario | What happens | Expected result |
|----------|-------------|-----------------|
| Normal | Alice logs in from her usual machine (C17788) to a familiar destination (C612) | ALLOW |
| Wrong Pass | Alice enters wrong password, then corrects it | ALLOW (single failure is normal) |
| New Dest | Alice logs in to a destination she has never visited before (C9999) | BLOCK (0.796) |
| Attacker | Attacker (C151) tries to log in -- has 17k+ suspicious history events | ALLOW (single attempt); FLAG or BLOCK with rapid-fire attempts |
| Late Night | Alice logs in at 3am | ALLOW (time alone is not enough) |

---

## How scoring works

Each event is scored by combining two signals:

1. **Isolation Forest anomaly score** -- a machine learning model that learned what
   "normal" looks like across 8 features (new destination, new source, hour patterns,
   prior visits, failure rate, velocity)

2. **Habit deviation points** -- simple rules that compare this event to the user's
   stored history:
   - First-ever destination: +1 point
   - First-ever source: +1 point
   - Repeated auth failures: +1 point

The combined score is: `if_score + 0.10 * min(dev_points, 3)`

Decision thresholds:
- Combined >= 0.75: BLOCK
- Combined >= 0.65: FLAG
- Below 0.65: ALLOW

LightGBM is also loaded and its score is displayed for transparency, but it is not
part of the decision -- it was trained on full-scale data and saturates at 1.0 on
demo-scale histories.

---

## Features (8)

| Feature | Type | What it measures |
|---------|------|-----------------|
| dst_first | binary | Is this the first event to this destination? |
| src_first | binary | Is this the first event from this source? |
| hour_ratio | float | Fraction of events at this hour vs total |
| dst_prior_events | int | How many times has this user visited this destination? |
| fail_1h | float | Auth failures in the last hour |
| vel_1h | int | Events in the last hour |
| hour_sin | float | Sine of hour (captures cyclical time) |
| hour_cos | float | Cosine of hour (captures cyclical time) |

---

## Seeded users

| User | User ID | Default Source | History Events |
|------|---------|---------------|----------------|
| alice | 1 | C17788 | ~99 |
| bob | 2 | C21468 | ~39 |
| carol | 3 | C18941 | ~42 |
| attacker | -1 | C151 | ~17,000 |

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /events | Score a single event |
| GET | /events/stream | SSE stream of scored events |
| GET | /api/dashboard | KPIs, recent events, alerts |
| GET | /api/investigation/<id> | Feature breakdown + timeline |
| GET | /api/users/<id>/profile | Baseline + distributions |
| GET | /api/users | All users + stats |
| GET | /api/alerts | Recent alerts |
| POST | /api/alerts/<id>/ack | Acknowledge alert |
| GET | /api/health | System status (models loaded, uptime) |
| POST | /api/reset | Reset demo to initial state |

---

## Project structure

```
lanl-anomaly/
  data/
    raw/lanl/slice.parquet     Source dataset
    live.duckdb                 Demo database
  models/
    lanl_if.joblib              Isolation Forest model
    lanl_lgb.joblib             LightGBM model
    lanl_ensemble.joblib        Ensemble model
  src/
    00_clean_dataset.py         Dataset cleaning
    01_load_and_sample.py       Sampling
    02_feature_engineering.py   Feature SQL
    02_retrain_both.py          Retrain IF + LGB
    02_retrain_if.py            Retrain IF only
    03_validate_contract.py     Validation
    04_rule_baseline.py         Rule engine
    07_ensemble_full.py         Ensemble evaluation
  live/
    app.py                      Flask backend
    scoring.py                  Scoring logic
    db.py                       Database layer
    seed_demo.py                Database seeder
    templates/login.html        Login page
    web/                        React dashboard
  reports/                      Evaluation reports
  legacy/                       Old RBA code (preserved)
```

---

## Experimental results

### LANL feature separation (702 red-team events)

The behavioral signals are real. Here's how each feature alone separates red-team
events from normal activity:

| Feature | Red vs user's own normal | Red vs normal users | What it means |
|---------|-------------------------|---------------------|---------------|
| dst_first | 0.650 | 0.649 | Red hits new destinations |
| src_first | 0.552 | 0.552 | Red uses new sources |
| hour_ratio | 0.712 | 0.352 | Red works at odd hours (per-user: 0.71) |
| dst_prior_events (inverted) | 0.970 | 0.905 | Red visits unfamiliar targets |
| fail_1h | 0.657 | 0.665 | Red coincides with failure bursts |
| vel_1h (inverted) | 0.810 | 0.586 | Red follows different activity patterns |

"Per-user" means vs the compromised user's own baseline (A vs B). This is the
UEBA framing: "is THIS user acting normally?" not "is this a bad user?"

### Model performance on LANL

| Model | ROC-AUC | F1 | Recall | FPR | Train time |
|-------|---------|-----|--------|-----|------------|
| Isolation Forest | 0.994 | 0.0005 | 0.75 | 0.004 | 13s |
| Elliptic Envelope | 1.000 | 0.333 | 0.25 | 0.000 | 245s |
| LOF | 0.814 | 0.003 | 0.25 | 0.000 | 911s |
| Combined (IF + habit) | 0.916 | 0.009 | 0.01 | 0.000 | -- |

Note: F1 is low because of extreme class imbalance (4 red events in 3M test rows).
ROC-AUC is the more meaningful metric here. The combined score trades peak ROC-AUC
for interpretable, per-user decisions.

### Demo scoring measurements (5 scenarios x 3 runs each)

| Scenario | n | p50 score | ALLOW | FLAG | BLOCK |
|----------|---|-----------|-------|------|-------|
| Normal (alice, familiar) | 15 | 0.48 | 15 | 0 | 0 |
| Wrong pass (single failure) | 15 | 0.58 | 3 | 12 | 0 |
| Burst (rapid-fire attacks) | 5 | 0.62 | 2 | 2 | 1 |
| Burst warmup (first attempts) | 5 | 0.54 | 4 | 1 | 0 |
| Replay (repeated patterns) | 15 | 0.58 | 3 | 12 | 0 |

The system correctly allows normal logins, flags suspicious patterns, and blocks
sustained attack bursts. Single failures and early attempts stay below the flag
threshold, reducing false alarms.

---

## Known limitations

- The Late Night scenario is cosmetic only. The timestamp is anchored to the
  seed data, so "3am" does not change the score without modifying the form
  to spoof the hour in the POST payload.
- LightGBM is displayed but not used for decisions. It was trained on
  full-scale data (~52k events per destination) and scores everything as
  anomalous on demo-scale histories.
- This is a single-dataset study on LANL Cyber1. Transfer to other networks
  is future work.

---

## References

- LANL Cyber1 dataset: `data/raw/lanl/slice.parquet`
- Original RBA dataset (preserved in `legacy/`): Zenodo 6782156
- Isolation Forest: Liu et al., 2008
- LightGBM: Ke et al., 2017
