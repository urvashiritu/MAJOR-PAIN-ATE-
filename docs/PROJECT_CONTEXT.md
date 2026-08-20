# MAJOR-PAIN-ATE — Full Project Context (for a new coder)

## 1. What this project is

**Real-Time User Identity Anomaly Detection Using Behavioral Login Profiles.** A login-security system that:

1. learns what *normal* looks like for each user,
2. flags *unusual* authentication events,
3. explains **why** each event was flagged,
4. shows decisions live on a security-operations dashboard.

It's not "AI tells you suspicious." It's *"the system learned Alice's identity — usual computers, usual hours, usual failure rate — then compared a real event against that identity, explained the deviation, and acted."*

## 2. The one idea everything hangs on: two datasets, two outcomes

The project studied two datasets. The whole story is **why ML honestly fails on one and works on the other.**

### Dataset 1 — RBA (Zenodo, Wiefling et al., synthesized)

- 31.3M login events, 4.3M users, ~13 months. Rich: IP, country, device, browser, OS, ASN.
- **But it's synthesized** (a program generated it — the scan even found the generator's URL stamped inside fake browser strings).
- Its attack label `Is Attack IP` is an **IP blocklist** — same IP always same label.
- **Result:** ML loses to a simple lookup. Best anomaly ensemble gold F1 **0.111** vs the blocklist's **0.747**. Only **141 Account Takeover** rows (a tiny positive set).
- **Lesson:** ML failed here because the label is a *shortcut* — a lookup beats a model at predicting a lookup.

### Dataset 2 — LANL Cyber1 (Los Alamos National Laboratory, real)

- **1,051,430,459 real auth events**, 80,553 users, ~58 days.
- **No IPs, no countries, no devices.** Just: `time, src_user, dst_user, src_computer, dst_computer, auth_type, logon_type, orientation, result`.
- Ground truth: the **red team** compromised 104 real accounts (attacker machines C17693/C19932/C22409/C18025; **702 events** verified in the data).
- **Result:** behavioral features separate real attacks from normal behavior — per-feature AUCs **0.65–0.97** (destination-familiarity 0.97, unusual-hour 0.71, failure-burst 0.66, first-visit-destination 0.65, velocity 0.81 inverted).
- **Lesson:** on LANL there is *no shortcut possible* — behavior is the only signal, so ML can legitimately win.

### The project's central narrative

> *"ML works when the data is honest; it fails when the label is a shortcut. RBA proved the failure. LANL is where ML is genuinely the only option."*

## 3. What already exists (verified, don't redo)

### LANL pipeline (fully done + independently audited)

- `data/raw/lanl/`: `slice.parquet` (29,905,488 events for **604 users** = 104 compromised + 500 normal), `feat.parquet` (same rows + 18 feature columns), `redteam.txt` (749 lines / 715 distinct / 104 users), `users.txt`, `lanl.duckdb` (tables: `auth_slice`, `feat`, `redteam`, `redteam_distinct`).
- `src/lanl_stream.py` (streamed the 73.4 GB file via `unzip -p`, never wrote it to disk — only 32G free), `src/lanl_features.sql` (feature SQL), `src/lanl_probe.py` (separation probe).
- `reports/lanl_findings.md`, `reports/lanl_feasibility.md`, `reports/lanl_dataset_scan_report.md` — all 7 verification gates passed, all 9 features recomputed with **0 mismatches**.

### feat.parquet columns (18) — this is your training input

`time` (INTEGER seconds, 1…5,011,199), `src_user`, `dst_user`, `src_computer`, `dst_computer`, `auth_type`, `logon_type`, `orientation`, `result`, `hour` (float hour-of-day `(time%86400)/3600`), `is_red` (BOOLEAN label), `dst_first`, `src_first`, `hour_events`, `user_events`, `dst_prior_events`, `fail_1h`, `vel_1h`.

**Model inputs = 8:** 6 core behavioral (`dst_first`, `src_first`, `hour_ratio = hour_events/user_events` computed in code, `dst_prior_events`, `fail_1h`, `vel_1h`) + 2 temporal (`hour_sin`, `hour_cos` derived at train time from `hour` — they are NOT columns).

### RBA pipeline (research/demo history)

