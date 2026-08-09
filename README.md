# AI-Based Identity Anomaly Detection System

**Team:** Hemanth Kumar KS (1SK23CS020) | Urvashi Tanwar (1SK23CS055) | Veenashree S T (1SK23CS057) | Vishwanath Sanapur (1SK23CS059)
**Guide:** Dr. Anitha A C — Government Sri Krishnarajendra Silver Jubilee Technological Institute, CSE

## The project in one paragraph

We watch login events (someone logged in from India on an iPhone at 2pm) and flag the suspicious ones (someone logged in from Russia at 3am on an Android, for this user). We use 4 machine learning models plus an explainable rule score, all trained on **31 million login events** from a published academic dataset (RBA, Telenor Norway). During the demo, login events arrive live from a second laptop, get scored, and show up on a dashboard as green (safe) or red (alert).

One finding shapes everything after Phase 4:

- The dataset's main label (`is_attack_ip`) is an **IP blocklist**, not a behavior label. The same IP always gets the same value.
- A model that studies behavior can never learn to predict a blocklist, and we measured that honestly.
- The real behavioral signal is the `is_ato` label (account takeover, 141 rows).
- Section [What the numbers mean](#what-the-numbers-mean) explains this in plain words.

> **Dataset caveat:** the published RBA dataset (Zenodo 6782156) is **synthesized** — statistically reconstructed from real Telenor Norway login patterns (timestamps randomized, categorical distributions matched, IPs/ASNs reassigned). Per the authors, feature values are "totally artificial" and the dataset is **not for production systems**. It is used here as a benchmark for academic/demo purposes only; `Is Attack IP` is an IP-reputation (blocklist) label, while `Is Account Takeover` is the behavioral gold standard.

### Plain-English glossary

| Word | What it means, simply |
|---|---|
| **Row / event** | One login attempt: who, when, from which country, on which device, did it succeed |
| **Feature** | A single number we compute from a row (e.g. `hour`, `country_change`, `ip_seen_before`) |
| **Label** | The truth: is this row an attack (1) or not (0). The model tries to predict this |
| **Blocklist label** | A label decided per IP, not per behavior. `is_attack_ip` is one: the same IP is always 1 or always 0 |
| **Gold label** | Our tuning target: `is_attack_ip` AND the login succeeded. A successful login from a blocked IP |
| **ATO** | Account Takeover — a real account got hacked (141 rows in the data, the behavioral gold standard) |
| **Sampling** | Picking a smaller, representative chunk out of the big dataset (31M rows do not fit in RAM) |
| **Train/test split** | Train the model on part A, test it on part B it never saw. If it works on part B, it works on new events |
| **FPR** | False positive rate: the fraction of normal events we wrongly flag |
| **Replay** | "If we challenge the top X% most suspicious logins, how many attacks do we catch, and how many normal users do we bother?" |
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
rba_features.parquet  (21 features per event)
   │  src/01_load_and_sample.py            ~2 min, samples from the featured table
   ▼
sample.parquet / features.parquet  (1M events, 192,649 users)
   │  src/03_validate_contract.py          seconds, must print PASS
   ▼
src/04_rule_baseline.py    points system → rule_baseline_scores.parquet
   │
   ▼
src/05_models_evaluation.py  models, thresholds, replay → reports/ + models/final_model.joblib
```

Two things to notice: features run before sampling (a sampled event carries the exact feature the live system would compute), and `02` runs before `01`. The order is `00 → 02 → 01 → 03 → 04 → 05`.

---

## Current state (Aug 9, 2026)

Phases 0–6 are done. Every gate passes. The honest evaluation is in `reports/`.

### What the numbers mean

We tune everything on the **gold label** (successful login from a blocked IP) with a false-positive budget of 5%. Results on the test set (212,233 events the models never saw):

| Model | Gold F1 | FPR | What it tells us |
|---|---|---|---|
| Rule baseline (10 rules) | 0.002 | 2.0% | Catches the takeover tail: 79% of ATO rows at 10% challenge, 11% of normal events re-challenged |
| IP blocklist prior (no ML) | 0.747 | 9.3% | The ceiling. A per-IP lookup alone beats every behavior model, because the label is per-IP |
| Isolation Forest | 0.006 | 5.0% | Weak, as expected |
| **Local Outlier Factor (final)** | **0.110** | **5.0%** | Best behavior model, ROC-AUC 0.56 |
| One-Class SVM | 0.001 | 5.0% | Weak, as expected |
| Elliptic Envelope | skipped | — | Feature skew 24.85 > 2.0 limit |

The honest one-liner:

- **Behavior cannot predict a blocklist.** The IP prior scores 0.75 with zero machine learning; that gap is the label's fault, not the models'.
- The behavioral value shows in the replay report (`reports/replay_analysis.csv`): at the 10% challenge rate, the rules flag ~79% of true account takeovers while re-challenging ~11% of normal events.
- The rules are our demo workhorse; the models are the comparison.

### What changed since the Aug 8 state

- **6 new "seen-before" features** (`ip_seen_before`, `country_seen_before`, `asn_seen_before`, `device_seen_before`, `os_seen_before`, `browser_seen_before`) computed over full history — 21 features total. Full dataset rebuilt, re-sampled, contract PASS.
- **Phase 5 done:** 10 rules with weights tuned against takeover behavior (new country +30, new IP +25, failed login +20, rapid activity +15, unusual hour +15, new ASN +15, device change +10, frequency +10, new OS +7, new browser +7). Risk levels kept at low <30 / medium 30–64 / high 65–89 / critical ≥90 — the gold-tuned optimum (score 77) was rejected because it tripled the false positive rate for +0.15% gold recall.
- **Phase 6 done:** models train on clean rows only (590,491, attack rows excluded), contamination 0.10 as flag-rate intent, thresholds tuned on gold under a 5% FPR budget, an IP-prior baseline kept separate, replay + recall@k + user-level ATO detection reported.
- **Label semantics documented:** `is_attack_ip` is a blocklist (12,583 always-attack IPs, 0 mixed, 229,326 distinct IPs); `is_ato` is the behavioral gold standard.

### Repo contents

- `data/raw/rba-dataset.csv` — raw RBA dataset (8.5 GB, 31.3M events, Zenodo)
- `data/processed/rba_clean.parquet` — cleaned (685 MB, same row count, flags added)
- `data/processed/rba_features.parquet` — 21 features over all 31.3M rows
- `data/processed/sample.parquet` + `features.parquet` — 1M-row training table
- `data/processed/user_baselines.parquet` — per-user history over all 31.3M rows
- `src/00_clean_dataset.py` → `src/02_feature_engineering.py` → `src/01_load_and_sample.py` → `src/03_validate_contract.py` → `src/04_rule_baseline.py` → `src/05_models_evaluation.py`
- `reports/` — rule scores, model comparison, threshold curves, confusion matrices, replay analysis, evaluation JSON
- `models/final_model.joblib` — the trained Local Outlier Factor + scaler + threshold

---

## How to run everything

```bash
venv/bin/python src/00_clean_dataset.py          # ~30 s
venv/bin/python src/02_feature_engineering.py    # ~8 min, full 31.3M pass
venv/bin/python src/01_load_and_sample.py        # ~2 min
venv/bin/python src/03_validate_contract.py      # must print PASS
venv/bin/python src/04_rule_baseline.py          # ~1 min
venv/bin/python src/05_models_evaluation.py      # ~3 min
```

Run them in that order. Each script writes a report next to its output (`cleaning_summary.json`, `features_report.json`, `sampling_report.json`, `rule_baseline_report.json`, `model_evaluation.json`). If `03` fails, the inputs are stale — rebuild.

## Docs

| Doc | What it covers |
|---|---|
| `README.md` | This file: overview, pipeline picture, current state, run commands |
| `dataset_scan_report.md` | Full-scan quality audit of all 31.3M rows + cleaning solution (§7–§8) |
| `PROJECT_ROADMAP.md` | Implementation plan, phases 0–11, definition of done |
| `COMPLETE_PROJECT_REFERENCE.md` | Deep design reference; read its STATUS UPDATE (Aug 9) section first |

Reading order: README → scan report (when you need the numbers) → roadmap → reference.

## Known Issues

1. ~~Training data has only 248 attack examples (1.36%)~~ — **RESOLVED (Aug 8):** whole-user sampling yields 1,000,003 rows with a 24.76% natural attack share.
2. ~~Documented metrics (94.2%/91.7%/88.3%) are not reproducible~~ — **RESOLVED (Aug 9):** Phase 6 measures and reports honestly; the old claim is gone. See `reports/model_comparison.csv`.
3. ~~`failed_before_success` semantics~~ — **RESOLVED (Aug 8):** real 5-minute lookback, renamed `failed_recently`.
4. ~~`contamination` must not be hardcoded~~ — **RESOLVED (Aug 9):** models fit on clean rows only; contamination 0.10 is the flag-rate intent; the measured train attack share (0.2504) is reported alongside.
5. ~~rule points must be tuned, not constants~~ — **RESOLVED (Aug 9):** weights follow the takeover-behavior ordering; level bounds were evaluated against gold and kept at 30/65/90 with the rationale in `src/04_rule_baseline.py`.
6. **RESOLVED (Aug 8):** `geo_unreliable` duplicate, iOS/Mobile substring mislabels, device short-circuit, `Andorid` typo, non-deterministic sampling, hardcoded `fixed_rows`, `prior_fail_ts` leak, `failed_before_success` misnomer — all fixed and guarded by `src/03_validate_contract.py`.
