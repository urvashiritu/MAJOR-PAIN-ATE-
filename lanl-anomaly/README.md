# LANL Anomaly Detection System

> **bob logs in at 3 AM. 100 simultaneous connections from his workstation.**
> **The system has 0.3 seconds to decide: let him through, or kill the session.**

An AI-powered identity anomaly detection system that watches every authentication event on an enterprise network and asks one question: **is this normal FOR THIS PERSON?**

```
29.9M events  ·  604 users  ·  702 red-team attacks  ·  0.002% hit rate
```

---

## The Problem

Your password is not enough.

An attacker who steals bob's credentials doesn't break in — they **log in**. Same username. Same password. Same NTLM handshake. To the firewall, it looks identical to bob working late.

Except bob never works at 3 AM. bob never connects to 47 machines in one minute. bob never accesses the finance server.

**Signature-based security can't catch this.** There's no malware. No exploit. Just valid credentials used in an impossible way.

This project builds an AI that learns what "normal" looks like for **each individual user** — their hours, their machines, their habits — and flags when reality deviates from that baseline.

---

## What We Built

A live anomaly detection dashboard powered by Isolation Forest machine learning and per-user behavioral profiling. Pick a user. Simulate a login. Watch the system decide in real time.

### The 5 Demo Scenarios

| Scenario | What Happens | Score | Verdict |
|----------|-------------|-------|---------|
| **Normal** | alice logs in from her usual workstation at a normal hour | ~0.34 | ALLOW |
| **Wrong Pass** | alice fails authentication 3 times in a row | ~0.65-0.75 | FLAG/BLOCK |
| **New Dest** | alice connects to a machine she's never seen before | ~0.73 | FLAG |
| **Attacker** | unknown user from an attacker source machine | ~0.72+ | BLOCK |
| **Late Night** | bob logs in at 3 AM with 100+ rapid connections | ~0.35-0.45 | ALLOW |

The dashboard shows live KPIs, a threat gauge, an alert feed, score trends, and an investigation drawer for drilling into any event.

---

## How It Works

### Two-Layer Scoring Engine

Every login event passes through two detectors:

```
┌─────────────────────────────────────────────────────┐
│  Layer 1: Isolation Forest (ML)                     │
│  "How weird is this event across 8 dimensions?"     │
│  Output: if_score (0.0 to 1.0)                      │
├─────────────────────────────────────────────────────┤
│  Layer 2: Habit Deviation (Rules)                   │
│  "Does this break the user's personal patterns?"    │
│  Output: +0.00 to +0.30 boost                       │
├─────────────────────────────────────────────────────┤
│  Combined = if_score + 0.10 × min(dev_points, 3)    │
│                                                      │
│  ≥ 0.65  →  FLAG (investigate)                       │
│  ≥ 0.75  →  BLOCK (kill session)                     │
│  < 0.65  →  ALLOW (proceed)                          │
└─────────────────────────────────────────────────────┘
```

### What the Model Sees: 8 Features

| # | Feature | Type | What It Measures |
|---|---------|------|------------------|
| 1 | `dst_first` | binary | Is this the user's first time on this destination machine? |
| 2 | `src_first` | binary | Is this the user's first time from this source machine? |
| 3 | `hour_ratio` | float | What fraction of this user's total activity happens at this hour? |
| 4 | `dst_prior_events` | count | How many times has this user connected to this destination before? |
| 5 | `fail_1h` | count | How many authentication failures in the last hour? |
| 6 | `vel_1h` | count | How many login events in the last hour? |
| 7 | `hour_sin` | float | Cyclical time encoding (sin) — captures hour of day |
| 8 | `hour_cos` | float | Cyclical time encoding (cos) — captures hour of day |

### The 4 Habit Deviation Rules

| Rule | Condition | Points |
|------|-----------|--------|
| New destination | First visit to a machine outside the user's top-10 | +1 |
| New source | First login from a machine outside the user's top-10 | +1 |
| Velocity spike | Event rate exceeds 10x the user's hourly average (min 20/h) | +1 |
| Auth failures | 2+ failed authentications in the last hour | +1 |

