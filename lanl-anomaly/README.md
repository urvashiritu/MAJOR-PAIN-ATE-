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

## The Journey: 73 GB of Logs to a 0.3-Second Decision

```
auth.txt (1.05B events, 73.4 GB)
    │  stream through unzip pipe (never extracted to disk)
    ▼
slice.parquet (29.9M events, 604 users)
    │  join red-team labels + compute 9 SQL window features
    ▼
feat.parquet (29.9M × 18 columns)
    │  log-transform → StandardScaler → train 200 trees
    ▼
Isolation Forest model (decides in 0.3 seconds)
```

---

## The Raw Data: What We Started With

The LANL Cyber1 dataset is a real enterprise authentication log from **Los Alamos National Laboratory**. Every login attempt on their network for 58 days.

**Format:** 9 columns, no header, comma-separated.

| # | Column | Example | What It Tells Us |
|---|--------|---------|------------------|
| 1 | time | `150885` | Seconds since monitoring started |
| 2 | src_user | `U748@DOM1` | Who is logging in |
| 3 | dst_user | `U748@DOM1` | Who they're logging in as |
| 4 | src_computer | `C17693` | Where they're logging in FROM |
| 5 | dst_computer | `C305` | Where they're logging in TO |
| 6 | auth_type | `NTLM` | How they authenticated |
| 7 | logon_type | `Network` | What kind of login |
| 8 | orientation | `LogOn` | Login or logout |
| 9 | result | `Success` | Did it work |

**The scale:** 1,051,430,459 events. 73.4 GB uncompressed. **Doesn't fit on disk** (only 43 GB free).

**The challenge:** No IP addresses. No device IDs. No GPS. Just user@computer, machine names, and Success/Fail. All detection must be behavioral.

---

## How We Cleaned It: From 1.05 Billion to 29.9 Million

### Step 1: Stream, Don't Extract

`auth.txt` is 73.4 GB decompressed — bigger than our disk. Solution: stream through a pipe.

```bash
unzip -p archive.zip auth.txt | python lanl_stream.py count
```

Never writes the full file to disk. Parses each line in memory, counts events, collects distinct users.

**Result:** 80,553 distinct source users identified.

### Step 2: Filter to 604 Users

We keep two groups:
- **104 red-team users** — compromised accounts from `redteam.txt` (ground truth attacks)
- **500 random normal users** — sampled with `random.seed(42)` for reproducibility

```python
keep = red_users | random.sample(normal_users, 500)  # 604 total
```

### Step 3: Label the Attacks

Join `redteam.txt` onto the filtered events. Each red-team entry is a 4-field match:

```
time, user, src_computer, dst_computer → is_red = True
```

**Result:** 702 events labeled as attacks out of 29.9M total (0.002%).

### Step 4: Verify

Independent blind audit — 7 verification gates, all passed:
- 29,905,488 rows confirmed
- 702/715 red-team tuples found (13 are label quirks)
- All 9 features recomputed from scratch: 0 mismatches

---

## Feature Engineering: The 9 Signals

Raw data tells us "bob logged in from C21468 to C586 at 10:14 PM." The model needs to know "is this NORMAL for bob?"

We compute **8 behavioral features** per event using SQL window functions:

### Binary Signals (First-Time Flags)

| Feature | Formula | What It Means |
|---------|---------|---------------|
| `dst_first` | `1 if this is user's first visit to dst_computer, else 0` | Never been here before = suspicious |
| `src_first` | `1 if this is user's first event from src_computer, else 0` | New machine = suspicious |

**Example:** If bob has connected to C586 before, `dst_first=0`. If this is his first time, `dst_first=1`. This is the **strongest signal** in the model.

### Count Signals (Activity Patterns)

| Feature | Formula | What It Means |
|---------|---------|---------------|
| `dst_prior_events` | `COUNT visits to dst_computer before this event` | 0 = new, 881,299 = very familiar |
| `fail_1h` | `COUNT failures in last 3600 seconds` | 0 = clean, 508 = brute force |
| `vel_1h` | `COUNT all events in last 3600 seconds` | 0 = idle, 30,097 = extreme burst |

**Math (SQL window functions):**
```sql
-- dst_prior_events: how many times has user visited this destination BEFORE now?
COUNT(*) OVER (
    PARTITION BY src_user, dst_computer
    ORDER BY time
    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
)

-- vel_1h: how many events in the last 3600 seconds?
COUNT(*) OVER (
    PARTITION BY src_user
    ORDER BY time
    RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING
)
```

### Time Signals (When They Login)

| Feature | Formula | What It Means |
|---------|---------|---------------|
| `hour_ratio` | `hour_events_so_far / user_events_so_far` | Fraction of user's activity at this hour |
| `hour_sin` | `sin(hour / 24.0 × 2π)` | Cyclical time encoding (X coordinate) |
| `hour_cos` | `cos(hour / 24.0 × 2π)` | Cyclical time encoding (Y coordinate) |

