Live dashboard has old code

# LANL Anomaly Detection System

AI-powered authentication anomaly detection on 29.9M events from Los Alamos National Laboratory.

## Prerequisites

- Python 3.12+
- pip
- Git

## Setup

```bash
# 1. Clone
git clone -b feature/lanl-rebuild https://github.com/urvashiritu/MAJOR-PAIN-ATE-.git
cd MAJOR-PAIN-ATE-/lanl-anomaly

# 2. Install dependencies
pip install -r requirements.txt
pip install gdown

# 3. Download dataset (~1.2 GB)
mkdir -p data/raw/lanl
gdown 147vxAEqS7hGj_KDSG8JJc2hLNq4lyd4c -O data/raw/lanl/lanl.duckdb

# 4. Train
python src/03_retrain_both.py --verbose
```

Models save to `models/lanl_if.joblib` and `models/lanl_lgb.joblib`.

## Dataset

Download: [Google Drive](https://drive.google.com/file/d/147vxAEqS7hGj_KDSG8JJc2hLNq4lyd4c/view?usp=sharing)

The `lanl.duckdb` file contains:

| Table | Rows | Description |
|-------|------|-------------|
| `feat` | 29,905,488 | Engineered features used for training |
| `auth_slice` | 29,905,488 | Raw authentication events |
| `redteam` | 702 | Red team attacker users |

## Training

```bash
# Retrain IF + LightGBM (production dual-model)
python src/03_retrain_both.py --verbose
```

The full pipeline from raw data (rarely needed — the dataset above is ready to use):

```bash
# 00: audit the 1.05B stream -> users.txt, then slice to 604 users -> slice.csv.gz
unzip -p ~/Downloads/archive.zip auth.txt/auth.txt | python src/00_build_slice.py count
unzip -p ~/Downloads/archive.zip auth.txt/auth.txt | python src/00_build_slice.py slice
python src/00_build_slice.py load          # slice.csv.gz -> auth_slice + slice.parquet

# 01: compute the 9 features -> feat table + feat.parquet (self-verifying)
python src/01_build_features.py

# 02: per-feature separation probe (AUCs of attacks vs normal behavior)
python src/02_feature_probe.py
```

Runtime: ~5 minutes, requires ~6 GB RAM.