Rules are capped at 3 points total. Each point adds +0.10 to the combined score.

---

## The Users We're Watching

All 4 demo users are **real people from the LANL Cyber1 dataset** — not fabricated.

| User | ID | Events | Sources | Destinations | Failure Rate | Persona |
|------|----|--------|---------|--------------|-------------|---------|
| alice | U10059@DOM1 | 99 | 1 (C17788) | 5 | 0% | Normal — single workstation, zero failures |
| bob | U10158@DOM1 | 39 | 4 | 5 | 0% | Normal — multi-workstation, mixed auth types |
| carol | U10500@DOM1 | 84 | 1 (C18941) | 5 | 11.9% | Normal — single workstation, has auth failures |
| attacker | U748@DOM1 | 62,633 | 117 | many | varies | Red team — lateral movement across 117 machines |

**alice** is predictable. One machine, one destination pattern, Kerberos only. The model learns her habits quickly.

**bob** is more varied. Four source machines, mixed auth types. The model needs more history to establish his baseline.

**carol** has failures built into her profile. This means the model treats some failures as "normal for carol" — only repeated failures trigger deviation.

**attacker** is a real red-team actor from Los Alamos. 62,633 events. 117 source machines. The model has seen this user during training and can recognize the lateral movement pattern.

---

## The Dataset: LANL Cyber1

This isn't synthetic data. It's a real enterprise authentication log from **Los Alamos National Laboratory**.

| Metric | Value |
|--------|-------|
| Total authentication events | 29,905,488 |
| Unique user accounts | 604 |
| Red-team (attacker) users | 104 |
| Red-team attack events | 702 (0.002% of all events) |
| Attack source computers | 4 (C17693 is the primary foothold) |
| Time span | Continuous enterprise monitoring |
| Auth types | NTLM, Kerberos, Unknown |

The extreme class imbalance (702 attacks out of 29.9M events) makes this a needle-in-a-haystack problem. The model must be precise enough to catch 0.002% without drowning in false positives.

### Why LANL?

- **Real enterprise data** — not lab-generated, not synthetic
- **Red-team ground truth** — 749 confirmed compromise events with timestamps
- **Scale** — 29.9M events across 604 users
- **Diversity** — 4 auth types, 12,840+ failure events, lateral movement patterns

---

## Model Performance

### Isolation Forest (Primary Detector)

| Metric | Value |
|--------|-------|
| Precision | 0.333 |
| Recall | 0.667 |
| F1 Score | 0.444 |
| False Positive Rate | 0.002% |
| ROC-AUC | 0.9997 |

### What the Numbers Mean

- **Precision 0.333**: Of every 3 events the model flags, 1 is a real attack.
- **Recall 0.667**: The model catches 2 out of every 3 actual attacks.
- **FPR 0.002%**: Only 2 in 100,000 normal events get falsely flagged.
- **ROC-AUC 0.9997**: Near-perfect separation between normal and attack distributions.

The model was trained with a contamination rate of 0.00235% — calibrated to flag only the most extreme 0.00235% of events as anomalies.

---

## Architecture