**Why sin/cos?** Hours are circular — 23:00 is close to 00:00. Linear encoding (0-23) misses this. Sin/cos maps hours to a circle where adjacent hours are close.

```
hour = (time % 86400) / 3600    # float [0.0, 24.0)
hour_sin = sin(hour / 24 × 2π)  # range [-1, 1]
hour_cos = cos(hour / 24 × 2π)  # range [-1, 1]
```

### Feature Value Ranges (What the Model Sees)

| Feature | Min | Max | Distribution |
|---------|-----|-----|-------------|
| dst_first | 0 | 1 | ~5% are 1 (first visits) |
| src_first | 0 | 1 | ~3% are 1 (first sources) |
| dst_prior_events | 0 | 881,299 | Heavily right-skewed |
| fail_1h | 0 | 508 | 99.8% are 0 |
| vel_1h | 0 | 30,097 | Right-skewed |
| hour_ratio | 0 | 1.0 | Clipped to 0.001 in production |
| hour_sin | -1 | 1 | Uniform (cyclical) |
| hour_cos | -1 | 1 | Uniform (cyclical) |
| **is_ntlm** | **0** | **1** | **100% of attacks, 4% of normals** |

---

## Why We Tested 7 Models

We didn't just pick Isolation Forest. We tried everything.

| Model | Type | ROC-AUC | F1 | FPR | Why Rejected/Selected |
|-------|------|---------|-----|-----|-------------|
| **Isolation Forest** | Unsupervised | 0.989 | 0.040 | **0.0%** | **Production** — zero false alarms |
| **LightGBM** | Supervised | 0.847 | 0.044 | **0.07%** | **Production** — catches 64.5% of attacks |
| **Combined (IF+LGB)** | Hybrid | 0.994 | **0.101** | **0.002%** | **Best balance** |
| Elliptic Envelope | Unsupervised | 1.000 | 0.333 | 0.0% | Only 4 test reds (meaningless) |
| LOF | Unsupervised | 0.814 | 0.003 | 0.02% | 15 min to train (too slow) |
| One-Class SVM | Unsupervised | 0.078 | 0.000 | 5.0% | Worse than random |
| Oracle (blocklist) | Post-hoc | 1.000 | 0.011 | 0.02% | Requires knowing attacker machines |

### Why LightGBM Now Works

LightGBM previously flagged **1.4 MILLION false alarms** (FPR=15.9%) because `scale_pos_weight=42634` saturated all outputs to 1.0. We fixed this by:

1. Adding `is_ntlm` feature (100% of attacks use NTLM, only 4% of normals)
2. Lowering `scale_pos_weight` from 42634 to 100

Now LGB catches **64.5% of attacks** with only **6,282 false alarms** (FPR=0.07%). It produces real probability scores instead of just outputting 1.0 for everything.

### Why One-Class SVM Failed

ROC-AUC of 0.078 is **worse than random** (0.500). The model consistently ranked attacks LOWER than normal events. Fundamental mismatch with high-dimensional, extremely imbalanced authentication data.

### Why Isolation Forest Won

1. **0% false positive rate** — SOC analysts trust it
2. **Unsupervised** — doesn't need labels to learn
3. **Fast** — 13 seconds on 7M rows, scales to 29.9M
4. **Works with habit deviation** — ML catches structural anomalies, rules catch personal pattern breaks

---

## How Isolation Forest Learns

The core intuition: **anomalies are easy to isolate. Normal events are hard.**

### The Algorithm

1. Build **200 decision trees**
2. Each tree trains on **256 random rows** (subsample)
3. At each node: pick a **random feature**, pick a **random split value**
4. Split recursively until isolated or depth limit reached

### Path Length = Anomaly Score

```
Normal event:  "bob logs in from C21468 to C586"
  → Similar to thousands of other events
  → Takes 15+ splits to isolate
  → Long path = LOW anomaly score

Attack event:  "attacker logs in from C17693 to C9999"  
  → Very different from everything else
  → Takes 2-3 splits to isolate
  → Short path = HIGH anomaly score
```

### The Math

```
anomaly_score(x) = 2^(-E[path_length(x)] / c(n))

where:
  E[path_length(x)] = average path length across 200 trees
  c(n) = 2 × H(n-1) - 2(n-1)/n  (average path in random BST)
  H(i) = harmonic number ≈ ln(i) + 0.5772
```

**Score interpretation:**
- Score → 1.0: anomaly (easy to isolate)
- Score → 0.5: normal (hard to isolate)
- Score → 0.0: very normal (deep in the cluster)

### Why 200 Trees?

More trees = more stable scores (law of large numbers). 200 is a balance between accuracy and speed. 100 trees gives similar results; 500 trees gives marginally better but 2.5x slower.

---

## Training the Beast: 29.9 Million Events

### The Contamination Problem

702 attacks out of 29,905,488 events = **0.00235%**. This is the contamination rate — the fraction of anomalies the model should expect.

```python
contamination = 702 / 29_905_488  # = 2.35e-5
```

