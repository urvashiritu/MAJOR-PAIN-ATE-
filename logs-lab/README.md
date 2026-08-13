# Logs-Lab (synthetic login-anomaly experiment)

A self-contained experiment that answers one question: **can machine learning detect
suspicious login behavior from scratch, without being handed an answer key?**

The main project (README) had a "cheat sheet" — the RBA dataset ships a per-IP
attack label, so a blocklist lookup alone scores 0.747 F1. Logs-lab removes that
crutch: it generates ~600k synthetic login events across six sources
(AWS / Entra / Windows / web / MySQL / SSH), labels only **success vs failure**
(no attack tags), and asks the models to find the signal on their own.

## Contents

| Item | What it is |
|---|---|
| `parse_logs.py` | Turns six raw text logs into one `events.parquet`, **verifying per source that every raw line was parsed** (fails loudly otherwise) |
| `train_models.py` | Feature engineering + honest 55/15/30 train/val/test split + 3 models, threshold tuned on the validation slice only |
| `LOGS-LAB.md` | The experiment write-up: methodology, scores, and why they're lower than the earlier numbers |
| `ui/` | Standalone explainable web UI (`make logs-lab-ui-bg` → http://127.0.0.1:5001) — see `ui/README.md` |
| `raw/`, `events.parquet`, `featured_events.parquet`, `models/`, `reports/` | Generated artifacts (gitignored, rebuilt by `make logs-lab-prepare`) |

## Run the whole thing

```bash
make logs-lab-prepare    # parse (with per-source verification) -> features -> train
make logs-lab-ui-bg      # launch the explainable UI on http://127.0.0.1:5001
```

## The honest numbers (test set, never tuned on)

| Model | F1 | Precision | Recall | ROC-AUC |
|---|---|---|---|---|
| **Hist Gradient Boosting** | **0.155** | 0.224 | 0.118 | 0.693 |
| Logistic Regression | 0.109 | 0.148 | 0.087 | 0.663 |
| Isolation Forest | 0.086 | 0.149 | 0.060 | 0.532 |

Detection is genuinely hard here: ~89% of events are successful logins, there are
no attack labels, and a typos/forgotten passwords count as "failures" just like
attacks. The earlier, prettier numbers (F1 0.199, ROC-AUC 0.711) were inflated by
a parser bug that made SSH look 100% failed and by tuning the threshold on the test
set itself — both are fixed, so these numbers are the real ones.

## Why this exists next to the main project

The main project proved behavior can't predict a per-IP blacklist label. Logs-lab
is the follow-up: with clean synthetic data and an honest evaluation protocol,
does behavior alone carry any signal? The answer — about 0.15 F1, above the 0.02
a coin flip would give — says "a little, and here's exactly what the model leans on"
(see the UI's per-event explanations).