```
                    ┌──────────────┐
                    │  LANL Data   │
                    │  (29.9M rows)│
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │   Feature    │
                    │  Extraction  │
                    │ (8 features) │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │                         │
     ┌────────▼────────┐      ┌────────▼────────┐
     │  Isolation      │      │  Per-User       │
     │  Forest (ML)    │      │  Profile        │
     │  if_score       │      │  (top-10 src/dst│
     │  0.0 ─ 1.0     │      │   avg rate)     │
     └────────┬────────┘      └────────┬────────┘
              │                         │
              │    ┌───────────────┐    │
              └───►│  Combined     │◄───┘
                   │  Score        │
                   │  if + 0.10×dev│
                   └───────┬───────┘
                           │
                ┌──────────┼──────────┐
                │          │          │
         ┌──────▼──┐ ┌────▼─────┐ ┌──▼───────┐
         │  ALLOW  │ │   FLAG   │ │  BLOCK   │
         │ < 0.65  │ │ ≥ 0.65   │ │ ≥ 0.75   │
         └─────────┘ └──────────┘ └──────────┘
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| ML Models | scikit-learn (Isolation Forest), LightGBM (display only) |
| Feature Engine | SQL window functions over DuckDB |
| Database | DuckDB (embedded, columnar) |
| Backend | Flask (Python) with SSE streaming |
| Frontend | React 18, Vite 5, Tailwind CSS 3, Recharts |
| Animations | Framer Motion |
| Data Format | Parquet (primary), joblib (models) |

---

## Project Structure

```
lanl-anomaly/
├── data/
│   └── raw/lanl/              # LANL Cyber1 dataset
│       ├── feat.parquet       # 29.9M events with precomputed features
│       ├── slice.parquet      # Demo subset (4 users)
│       └── redteam.txt        # 749 ground-truth attack labels
├── src/                       # Training pipeline
│   ├── 01_anomaly_ensemble.py # Ensemble training
│   ├── 02_retrain_both.py     # IF + LGB retraining
│   └── _shared.py             # Shared evaluation utilities
├── models/                    # Trained model artifacts
│   ├── lanl_if.joblib         # Isolation Forest (production)
│   └── lanl_lgb.joblib        # LightGBM (display only)
├── live/                      # Live scoring system
│   ├── scoring.py             # Core engine — IF + habit deviation
│   ├── app.py                 # Flask backend (REST + SSE)
│   ├── db.py                  # DuckDB storage + user profiles
│   ├── seed_demo.py           # Seeds 4 real users from LANL data
│   ├── generate.py            # Event generation for demo
│   └── web/                   # React SPA dashboard
│       └── src/               # Components, pages, hooks
├── docs/                      # Documentation
│   ├── model_deep_dive.md     # Full mathematical reference
│   └── phase2_report.md       # Academic project report
└── reports/                   # Analysis reports
    └── lanl_findings.md       # Dataset findings + separation analysis
```

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- npm

### Quick Start

```bash
# Clone the repository
git clone <repo-url>
cd lanl-anomaly

# Install Python dependencies
pip install flask duckdb scikit-learn lightgbm joblib numpy pandas

# Install frontend dependencies
cd live/web && npm install && cd ../..

# Seed the demo database
python -m live.seed_demo

# Start the backend
python -m live.app

# In a separate terminal — start the frontend
cd live/web && npm run dev
```

Open the login page. Pick a scenario. Watch the system decide.

---

## Key Files to Read

| File | What It Does | Lines |
|------|-------------|-------|
| `live/scoring.py` | The brain — IF scoring + habit deviation + feature computation | ~400 |
| `live/app.py` | Flask backend — routes, SSE streaming, event generation | ~300 |
| `live/db.py` | Database layer — schema, profiles, queries | ~200 |
| `live/seed_demo.py` | Seeds 4 real LANL users into the demo database | ~130 |
| `docs/model_deep_dive.md` | Complete mathematical reference for every formula | 1105 |

---

## How Late Night Stays Below 0.45

The most common question: "Why doesn't 100 simultaneous logins at 3 AM trigger an alert?"

Five mechanisms compress the score:

1. **`hour_ratio` capped at 0.001** — the time-of-day feature is hard-clipped, effectively neutering it
2. **Same source/destination** — `dst_first=0`, `src_first=0` removes the two strongest signals
3. **Successful logins** — `fail_1h=0` means no authentication failure signal
4. **Log compression** — `log1p(100) = 4.62` is moderate relative to training data (max 30,097)
5. **Normalization range** — IF scores are normalized against extreme training outliers, compressing moderate anomalies

The system is designed this way intentionally. Time-of-day alone is a weak signal. The system prioritizes **destination novelty** and **lateral movement** as stronger indicators of compromise.

---

## Academic Context

This project was developed as a Bachelor of Engineering thesis in Computer Science and Engineering at Government Sri Krishnarajendra Silver Jubilee Technological Institute, affiliated to VTU, Belagavi.

**Core contribution**: A hybrid UEBA (User and Entity Behavior Analytics) system combining unsupervised machine learning with per-user behavioral profiling for authentication anomaly detection on real enterprise data.

---

## License

Academic project — see `docs/phase2_report.md` for full attribution and references.
