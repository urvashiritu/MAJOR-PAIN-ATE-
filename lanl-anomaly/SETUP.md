# LANL Anomaly Detection — Installation and Running

This system finds abnormal authentication activity. It scores 29,905,488
authentication events from Los Alamos National Laboratory.

## Installation

```bash
# 1. Get the code
git clone -b feature/lanl-rebuild https://github.com/urvashiritu/MAJOR-PAIN-ATE-.git
cd MAJOR-PAIN-ATE-/lanl-anomaly

# 2. Copy the database into this directory before you continue
#    Copy lanl.duckdb.zst (5.6 GB) into data/raw/lanl/
#    See "Copying the database" below.

# 3. Install Git LFS
sudo apt install git-lfs zstd
git lfs install

# 4. Install the packages and check the setup
./bootstrap.sh

# 5. Start the system
LANL_DEV=1 venv/bin/python -m live.app
```

Then open `http://localhost:5000` in a browser.

The replay starts by itself. The dashboard has data when the system is ready.

## Hardware and software requirements

| Item | Requirement |
|------|-------------|
| Operating system | Linux, or Windows using WSL |
| Python | 3.12 or later |
| Git | With Git LFS |
| Disk space | 12 GB or more |
| RAM | 16 GB or more |
| GPU | Not necessary |

The models use the CPU. The script installs the CPU version of PyTorch by
default. This install uses about 1 GB. Set `USE_GPU=1` to install the CUDA
version. That install uses about 5.9 GB.

## Running on a second machine

Run `./bootstrap.sh` again. The script continues an install that stopped. The
script does not change a correct file.

## Copying the database with a cable or a memory stick

The script does not download the database. You must copy the file to the
computer. Use a memory stick, a phone cable, or a network share.

1. Copy `lanl.duckdb.zst` (5,613,536,885 bytes) to the new computer. The file
   name must stay `lanl.duckdb.zst`.
2. Put the file in this directory:
   ```
   <repo>/data/raw/lanl/
   ```
3. Run the script:
   ```bash
   ./bootstrap.sh
   ```

The script finds the file and decompresses it. The script does not use the
network for the database.

You can also copy `lanl.duckdb` (10,399,002,624 bytes) instead. The script uses
this file directly and does not decompress it.

## Checking a machine without changing it

Run:

```bash
./bootstrap.sh --verify
```

The check confirms these items.

1. The file `lanl.duckdb` has the correct size.
2. The database opens and the table `feat` has 29,905,488 rows.
3. The count of red team events is 702.
4. The two model files exist.
5. The parquet file has 29,905,488 rows.

## Settings for the installation

| Name | Default | Meaning |
|------|---------|---------|
| `USE_GPU` | `0` | Set `1` to install the CUDA version of PyTorch |
| `VENV` | `venv` | The directory for the virtual environment |

## Settings for running

| Name | Default | Meaning |
|------|---------|---------|
| `LANL_DEV` | not set | Show the passwords and the TOTP codes on the login page |
| `LANL_AUTOPLAY` | `1` | Start the replay when the system starts. Set `0` to start it with the Play button |
| `LANL_REPLAY_SPEED` | `20` | Events each second. The range is 1 to 500 |

**Warning:** `LANL_DEV` shows real passwords and real TOTP codes. Do not use this
setting on a server that the public internet can reach.

## Data

The file `data/raw/lanl/lanl.duckdb` has a size of 9.7 GiB. It contains these
tables.

| Table | Rows | Use |
|-------|------|-----|
| `feat` | 29,905,488 | 21 features and 16 latent values for each event |
| `auth_slice` | 29,905,488 | The raw authentication events |
| `redteam` | 749 | 104 red team attackers, one row per event |
| `redteam_distinct` | 715 | The red team attackers |

The `feat` table has 702 rows where `is_red` is true. The system found 591 of
these rows.

Git LFS does not carry this file. GitHub does not accept a Git LFS file that is
bigger than 2 GB on the free plan. This file is 9.7 GiB. You must copy the file
to each computer.

Copy the compressed file instead. It is 2.78 times smaller:

| File | Size |
|------|------|
| `lanl.duckdb` | 10,399,002,624 bytes |
| `lanl.duckdb.zst` | 5,613,536,885 bytes |

To make the compressed file, run:

```bash
zstd -19 -T0 -f data/raw/lanl/lanl.duckdb -o data/raw/lanl/lanl.duckdb.zst
```

The disk needs 14 GB during the setup. The disk needs this space for the
compressed file and for the database.

Git LFS carries the models and the parquet files. The total size is 1.5 GB.

```bash
git lfs install
git lfs pull
```

## How the system works

The system processes each event in these steps.

1. The feature engine computes 21 features.
2. The LSTM autoencoder computes the reconstruction error. This is feature 21.
3. LightGBM computes the risk score.
4. The threshold module sets the decision.

