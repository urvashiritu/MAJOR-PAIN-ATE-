# LANL Anomaly Detection — Setup & Run

AI-powered identity anomaly detection on **29.9M authentication events** from Los Alamos National Laboratory. Catches attacks in **0.3 seconds**.

---

## Quick Start (5 min)

```bash
# 1. Clone
git clone https://github.com/urvashiritu/MAJOR-PAIN-ATE-.git
cd MAJOR-PAIN-ATE-/lanl-anomaly

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Seed demo database (creates data/live.duckdb with 4 real LANL users)
python -m live.seed_demo

# 4. Start backend (Flask on port 5000)
python -m live.app

# 5. Open dashboard
# Flask serves the vanilla HTML/CSS/JS dashboard at http://localhost:5000/dashboard
```

---

## Prerequisites

- **Python 3.12+**
- **Git** (with Git LFS for dataset download)
- **~2 GB disk space** for the dataset

---

## Data

The dataset lives in `data/raw/lanl/lanl.duckdb` (tracked via Git LFS). It contains:

| Table | Rows | Purpose |
|-------|------|---------|
| `feat` | 29,905,488 | Engineered features (20 columns incl. `is_ntlm`) — used for training |
| `auth_slice` | 29,905,488 | Raw auth events (9 columns) — used for demo seeding |
| `redteam` | 702 | Red team attacker users |

**Git LFS is required** to download the database (~1.2 GB):
```bash
# Install Git LFS (if not already installed)
sudo apt install git-lfs   # Ubuntu/Debian
# or: brew install git-lfs  # macOS

git lfs install
git lfs pull   # downloads the actual .duckdb file
```

---

## Retraining Models

### Retrain IF + LGB (production dual-model)

```bash
python src/03_retrain_both.py --verbose
```

- Reads `feat` table from `lanl.duckdb`
- Outputs: `models/lanl_if.joblib` (2 MB), `models/lanl_lgb.joblib` (1 MB)
- Runtime: ~5 min, requires ~6 GB RAM
- See `reports/both_report.json` for metrics

### Rebuild the dataset from raw (rarely needed)

Only if you downloaded the original LANL archive (`archive.zip`, 7.1 GB) and want
to reproduce the 29.9M dataset from scratch — see `docs/PROJECT_STORY.md`:

```bash
# 00: stream-audit all 1.05B events (writes users.txt), then slice to 604 users
unzip -p ~/Downloads/archive.zip auth.txt/auth.txt | python src/00_build_slice.py count
unzip -p ~/Downloads/archive.zip auth.txt/auth.txt | python src/00_build_slice.py slice
python src/00_build_slice.py load            # -> auth_slice table + slice.parquet

# 01: compute the 9 features (self-verifying against the existing feat table)
python src/01_build_features.py

# 02: per-feature separation probe (red-team vs normal behavior, ROC-AUCs)
python src/02_feature_probe.py
```

---

## Project Structure

```
lanl-anomaly/
├── data/raw/lanl/
│   └── lanl.duckdb              # Full dataset (Git LFS, 1.2 GB)
├── models/
│   ├── lanl_if.joblib           # Isolation Forest (2 MB)
│   └── lanl_lgb.joblib          # LightGBM (1 MB)
├── src/                         # Training pipeline
│   ├── 00_build_slice.py        # Stream 1.05B events -> audit + 604-user slice
│   ├── 01_build_features.py     # 9 features via window SQL (self-verifying)
│   ├── 02_feature_probe.py      # Per-feature separation probe (AUCs)
│   └── 03_retrain_both.py       # Main: retrain IF + LGB
├── live/                        # Live scoring system
│   ├── scoring.py               # Core scoring engine
│   ├── app.py                   # Flask backend (port 5000)
│   ├── db.py                    # Database schema + helpers
│   ├── seed_demo.py             # Seed demo DB from lanl.duckdb
│   ├── vanilla-dashboard/       # HTML/CSS/JS dashboard
│   │   ├── index.html
│   │   ├── css/style.css
│   │   ├── js/app.js            # Main app (router, pages, SSE)
│   │   ├── js/api.js            # API client
│   │   ├── js/charts.js         # Chart.js visualizations
│   │   ├── js/components.js     # UI components
│   │   ├── js/utils.js          # Utilities
│   │   └── serve.py             # Static file proxy (port 8080)
│   └── web/                     # React dashboard (optional, not used)
├── docs/                        # Documentation
│   ├── model_deep_dive.md       # Technical deep dive
│   ├── phase2_ppt.md            # Presentation slides
│   └── phase2_report.md         # Project report
├── reports/                     # Analysis reports
├── scripts/                     # Utility scripts
├── requirements.txt             # Python dependencies
├── SETUP.md                     # This file
└── README.md                    # Project overview
```

---

## Dashboard Architecture

```
Browser (port 8080 or 5000)
  │
  ├── GET /api/dashboard     → KPIs, recent events, alerts
  ├── GET /api/alerts        → Alert list
  ├── GET /api/users         → User list
  ├── POST /api/alerts/<id>/ack  → Acknowledge alert
  ├── POST /api/reset        → Clear all live data
  ├── GET /events/stream     → SSE (live score updates)
  │
  └── Flask backend (port 5000)
        ├── scoring.py       → IF + LGB + habit deviation
        └── data/live.duckdb → Live state (users, events, alerts)
```

### Running the vanilla dashboard (two options)

**Option A: Flask serves everything (recommended)**
```bash
python -m live.app
# Open http://localhost:5000/dashboard
```

**Option B: Separate proxy server**
```bash
# Terminal 1: Flask backend
python -m live.app

# Terminal 2: Vanilla dashboard proxy (port 8080)
python live/vanilla-dashboard/serve.py
# Open http://localhost:8080
```

---

## How It Works

1. **Feature Engineering**: 9 features computed from raw auth events
   - `dst_first`, `src_first` — first-time destination/source
   - `hour_ratio` — hour-of-day ratio
   - `dst_prior_events` — prior events to this destination
   - `fail_1h` — failures in last hour
   - `vel_1h` — velocity in last hour
   - `hour_sin`, `hour_cos` — cyclical hour encoding
   - `is_ntlm` — NTLM auth type flag

2. **Scoring Pipeline**:
   - Isolation Forest anomaly score (primary detector)
   - LightGBM probability (displayed for transparency)
   - Habit-deviation boost (per-user baseline)
   - Combined score → BLOCK (>0.75) / FLAG (>0.65) / ALLOW

3. **Metrics** (test set, 29.9M events):
   | Model | ROC-AUC | PR-AUC | FPR |
   |-------|---------|--------|-----|
   | IF | 0.989 | 0.0063 | 0.00% |
   | LGB | 0.847 | 0.0153 | 0.07% |
   | Combined | **0.994** | **0.0323** | **0.02%** |

---

## Team

Hemanth Kumar KS, Urvashi Tanwar, Veenashree S T, Vishwanath Sanapur — guided by Dr. Anitha A C at GSKSJTI, CSE.