- `data/processed/` holds cleaned/sampled/featured RBA artifacts.
- `src/00_clean_dataset.py` → `02_feature_engineering.py` → `01_load_and_sample.py` → `03_validate_contract.py` → `04_rule_baseline.py` → `07_ensemble_full.py`.
- `src/_shared.py` = shared eval helpers (SEED=42, SPLIT_RATIO=0.7, FPR_BUDGET=0.05, `metrics_at`, `tune_threshold`, `replay_rows`).
- `src/07_ensemble_full.py` = the training pattern to mirror (IsolationForest, LOF(novelty), **SGDOneClassSVM — linear**, EllipticEnvelope; contamination = train attack share; rank-average ensembles; threshold tuned on gold under FPR≤5%).
- The current live demo (`live/`) is a **rule engine** (blocklist → block, rule score ≥90 → block, ≥45 → flag). It was deliberately "de-ML'd" (commit `cfac0bd`). **This is what we're replacing.**

## 4. The locked decision (Fork A)

**Rebuild the live demo on LANL, with the trained ML model as the SOLE scorer. Rules are gone. Nothing fake.**

- The dashboard follows a detailed SOC-analyst design ("Design 1"): dark blue, dense, source→destination arrow as the visual hero, real tuned threshold bands on the risk scale, a "WHY WAS THIS FLAGGED?" panel comparing the event to the user's baseline, a user-baseline panel with trust/update status, an event pipeline, and a "normal vs attack" story.
- **Demo personas:** 3 normal users + **U748@DOM1 as the attacker persona** — its own real (non-red) history as baseline, and its **real 26 red-team events as the live attack payload**.

## 5. Locked architecture

```
                    LANL Cyber1
                         │
                         ▼
                 Historical Events
                         │
                         ▼
                ┌─────────────────┐
                │ Feature Builder │  src/lanl_features.py  (training == live, contract-tested)
                └────────┬────────┘
                         │  per-user chronological split
             ┌───────────┴──────────┐
             ▼                      ▼
          TRAIN                   TEST
             │
             ▼
    IF / LOF / SGDOneClassSVM / EE
             │
             ▼
         Ensemble (rank-average)
             │
             ▼
     Threshold calibration (FPR ≤ 5%)
             │
             ▼
       Model artifact  models/lanl_ensemble.joblib
             │
       ──────┼──────────────
             │
             ▼
       LIVE BACKEND (Flask)
Laptop 2 ──► API → event validation → same feature code → baseline → ML inference
             → risk + reasons → DB → SSE
             │
             ▼
         Laptop 1: SOC Dashboard (Design 1)
```

## 6. Execution plan (validated)

- **Phase 0 — Cleanup:** move RBA live code (`live/scoring.py`, `seed_demo.py`, `ua.py`, `geolocation.py`) to `legacy/rba/`; README narrative: *"RBA was evaluated first and demonstrated why shortcut labels mislead; the live system moved to LANL Cyber1."* No legacy route.
- **Phase 1 — Feature contract:** `src/lanl_features.py` — one parametrized SQL template (8 inputs) used by training AND live. Golden-case test: `U748@DOM1, C17693 → C332, t=155591` must always yield `dst_first=1, src_first=0, dst_prior_events=0, fail_1h=0, vel_1h=148, hour≈19.22`.
- **Phase 2 — Train:** `src/lanl_train.py` mirroring `07_ensemble_full.py`; split = `PARTITION BY src_user ORDER BY time` (+ deterministic tiebreak for duplicate (time, src_user) rows); baselines = **Oracle attacker-source blocklist** (src_computer in {C17693,C19932,C22409,C18025}) + random; risk bands derived from the validation distribution; artifacts `models/lanl_ensemble.joblib` + `reports/lanl_ensemble_report.json` + `reports/lanl_train_report.md`.
- **Phase 2.5 — Offline replay harness:** `src/lanl_replay.py` + `make lanl-replay-demo`. Prints a normal event → ALLOW and the real attack sequence → escalating risk → BLOCK. **Gate: must pass before any web code.**
- **Phase 3 — Live backend:** rework `live/db.py` (LANL schema; users keyed by VARCHAR `src_user`), new `live/lanl_scoring.py` (model-dominant; `refresh_profile` **only on ALLOW** — flag/block quarantined), `live/seed_lanl_demo.py`, rework `live/app.py` routes/templates/SSE. Keep SSE machinery, `_jdict`, `_fmt_ts`, ack logic.
- **Phase 4 — Dashboard (Design 1):** rebuild `live/web/src` SPA. Replace `WorldMap`, `DatasetPage`, `UsersPage`, `LoginTable` columns, `InvestigationDrawer` (remove fake "AI/Ensemble Confidence" at `InvestigationDrawer.jsx:88-114` fed by `app.py:731-734`). Reuse `KpiRow`, `ChartGrid`, layout, hooks.
- **Phase 5 — Docs/report:** honest numbers, oracle-baseline caveat, risk-score caveat.