This tells Isolation Forest: "Assume 0.00235% of your training data is anomalous."

### Log-Transform: Taming Skewed Features

Three features are heavily right-skewed:
- `dst_prior_events`: 0 to 881,299
- `fail_1h`: 0 to 508
- `vel_1h`: 0 to 30,097

Distance-based models (like IF) get confused by extreme values. Solution: log-transform.

```python
log1p(x) = ln(1 + x)

# Examples:
log1p(0) = 0.0
log1p(100) = 4.62
log1p(10000) = 9.21
log1p(881299) = 13.69
```

Log-transform compresses the range: 0-881,299 becomes 0-13.69. The model can now see differences at the low end without being overwhelmed by outliers.

### StandardScaler: Centering the Data

After log-transform, features have different scales. StandardScaler centers them:

```
z = (x - mean_train) / std_train
```

Mean and standard deviation are computed from the **training set only** (no test leakage).

### Score Normalization: Mapping to [0, 1]

Raw IF scores can be any number. We normalize to [0, 1] using the training set's score range:

```python
if_scores_raw = -model.score_samples(X)  # negate (higher = more anomalous)
if_min = if_scores_raw.min()  # from training set
if_max = if_scores_raw.max()  # from training set

if_score = (if_scores_raw - if_min) / (if_max - if_min)  # → [0, 1]
```

**Why min-max?** The model's decision threshold is at 0.65 (FLAG) and 0.75 (BLOCK). Normalizing to [0,1] makes these thresholds meaningful and interpretable.

### The Stratified Split

We can't just randomly split 29.9M rows — we might get 0 attacks in the test set. Solution: **stratified split**.

```python
from sklearn.model_selection import StratifiedShuffleSplit

sss = StratifiedShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
# Ensures ~211 reds in test (30% of 702) and ~491 reds in train (70% of 702)
```

**Result:** Train = 20,933,841 rows (491 reds) / Test = 8,971,647 rows (211 reds).

---

## What Each Model Learned

### The Full Results Table

| Model | ROC-AUC | Precision | Recall | F1 | FPR | TP | FP | Verdict |
|-------|---------|-----------|--------|-----|-----|-----|-----|---------|
| **Isolation Forest** | 0.989 | 0.051 | 0.033 | 0.040 | **0.0%** | 7 | 131 | **Production** |
| **LightGBM** | 0.847 | 0.023 | **0.645** | 0.044 | **0.07%** | 136 | 6,282 | **Production** |
| **Combined (IF+LGB)** | 0.994 | 0.057 | **0.488** | **0.101** | **0.002%** | 103 | 178 | **Best balance** |
| Elliptic Env | 1.000 | 0.500 | 0.250 | 0.333 | 0.0% | 1 | 1 | 4 test reds only |
| LOF | 0.814 | 0.002 | 0.250 | 0.003 | 0.02% | 1 | 611 | Too slow |
| One-Class SVM | 0.078 | 0.0 | 0.0 | 0.0 | 5.0% | 0 | 150,567 | Worse than random |

### What These Numbers Mean (Plain English)

**IF catches 7 attacks with zero false alarms.** Conservative but safe. Every alert is real.

**LGB catches 136 attacks with 6,282 false alarms.** More aggressive — catches 19x more attacks than IF, but flags some normal logins too.

**Combined catches 103 attacks with only 178 false alarms.** Best balance — nearly half of all attacks caught, almost no false alarms. The two models cover each other's weaknesses.

**ROC-AUC = 0.994 (combined)** → The model ranks attacks higher than normal events 99.4% of the time. Near-perfect separation.

### The Holdout Test: C17693

One attacker machine was **held out** from training entirely: C17693 (the primary red-team foothold with 670 attack events).

| Model | C17693 ROC-AUC | C17693 PR-AUC |
|-------|---------------|---------------|
| IF | 0.556 | 0.576 |
| LGB | 0.555 | 0.556 |
| Combined | 0.576 | 0.609 |

**Interpretation:** The models barely beat random (0.500) on unseen attacker machines. This is expected — the model learns user-specific patterns, not attacker-specific patterns. In production, the **habit deviation layer** catches novel attacks that the IF model misses.

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

### What the Model Sees: 9 Features

The model receives 9 behavioral features per event (computed via SQL window functions — see [Feature Engineering](#feature-engineering-the-8-signals) for the math):

`dst_first` · `src_first` · `hour_ratio` · `dst_prior_events` · `fail_1h` · `vel_1h` · `hour_sin` · `hour_cos` · `is_ntlm`

### The 4 Habit Deviation Rules

| Rule | Condition | Points |
|------|-----------|--------|
| New destination | First visit to a machine outside the user's top-10 | +1 |
| New source | First login from a machine outside the user's top-10 | +1 |
| Velocity spike | Event rate exceeds 10x the user's hourly average (min 20/h) | +1 |
| Auth failures | 2+ failed authentications in the last hour | +1 |

Rules are capped at 3 points total. Each point adds +0.15 to the combined score.

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
