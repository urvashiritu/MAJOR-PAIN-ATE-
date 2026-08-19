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
src/04_rule_baseline.py    points system → rule scores   (the live decision layer)
   │
   ▼
src/07_ensemble_full.py   anomaly models on the FULL 1M sample → reports/, models/
```

Two things to notice: features run before sampling (a sampled event carries the exact
feature the live system would compute), and `02` runs before `01`. The order is
`00 → 02 → 01 → 03 → 04 → 07`. The rules engine is what decides in the live demo;
`07` is the model experiment that compares anomaly detectors head-to-head on the full
sample.

---

## Current state (Aug 19, 2026)

Phases 0–8 are done (the live demo app shipped Aug 11–12). Every gate passes.
The honest evaluation is in `reports/`.

### What the numbers mean (in plain words)

The simplest way to read the results — three honest facts:

1. **A blocklist beats every behavior model.** Just looking up "is this IP on a bad-IP
   list" scores **0.75**, while our best machine-learning model scores **0.11**. That's
   because the main attack label *is* a blocklist, not a behavior label. The gap is the
   label's fault, not the model's.
2. **The rules are the practical winner.** When we "double-check" the 10% most suspicious
   logins, the rule engine catches **~79% of real account takeovers** while re-challenging
   ~11% of normal users.
3. **The ML is the honest comparison, not the demo.** All four anomaly models are trained
   on the same full 1M-row sample; the best is the trimmed ensemble (**F1 0.111**), just
   ahead of Local Outlier Factor alone (0.092). (F1 is one number from 0=useless to
   1=perfect balancing "are we right when we flag?" and "do we catch enough?")

> **Why there is no "ML score" in the live demo:** an earlier phase trained a supervised
> HGB model on the gold label (best F1 0.287). Auditing the demo showed that score never
> moved a decision — the features the demo surfaces (new device, foreign login) move it
> the *wrong way*, and its trigger was never reached. The supervised model, the
> subset-trained Phase-6 detectors, and the separate `logs-lab` experiment were removed
> so the demo is honestly **rule-driven**: blocklist → block, rule ≥ 90 → block,
> rule ≥ 45 → flag, otherwise allow.

- **This is a single-dataset study.** We evaluated LANL, CERT R4.2 and Cloud-UEBA as a
  second dataset and rejected them: none has the login columns (country/device/IP/browser,
  success/failure) our shared feature and rule SQL needs, and none provides event-level
  attack ground truth (CERT is user+day, Cloud-UEBA is unlabeled by design). So the
  findings here — blocklist ceiling, 79%-ATO rules replay, 141-ATO needle — are measured
  on RBA alone; transfer to other login telemetry is future work, not a claim.

### Live dashboard vs. dataset browser

The `/dashboard` SPA mixes two data sources, by design. The headline **KPIs, anomaly
trend, risk distribution, activity-by-hour and top reasons come from the live demo
database** (`events` where `decision != 'history'`) and tick as logins are scored. The
**world map, scatter plot and Dataset page read the offline 1M-row scored sample** — that
page is the "show the cleaned dataset" view, not live traffic.

### What was done, phase by phase (plain words)

| Phase | What we did | In one sentence |
|---|---|---|
| 0–2 | Scope, environment, dataset audit | Decided what to build and studied all 31.3M rows (found the messy parts, and the big discovery: the main label is a blocklist) |
| 3 | Cleaning + sampling | Fixed the messy values, then picked 1M representative rows — keeping all 141 takeover rows and capping one "robot" user that was 45% of the data |
| 4 | Feature engineering | 21 features per login: new country? new device? failed login 5 min ago? rapid burst? unusual hour? — all computed over the user's real history |
| 5 | Rule baseline | A bouncer's checklist: new country +30, new IP +25, recent failure +20, ... → low / medium / high / critical, with written reasons |
| 6 | Anomaly models | 4 models that learn "what is normal" and flag the unusual — compared honestly on the full 1M sample; the trimmed ensemble won at 0.111 |
| 7–8 | Live demo app | Flask app + DuckDB: personas seeded from the real sample, every login scored live by the exact training SQL (rule engine), verdict/blocked/challenge pages, admin dashboard with live push, user profiles + JSON API |

### Repo contents

- `data/raw/rba-dataset.csv` — raw RBA dataset (8.5 GB, 31.3M events, Zenodo)
- `data/processed/rba_clean.parquet` — cleaned (same row count, flags added)
- `data/processed/rba_features.parquet` — features over all 31.3M rows
- `data/processed/sample.parquet` + `features.parquet` — 1M-row training table
- `data/processed/user_baselines.parquet` — per-user history over all 31.3M rows
- `data/live.duckdb` — live demo DB (users, events, alerts, user_profile)
- `src/00_clean_dataset.py` → `src/02_feature_engineering.py` → `src/01_load_and_sample.py` → `src/03_validate_contract.py` → `src/04_rule_baseline.py` → `src/07_ensemble_full.py`
- `live/` — Flask demo: `app.py` (web + JSON API + SSE), `db.py` (schema + profiles), `scoring.py` (shared rule SQL), `ua.py` (User-Agent parsing), `seed_demo.py` (personas), `templates/`, `web/` (React dashboard)
- `reports/` — rule scores, model comparison, ensemble evaluation, replay analysis, evaluation JSONs
- `models/ensemble_full.joblib` — the full-sample ensemble + scaler + tuned thresholds (the model deliverable; not loaded by the live app)

---

## How to run everything

```bash
venv/bin/python src/00_clean_dataset.py          # ~30 s
venv/bin/python src/02_feature_engineering.py    # ~8 min, full 31.3M pass
venv/bin/python src/01_load_and_sample.py        # ~2 min
venv/bin/python src/03_validate_contract.py      # must print PASS
venv/bin/python src/04_rule_baseline.py          # ~1 min
venv/bin/python src/07_ensemble_full.py          # ~3 min (trains all models on the full 1M sample)
```

Run them in that order (note: the file numbers are phase numbers — `01` runs
*third*). Each script writes a report next to its output. If `03` fails,
the inputs are stale — rebuild.

Or use the Makefile, which encodes the order for you (each target rebuilds
its inputs only when they are stale):

```bash
make all          # full pipeline 00 -> 02 -> 01 -> 03 -> 04 -> 07
make clean features sample validate rules ensemble-full   # any stage
```

## Running the live demo

```bash
venv/bin/python live/seed_demo.py   # (re)create data/live.duckdb with persona history
venv/bin/python live/app.py         # http://127.0.0.1:5000
```

- `/` login form (persona cards + custom event) · `/dashboard` SPA · `/admin` redirects to it
- score a login from another machine (demo): `POST /events` with JSON
  `{"user_id": <id>, "country": "FR", ...}` — all endpoints return JSON:
  `GET /risk/<event_id>` · `GET /users/<user_id>/profile` · `GET /alerts`
- the dashboard updates live over SSE (`GET /events/stream`) — no refresh

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
2. ~~Documented metrics (94.2%/91.7%/88.3%) are not reproducible~~ — **RESOLVED (Aug 9):** Phase 6 measures and reports honestly; the old claim is gone. See `reports/ensemble_full_comparison.csv`.
3. ~~`failed_before_success` semantics~~ — **RESOLVED (Aug 8):** real 5-minute lookback, renamed `failed_recently`.
4. ~~`contamination` must not be hardcoded~~ — **RESOLVED (Aug 9):** models fit on clean rows only; contamination 0.10 is the flag-rate intent; the measured train attack share (0.2504) is reported alongside.
5. ~~rule points must be tuned, not constants~~ — **RESOLVED (Aug 9):** weights follow the takeover-behavior ordering; level bounds kept at 30/65/90 with rationale in `src/04_rule_baseline.py`.
6. **RESOLVED (Aug 8):** `geo_unreliable` duplicate, iOS/Mobile substring mislabels, device short-circuit, `Andorid` typo, non-deterministic sampling, hardcoded `fixed_rows`, `prior_fail_ts` leak, `failed_before_success` misnomer — all fixed and guarded by `src/03_validate_contract.py`.
