# AI-Based Identity Anomaly Detection System

**Team:** Hemanth Kumar KS (1SK23CS020) | Urvashi Tanwar (1SK23CS055) | Veenashree S T (1SK23CS057) | Vishwanath Sanapur (1SK23CS059)
**Guide:** Dr. Anitha A C — Government Sri Krishnarajendra Silver Jubilee Technological Institute, CSE

---

## The project in one paragraph (plain words)

Think of the system as a **bouncer at a nightclub** — but for login events.

Every time someone logs in, the system asks: *"Is this how this user normally behaves?"*
A normal login (usual time, usual country, usual device) gets a **green light**. A strange
login (new country, new device, 3am, failed attempts just before) gets a **red flag** with
a written explanation of *why*.

The system was trained on **31 million real login events** from a published academic
dataset (RBA, from Telenor Norway). During the live demo, login events arrive from a
second laptop, get scored in real time, and appear on a dashboard as safe (green) or
suspicious (red), with the reasons shown for every decision.

### The one finding that shapes everything

While analyzing the dataset, we discovered something important:

- The dataset's main attack label (`is_attack_ip`) is **not about behavior at all** —
  it's an **IP blacklist** (a list of "bad" IP addresses). The same IP always gets the
  same label.
- A model that studies *behavior* can never learn to predict a *list*. We proved this
  honestly with numbers (see "What the numbers mean" below).
- The real behavioral signal is `is_ato` (account takeover — a hacked account), but
  there are only **141** such events in 31 million rows — a needle in a haystack.

> **Dataset warning:** the RBA dataset (Zenodo 6782156) is **synthesized** — statistically
> recreated from real Telenor login patterns by the authors, who state the feature values
> are "totally artificial" and **not for production systems**. We use it as a benchmark for
> academic/demo purposes only.

---

## Plain-English glossary

