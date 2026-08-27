# LANL Anomaly Detection System

> **bob logs in at 3 AM. 100 simultaneous connections from his workstation.**
> **The system has 0.3 seconds to decide: let him through, or kill the session.**

An AI that watches every login on an enterprise network and asks: **is this normal FOR THIS PERSON?**

```
29.9M events  ·  604 users  ·  702 attacks  ·  0.002% hit rate  ·  0.3s decision
```

---

## What We Built

- **9 behavioral features** per login event, computed via SQL window functions
- **Isolation Forest + LightGBM** hybrid model, ROC-AUC **0.994**
- **Two-layer scoring**: ML anomaly detection + per-user habit deviation rules
- **Near-zero false positives**: 178 false alarms across 8.9M test events
- **Live dashboard** with real-time SSE streaming and investigation tools

---

## How It Works

```
auth.txt (1.05B events, 73 GB)
    │  stream through unzip (never extracted to disk)
    ▼
slice.parquet (29.9M events, 604 users)
    │  join red-team labels + compute 9 SQL window features
    ▼
feat.parquet (29.9M rows × 19 columns)
    │  log-transform → StandardScaler → train 200 trees
    ▼
IF + LGB models → score in 0.3 seconds
```

### Two-Layer Scoring

```
┌──────────────────────────────────────────────────┐
│  Layer 1: Isolation Forest (ML)                  │
│  "How weird is this event across 9 dimensions?"  │
│  Output: if_score (0.0 to 1.0)                   │
├──────────────────────────────────────────────────┤
│  Layer 2: Habit Deviation (Rules)                │
│  "Does this break the user's personal patterns?" │
│  Output: +0.00 to +0.45 boost                    │
├──────────────────────────────────────────────────┤
│  Combined = if_score + 0.15 × min(dev_points, 3) │
│                                                   │
│  ≥ 0.65  →  FLAG (investigate)                    │
│  ≥ 0.75  →  BLOCK (kill session)                  │
│  < 0.65  →  ALLOW (proceed)                       │
└──────────────────────────────────────────────────┘
```

---

## The 9 Features

| # | Feature | What It Measures | Why It Matters |
|---|---------|-----------------|----------------|
| 1 | `dst_first` | First visit to this destination? | **Strongest signal** — new machine = suspicious |
| 2 | `src_first` | First event from this source? | New source machine = suspicious |
| 3 | `hour_ratio` | Fraction of user's activity at this hour | Unusual time for this person |
| 4 | `dst_prior_events` | Prior visits to this destination | 0 = never visited, 881K = familiar |
| 5 | `fail_1h` | Login failures in last hour | 0 = clean, 508 = brute force |
| 6 | `vel_1h` | Events in last hour | 0 = idle, 30K = extreme burst |
| 7 | `hour_sin` | sin(hour/24 × 2π) | Cyclical time encoding |
| 8 | `hour_cos` | cos(hour/24 × 2π) | Cyclical time encoding |
| 9 | `is_ntlm` | NTLM authentication? | **100% of attacks**, 4% of normals |

---

## Results

### Model Comparison

| Model | ROC-AUC | Catches | False Alarms | FPR | Verdict |
|-------|---------|---------|-------------|-----|---------|
| **Isolation Forest** | **0.989** | 7/211 | 131 | **0.0%** | Production — zero false alarms |
| **LightGBM** | 0.847 | 136/211 | 5,833 | **0.07%** | Production — catches 19x more |
| **Combined (IF+LGB)** | **0.994** | **103/211** | **178** | **0.002%** | **Best balance** |
| One-Class SVM | 0.078 | 0/211 | 150,567 | 5.0% | Worse than random |
| LOF | 0.814 | 1/211 | 611 | 0.02% | Too slow (15 min train) |

### Confusion Matrices

**IF:** 7 attacks caught, 131 false alarms — conservative but safe.
```
                    Predicted Normal    Predicted Attack
Actual Normal       8,971,305           131
Actual Attack       204                 7
```

**LGB:** 136 attacks caught, 5,833 false alarms — aggressive but catches more.
```
                    Predicted Normal    Predicted Attack
Actual Normal       8,965,603           5,833
Actual Attack       75                  136
```

**Combined:** 103 attacks caught, 178 false alarms — best balance.
```
                    Predicted Normal    Predicted Attack
Actual Normal       8,971,127           178
Actual Attack       108                 103
```