The decision rules are as follows.

| Condition | Decision |
|-----------|----------|
| The score is above 0.187195 | BLOCK |
| The score is above 0.131 | FLAG |
| The score is any other value | ALLOW |

The model metrics for a held-out set are as follows.

| Metric | Value |
|--------|-------|
| ROC-AUC | 0.9999 |
| F1 | 0.4866 |
| True positives | 136 of 240 |
| False positives | 183 of 5,399,886 |

The test set has 5,399,886 events. Of these, 240 are attacks.

## Retraining the models

You do not have to retrain the models for a demonstration. The models are in the
repository.

To retrain the Isolation Forest and LightGBM, run:

```bash
venv/bin/python src/03_retrain_both.py --verbose
```

The run uses about 6 GB of RAM. It takes about 5 minutes. It writes
`models/lanl_if.joblib` and `models/lanl_lgb.joblib`.

To rebuild the data from the original LANL archive, run:

```bash
unzip -p ~/Downloads/archive.zip auth.txt/auth.txt | venv/bin/python src/00_build_slice.py count
unzip -p ~/Downloads/archive.zip auth.txt/auth.txt | venv/bin/python src/00_build_slice.py slice
venv/bin/python src/00_build_slice.py load
venv/bin/python src/01_build_features.py
venv/bin/python src/02_feature_probe.py
```

You must download `archive.zip` first. The file has a size of 7.1 GB.

## Project structure

```
lanl-anomaly/
├── data/
│   ├── raw/lanl/
│   │   ├── lanl.duckdb          # 9.7 GiB. The script downloads this file
│   │   ├── users.txt            # 604 users
│   │   ├── redteam.txt          # The attackers
│   │   └── *.parquet            # Git LFS
│   └── processed/
│       └── lanl_scores.parquet  # Git LFS, 370 MB
├── models/                      # Git LFS. LGB and LSTM-AE
├── src/                         # The training scripts
│   ├── 00_build_slice.py        # 1.05B events to a 604-user slice
│   ├── 01_build_features.py     # The first 9 features
│   ├── 02_feature_probe.py      # The ROC-AUC of each feature
│   ├── 03_retrain_both.py       # Retrain IF and LGB
│   ├── 04_lstm_surprisal.py     # LSTM surprisal
│   ├── 05_lstm_autoencoder.py   # LSTM autoencoder
│   └── 06_extract_latent.py     # The latent values
├── live/                        # The live system
│   ├── app.py                   # Flask, port 5000
│   ├── scorer.py                # The scoring engine
│   ├── replay.py                # The replay window
│   ├── auth.py                  # Password and TOTP
│   ├── db.py                    # Paths and the feature names
│   ├── scoring.py               # Batch scoring
│   ├── templates/               # Login, analyst, dataset, employee
│   ├── static/                  # CSS, JavaScript, the diagram
│   ├── test_audit.py            # 36 browser checks
│   └── test_blind_event.py      # Blind event tests
├── docs/                        # The documentation
├── reports/                     # The metrics and the run log
├── bootstrap.sh                 # The installation script
├── requirements.txt             # The Python packages
├── SETUP.md                     # This file
└── README.md                    # The project overview
```

## Architecture

```
Browser → http://localhost:5000
  │
  ├── GET  /api/dashboard          → KPIs, events, alerts
  ├── GET  /api/replay/status      → The replay position
  ├── POST /api/replay/start       → Start the replay
  ├── POST /api/replay/stop        → Stop the replay
  ├── POST /api/replay/reset       → Go to the first event
  ├── POST /api/replay/jump_attack → Go to the next attack
  ├── GET  /api/alerts             → The alerts
  ├── GET  /api/users              → The users
  ├── GET  /api/user_profile/<id>  → The baseline for one user
  ├── POST /api/alerts/<id>/ack    → Acknowledge an alert
  ├── GET  /api/model/metrics      → The metrics and the importances
  ├── GET  /api/dataset/dashboard  → The KPIs for all 29.9M events
  └── GET  /events/stream          → SSE
  │
  └── Flask, port 5000
        ├── scorer.py  → 21 features → LGB + LSTM-AE
        ├── replay.py  → The real events
        └── auth.py    → Password and TOTP
```

## Pages

| Address | Page |
|---------|------|
| `/` | Goes to `/analyst`. Signs in as the analyst |
| `/login` | The sign-in page |
| `/analyst` | Live Monitoring |
| `/analyst/dataset` | Dataset Analysis |
| `/#/behavior` | Behavior Insights |
| `/#/model` | Model Performance |
| `/#/alerts` | Alerts |
| `/#/users` | Users |
| `/#/settings` | Settings |

## Tests

Start the system first. Then run:

```bash
venv/bin/python test_live.py
venv/bin/python live/test_audit.py
```

The first script runs 9 checks. The second script runs 36 checks. Both scripts
use Playwright.