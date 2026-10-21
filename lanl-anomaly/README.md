# LANL Anomaly Detection

This system finds abnormal authentication activity. It uses 29,905,488
authentication events from Los Alamos National Laboratory (LANL).

## Architecture

[Interactive diagram](live/static/lanl-ueba-architecture.html) — open the file in
a browser. Click a node for details. Use the button to change the theme.

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌─────────────┐
│  Employees  │───▶│  Flask API   │───▶│  Feature Eng │───▶│  LGB-21     │
│  (4 users)  │    │  :5000       │    │  21 feats    │    │  Model      │
└─────────────┘    └──────────────┘    └──────┬───────┘    └──────┬──────┘
                                               │                   │
                                      ┌────────▼────────┐   ┌──────▼──────┐
                                      │  LSTM-AE        │──▶│  Threshold  │
                                      │  Recon Error    │   │  BLOCK/FLAG │
                                      │  (Feature 21)   │   └──────┬──────┘
                                      └─────────────────┘          │
                                                     ┌─────────────▼─────────────┐
                                                     │  SSE Stream → Dashboard   │
                                                     │  ECharts + Alerts         │
                                                     └───────────────────────────┘
```

The data layer consists of these items.

| Item | Size | Use |
|------|------|-----|
| `data/raw/lanl/lanl.duckdb.zst` | 5.61 GB | The compressed source events |
| `data/raw/lanl/lanl.duckdb` | 9.7 GiB | The source events after decompression. Read only |
| `data/processed/lanl_scores.parquet` | 370 MB | Model scores for 29.9M events |
| `models/*.joblib`, `models/*.pt` | 17.6 MB | LGB and LSTM-AE weights |

## Requirements

You must have these items.

- Linux, or Windows using WSL
- Python 3.12 or later
- Git with Git LFS
- 12 GB free disk space
- 16 GB RAM

The GPU is not necessary. The models run on the CPU.

## Setup

```bash
# 1. Get the code
git clone -b exp/live-feature-parity https://github.com/urvashiritu/MAJOR-PAIN-ATE-.git
cd MAJOR-PAIN-ATE-/lanl-anomaly

# 2. Copy the database into data/raw/lanl/ before you continue.
#    The file is lanl.duckdb.zst (5,613,536,885 bytes). See SETUP.md.

# 3. Install Git LFS and zstd
sudo apt install git-lfs zstd
git lfs install

# 4. Install the packages and check the setup
./bootstrap.sh

# 4. Start the system
LANL_DEV=1 venv/bin/python -m live.app

# 5. Open the dashboard
#    The address is http://localhost:5000
```

The script fetches 1.5 GB from Git LFS. It does not fetch the database. Copy
`lanl.duckdb.zst` into `data/raw/lanl/` before you run the script. A memory
stick or a phone cable works. See `SETUP.md` for the instructions.

## Dataset

The file `lanl.duckdb` contains these tables.

| Table | Rows | Use |
|-------|------|-----|
| `feat` | 29,905,488 | 21 features for each event |
| `auth_slice` | 29,905,488 | Raw authentication events |
| `redteam` | 749 | 104 red team attackers, one row per event |

The `feat` table has 702 rows where `is_red` is true. The system found 598 of
these rows.

The system scores the events as follows.

1. The feature engine computes 21 features for each event.
2. The LSTM autoencoder computes the reconstruction error. This is feature 21.
3. LightGBM computes the risk score.
4. The threshold module sets the decision. The value is BLOCK above 0.1872, FLAG
   above 0.131, or ALLOW for all other values.

## Results

The team tested the model on a held-out set. The split groups the data by user.
No user appears in both the training set and the test set.

| Metric | Value |
|--------|-------|
| PR-AUC | 0.3682 |
| ROC-AUC | 0.9999 |
| F1 | 0.4866 |
| True positives | 136 of 240 |
| False positives | 183 of 5,399,886 |

PR-AUC is the figure to read. Attacks are 240 in 5,399,886, so a random
ranker scores 0.000044 and this model scores 0.3682, which is about
8,285 times the random baseline. ROC-AUC is 0.9999, but at this class
ratio it is near-saturated by construction and does not separate a useful
model from an unhelpful one. The dashboard leads with PR-AUC for that
reason.

Over the complete dataset the system found 598 of 702 attacks. This is 85.2%.

## Retraining

You do not have to retrain for the demo. The models are in the repository.

To retrain the Isolation Forest and LightGBM, run:

```bash
venv/bin/python src/03_retrain_both.py --verbose
```

The run uses about 6 GB of RAM. It takes about 5 minutes.

To rebuild the dataset from the original LANL archive, run:

```bash
unzip -p ~/Downloads/archive.zip auth.txt/auth.txt | venv/bin/python src/00_build_slice.py count
unzip -p ~/Downloads/archive.zip auth.txt/auth.txt | venv/bin/python src/00_build_slice.py slice
venv/bin/python src/00_build_slice.py load
venv/bin/python src/01_build_features.py
venv/bin/python src/02_feature_probe.py
```

## Tests

Start the server first. Then run:

```bash
venv/bin/python test_live.py        # 9 checks, including the browser
venv/bin/python live/test_audit.py  # 36 checks
```

Both scripts require Playwright. Run `./bootstrap.sh --deps-only` first, then
`venv/bin/pip install playwright && venv/bin/playwright install chromium`.

## Documentation

| File | Content |
|------|---------|
| `SETUP.md` | Installation and running |
| `LIVE_README.md` | Architecture of the live system |
| `docs/model_deep_dive.md` | Model design |
| `docs/FEATURE_ENGINEERING_SUMMARY.md` | Feature design |
| `reports/experiment_log.md` | All 14 runs |