### Holdout Test (C17693 — unseen attacker)

| Model | ROC-AUC | PR-AUC |
|-------|---------|--------|
| IF | 0.556 | 0.576 |
| LGB | 0.555 | 0.556 |
| Combined | 0.576 | 0.609 |

Models barely beat random (0.500) on unseen attackers. This is honest — the model learns user patterns, not attacker patterns. The **habit deviation layer** catches novel attacks that IF misses.

---

## Demo Scenarios

| Scenario | What Happens | Score | Verdict |
|----------|-------------|-------|---------|
| **Normal** | alice logs in from her usual workstation | ~0.34 | ALLOW |
| **Wrong Pass** | alice fails authentication 3 times | ~0.65-0.75 | FLAG/BLOCK |
| **New Dest** | alice connects to a machine she's never seen | ~0.73 | FLAG |
| **Attacker** | unknown user from attacker source machine | ~0.72+ | BLOCK |
| **Late Night** | bob logs in at 3 AM with 100+ rapid connections | ~0.35-0.45 | ALLOW |

---

## The Users

All 4 demo users are **real people from the LANL dataset** — not fabricated.

| User | Events | Sources | Failure Rate | Persona |
|------|--------|---------|-------------|---------|
| alice | 99 | 1 | 0% | Predictable — one machine, zero failures |
| bob | 39 | 4 | 0% | Multi-workstation, mixed auth types |
| carol | 84 | 1 | 11.9% | Has failures in her baseline |
| attacker | 62,633 | 117 | varies | Red team — lateral movement across 117 machines |

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
                    │ (9 features) │
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
                   │  if + 0.15×dev│
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
| ML Models | scikit-learn (Isolation Forest), LightGBM |
| Feature Engine | SQL window functions over DuckDB |
| Database | DuckDB (embedded, columnar) |
| Backend | Flask (Python) with SSE streaming |
| Frontend | React 18, Vite 5, Tailwind CSS 3, Recharts |

---

## Project Structure

```
lanl-anomaly/
├── data/raw/lanl/           # LANL Cyber1 dataset
│   ├── feat.parquet         # 29.9M events with 19 columns
│   ├── slice.parquet        # Demo subset (4 users)
│   └── redteam.txt          # 749 ground-truth attack labels
├── src/                     # Training pipeline
│   ├── 02_retrain_both.py   # IF + LGB retraining
│   └── _shared.py           # Shared evaluation utilities
├── models/                  # Trained model artifacts
│   ├── lanl_if.joblib       # Isolation Forest (production)
│   └── lanl_lgb.joblib      # LightGBM (production)
├── live/                    # Live scoring system
│   ├── scoring.py           # Core engine — IF + habit deviation
│   ├── app.py               # Flask backend (REST + SSE)
│   ├── db.py                # DuckDB storage + user profiles
│   ├── seed_demo.py         # Seeds 4 real users from LANL data
│   └── web/                 # React SPA dashboard
├── docs/                    # Documentation
│   ├── model_deep_dive.md   # Full mathematical reference
│   ├── phase2_ppt.md        # Presentation slides
│   └── phase2_report.md     # Academic project report
└── reports/                 # Analysis reports
```

---

## Quick Start

```bash
# Clone
git clone <repo-url> && cd lanl-anomaly

# Backend
pip install flask duckdb scikit-learn lightgbm joblib numpy pandas
python -m live.seed_demo
python -m live.app

# Frontend (separate terminal)
cd live/web && npm install && npm run dev
```

Open the login page. Pick a scenario. Watch the system decide.

---

## Key Files

| File | What It Does |
|------|-------------|
| `live/scoring.py` | The brain — IF scoring + habit deviation + feature computation |
| `live/app.py` | Flask backend — routes, SSE streaming, event generation |
| `live/db.py` | Database layer — schema, profiles, queries |
| `docs/model_deep_dive.md` | Complete mathematical reference for every formula |

---

## Academic Context

Bachelor of Engineering thesis in CSE at GSKSJTI, affiliated to VTU, Belagavi.

**Core contribution:** Hybrid UEBA system combining unsupervised ML with per-user behavioral profiling for authentication anomaly detection on real enterprise data.

See `docs/phase2_report.md` for full attribution and references.