## 7. Gotchas the validation found (read before coding)

1. **U748's 26 red events are NOT all from C17693** — 3 come from **C18025** (times 210086/210294/210312 → C1493). For the demo payload either replay the **23 C17693 events** (clean "attacker machine" story) or replay all 26 (accurate but mixed source).
2. **"Typical auth = Kerberos" is imprecise** — U748's normal mode is `'?'` (64.6%), Kerberos 30%, NTLM 5.2%. Red events are **100% NTLM** (26/26 U748, 702/702 globally). The baseline panel should show this honestly (typical: `?`/Kerberos — current: NTLM → deviation).
3. **LANL user ids are VARCHAR** (`U748@DOM1`) — the Flask `SignedIntConverter` and `int(payload["user_id"])` won't accept them. User routes must switch to string keys; event routes keep numeric `row_id`.
4. **`split_sql` from `_shared` is RBA-coupled** (`PARTITION BY user_id ORDER BY ts, row_id`) — must become `PARTITION BY src_user ORDER BY time` with a deterministic tiebreak.
5. **Use SGDOneClassSVM (linear)**, not kernel OCSVM (O(n²) — infeasible at 30M scale).
6. **`hour_ratio` and `hour_sin/cos` are computed in code**, not stored — keep them consistent between train and live.
7. **702 red events = 715 tuples minus 14 unmatched** (ground-truth quirk: intended vs logged destination; 1 tuple matches 2 rows). The 702 label count is correct — don't "fix" it.
8. **Risk Score is a presentation scale**, anchored to the real tuned thresholds — document as *"not a probability or confidence."*
9. **The oracle baseline is post-hoc** (uses ground-truth machines) — must be labeled as such, never "production blocklist ceiling."

## 8. Conventions & honesty rules (non-negotiable)

- Never fake a result; report ML numbers as measured (even when bad). No silent row deletion.
- Features before sampling; chronological splits only; no future leakage.
- The model is dominant — `auth_type`, unusual source/dest etc. are **model features, never hidden hard-coded block rules**.
- Baseline learns from ALLOW only; FLAG/BLOCK never pollute it (prevents adaptive-detection poisoning).
- Every alert carries an explanation; docs must match the implemented system.
- No comments in code unless asked; surgical changes; verify after every step.

## 9. Key files & commands

```
src/lanl_features.sql      existing feature SQL (offline rebuild reference)
src/lanl_stream.py         streaming parser (count/slice) — done
src/lanl_probe.py          separation probe — done
src/lanl_features.py       NEW: shared feature template (training + live)
src/test_lanl_features.py  NEW: golden-case parity test
src/lanl_train.py          NEW: train ensemble + report
src/lanl_replay.py         NEW: offline replay harness
live/db.py, lanl_scoring.py, seed_lanl_demo.py, app.py   NEW LANL live backend
live/web/src/              NEW dashboard (Design 1)
reports/lanl_train_report.md   NEW honest report
```

New Makefile targets (existing style): `lanl-features`, `lanl-train`, `lanl-replay-demo`, `lanl-seed`, `lanl-demo`. Python via `venv/bin/python`; SPA build `cd live/web && npm run build`.

## 10. The demo story (what the viva sees)

Watch the system learn Alice's identity (usual computers C151/C728/C625/C586; destinations C625/C586/C529/C612; active 06:00–18:00; failure rate 0.05%). Then observe her real compromise unfold: C17693 → C305 (risk 62) → C728 (78) → C5693 (91) → C332 (96, BLOCK) — new source, new destinations, NTLM instead of her normal auth, velocity climbing to 148/hr. The model explains every step against her baseline and blocks the session.