| Word | What it means, simply |
|---|---|
| **Row / event** | One login attempt: who, when, from which country, on which device, did it succeed |
| **Feature** | A single number computed from a row (e.g. `hour`, `country_change`, `ip_seen_before`) |
| **Label** | The truth: is this row an attack (1) or not (0). The model tries to predict this |
| **Blocklist label** | A label decided per IP, not per behavior. `is_attack_ip` is one: the same IP is always 1 or always 0 |
| **Gold label** | Our tuning target: `is_attack_ip` AND the login succeeded. A successful login from a blocked IP |
| **ATO** | Account Takeover — a real account got hacked (141 rows in the data; the behavioral gold standard) |
| **Sampling** | Picking a smaller, representative chunk out of the big dataset (31M rows don't fit in memory) |
| **Train/test split** | Train the model on part A, test it on part B it never saw. If it works on part B, it works on new events |
| **F1 score** | One number that balances "how often you're right when you flag" and "how many attacks you catch" (0 = worst, 1 = perfect) |
| **FPR** | False positive rate: the fraction of normal events we wrongly flag (our budget: 5%) |
| **Replay** | "If we double-check the top X% most suspicious logins, how many attacks do we catch, and how many normal users do we bother?" |
| **Challenge rate** | The fraction of events we pick for a second check (e.g. 10%) |

---

## The pipeline in one picture

```
raw CSV  (31.3M events)
   │  src/00_clean_dataset.py              ~30 s
   ▼
rba_clean.parquet  (cleaned, flags added)
   │  src/02_feature_engineering.py        ~8 min over the FULL 31.3M rows
   ▼
rba_features.parquet  (features per event)
   │  src/01_load_and_sample.py            ~2 min, samples from the featured table
   ▼
sample.parquet / features.parquet  (1M events, 192,649 users)
   │  src/03_validate_contract.py          seconds, must print PASS
   ▼
src/04_rule_baseline.py    points system → rule scores
   │
   ▼
src/05_models_evaluation.py  anomaly models, thresholds, replay → reports/
   │
   ▼
src/06_supervised_model.py   supervised models on the gold label → reports/
```

Two things to notice: features run before sampling (a sampled event carries the exact
feature the live system would compute), and `02` runs before `01`. The order is
`00 → 02 → 01 → 03 → 04 → 05 → 06`.

---

## Current state (Aug 11, 2026)

Phases 0–6 are done. Every gate passes. The honest evaluation is in `reports/`.

### What the numbers mean (in plain words)

We tune everything on the **gold label** (successful login from a blocked IP) with a
false-positive budget of 5%. Results on the test set (212,233 events the models never saw):

| Model | Gold F1 | FPR | What it tells us |
|---|---|---|---|
| Rule baseline (10 rules) | 0.002 | 2.0% | Catches the takeover tail: **79% of ATO rows at 10% challenge**, 11% of normal events re-challenged |
| IP blocklist prior (no ML) | 0.747 | 9.3% | The **ceiling**. A per-IP lookup alone beats every behavior model, because the label is per-IP |
| Isolation Forest | 0.006 | 5.0% | Weak, as expected |
| Local Outlier Factor (Phase 6 winner) | 0.110 | 5.0% | Best of the 4 anomaly models, ROC-AUC 0.56 |
| One-Class SVM | 0.001 | 5.0% | Weak, as expected |
| Elliptic Envelope | skipped | — | Feature skew 24.85 > 2.0 limit |
| **Supervised HGB (Phase 6 extension)** | **0.287** | **5.0%** | **2.6× better** than LOF: a supervised model trained on the gold label itself. ROC-AUC 0.75 |
| **Supervised Logistic Regression** | **0.180** | **5.0%** | Second opinion; readable coefficients, proves the signal isn't a fluke |

The honest one-liner:

- **Behavior cannot predict a blocklist.** The IP prior scores 0.75 with zero machine
  learning; that gap is the label's fault, not the models'.
- **Supervised learning on the gold label improves behavioral detection 2.6×** (0.110 → 0.287),
  but the blocklist ceiling still stands — the label is the limit, not the methods.
- The behavioral value shows in the replay report (`reports/replay_analysis.csv`): at the
  10% challenge rate, the rules flag ~79% of true account takeovers while re-challenging
  ~11% of normal events.
- The rules are our demo workhorse; the models are the comparison.

### What was done, phase by phase (plain words)

| Phase | What we did | In one sentence |
|---|---|---|
| 0–2 | Scope, environment, dataset audit | Decided what to build and studied all 31.3M rows (found the messy parts, and the big discovery: the main label is a blocklist) |
| 3 | Cleaning + sampling | Fixed the messy values, then picked 1M representative rows — keeping all 141 takeover rows and capping one "robot" user that was 45% of the data |
| 4 | Feature engineering | 21 features per login: new country? new device? failed login 5 min ago? rapid burst? unusual hour? — all computed over the user's real history |
| 5 | Rule baseline | A bouncer's checklist: new country +30, new IP +25, recent failure +20, ... → low / medium / high / critical, with written reasons |
| 6 | Anomaly models | 4 models that learn "what is normal" and flag the unusual — compared honestly; LOF won at 0.110 |
| 6+ | Supervised models | The same features, but trained *with* the gold label as the answer key → 0.287, a 2.6× improvement |

### Repo contents

- `data/raw/rba-dataset.csv` — raw RBA dataset (8.5 GB, 31.3M events, Zenodo)
- `data/processed/rba_clean.parquet` — cleaned (same row count, flags added)
- `data/processed/rba_features.parquet` — features over all 31.3M rows
- `data/processed/sample.parquet` + `features.parquet` — 1M-row training table
- `data/processed/user_baselines.parquet` — per-user history over all 31.3M rows
- `src/00_clean_dataset.py` → `src/02_feature_engineering.py` → `src/01_load_and_sample.py` → `src/03_validate_contract.py` → `src/04_rule_baseline.py` → `src/05_models_evaluation.py` → `src/06_supervised_model.py`
- `reports/` — rule scores, model comparison, threshold curves, replay analysis, evaluation JSONs
- `models/final_model.joblib` — the Phase 6 Local Outlier Factor + scaler + threshold

---

## How to run everything

```bash
venv/bin/python src/00_clean_dataset.py          # ~30 s
venv/bin/python src/02_feature_engineering.py    # ~8 min, full 31.3M pass
venv/bin/python src/01_load_and_sample.py        # ~2 min
venv/bin/python src/03_validate_contract.py      # must print PASS
venv/bin/python src/04_rule_baseline.py          # ~1 min
venv/bin/python src/05_models_evaluation.py      # ~3 min
venv/bin/python src/06_supervised_model.py       # ~1 min
```

Run them in that order. Each script writes a report next to its output. If `03` fails,
the inputs are stale — rebuild.

## Docs

| Doc | What it covers |
|---|---|
| `README.md` | This file: overview, pipeline picture, current state, run commands |
| `dataset_scan_report.md` | Full-scan quality audit of all 31.3M rows + cleaning solution, in plain words |
| `PROJECT_ROADMAP.md` | Implementation plan, phases 0–11, in plain words |
| `COMPLETE_PROJECT_REFERENCE.md` | Slim plain-English reference: metrics explained, honest findings, demo script, viva Q&A |

Reading order: README → roadmap → scan report → reference.

## Known Issues (all resolved)

1. ~~Training data has only 248 attack examples (1.36%)~~ — **RESOLVED (Aug 8):** whole-user sampling yields 1,000,003 rows with a 24.76% natural attack share.
2. ~~Documented metrics (94.2%/91.7%/88.3%) are not reproducible~~ — **RESOLVED (Aug 9):** Phase 6 measures and reports honestly; the old claim is gone. See `reports/model_comparison.csv`.
3. ~~`failed_before_success` semantics~~ — **RESOLVED (Aug 8):** real 5-minute lookback, renamed `failed_recently`.
4. ~~`contamination` must not be hardcoded~~ — **RESOLVED (Aug 9):** models fit on clean rows only; contamination 0.10 is the flag-rate intent; the measured train attack share (0.2504) is reported alongside.
5. ~~rule points must be tuned, not constants~~ — **RESOLVED (Aug 9):** weights follow the takeover-behavior ordering; level bounds kept at 30/65/90 with rationale in `src/04_rule_baseline.py`.
6. **RESOLVED (Aug 8):** `geo_unreliable` duplicate, iOS/Mobile substring mislabels, device short-circuit, `Andorid` typo, non-deterministic sampling, hardcoded `fixed_rows`, `prior_fail_ts` leak, `failed_before_success` misnomer — all fixed and guarded by `src/03_validate_contract.py`.
