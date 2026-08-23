# Session Log — `ses_fdb99c330ffe1Kt7wL0kQQQKFJ`

| Field | Value |
|---|---|
| Started | 2026-08-21 18:27 |
| Last activity | 18:33 |
| Title | New session - 2026-08-21T12:57:55.151Z |
| Model | mimo-v2.5-free (opencode, variant: -) |
| Agent/mode | plan |
| opencode | v1.18.20 |
| Tokens in | 49.6K |
| Tokens out | 939 |
| Reasoning | 0 |
| Cache read | 62.0K |
| Cost | $0 |

---


## [18:27] USER

 do a valut of obsidian of this codebase

## [18:27] ASSISTANT

I'll analyze this codebase to create a comprehensive "vault" understanding of it. Let me explore the structure first.

> ⚙ tool: read (completed)

> ⚙ tool: glob (completed)

## [18:28] ASSISTANT

> ⚙ tool: read (completed)

> ⚙ tool: read (completed)

> ⚙ tool: read (completed)

> ⚙ tool: read (completed)

> ⚙ tool: read (completed)

> ⚙ tool: read (completed)

## [18:28] USER

i need to see the graph view

## [18:28] ASSISTANT

Let me map out all the connections to build a graph view. I'll explore the code structure and dependencies.

> ⚙ tool: task (completed)

> ⚙ tool: task (completed)

## [18:32] ASSISTANT

Here's your **Vault Graph View** of the codebase — every concept, file, and data artifact as interconnected nodes:

---

## 🏗️ GRAPH VIEW — Codebase Vault

### Layer 1: Core Data Flow (the backbone)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         OFFLINE TRAINING PIPELINE                          │
│                                                                             │
│  data/raw/rba-dataset.csv                                                  │
│       │  (31.3M events, 8.5 GB)                                            │
│       ▼                                                                    │
│  ┌─────────────────────┐                                                   │
│  │ 00_clean_dataset.py │ ← src/_ua_patterns.py                             │
│  └─────────┬───────────┘                                                   │
│            ▼                                                               │
│  data/processed/rba_clean.parquet                                          │
│            │                                                               │
│            ▼                                                               │
│  ┌──────────────────────────┐                                              │
│  │ 02_feature_engineering.py│  ← defines feature_sql() [CRITICAL]         │
│  └─────────┬────────────────┘                                              │
│            ▼                                                               │
│  data/processed/rba_features.parquet (31.3M + 19 features)                │
│            │                                                               │
│            ├──▶ ┌─────────────────────────┐                                │
│            │    │ 01_load_and_sample.py   │                                │
│            │    └──────────┬──────────────┘                                │
│            │               ▼                                               │
│            │    sample.parquet (1M rows)                                   │
│            │    features.parquet (1M, training table)                      │
│            │    user_baselines.parquet                                     │
│            │               │                                               │
│            │               ▼                                               │
│            │    ┌──────────────────────────┐                               │
│            │    │ 03_validate_contract.py  │──▶ PASS/FAIL gate             │
│            │    └──────────────────────────┘                               │
│            │                                                               │
│            ▼                                                               │
│  ┌─────────────────────────┐                                               │
│  │ 04_rule_baseline.py     │ ← defines score_sql() [CRITICAL]            │
│  └─────────┬───────────────┘                                               │
│            ▼                                                               │
│  reports/rule_baseline_scores.parquet                                      │
│  reports/rule_baseline_report.json                                         │
│            │                                                               │
│            ▼                                                               │
│  ┌──────────────────────────┐                                              │
│  │ 07_ensemble_full.py      │ ← src/_shared.py (SEED, metrics, split)    │
│  └─────────┬────────────────┘                                              │
│            ▼                                                               │
│  reports/model_comparison.csv                                              │
│  models/xgboost_model.joblib                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Layer 2: Live Demo (connected to pipeline via shared SQL)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LIVE DEMO (Flask)                                │
│                                                                             │
│  live/seed_demo.py                                                         │
│       │  reads sample.parquet → writes data/live.duckdb                   │
│       ▼                                                                    │
│  data/live.duckdb ─────────────────────────────────────────┐               │
│  (users, events, alerts, user_profile)                     │               │
│                                                             │               │
│  live/app.py ───────────────────────────────────────┐      │               │
│  (Flask routes, SSE, JSON API, React SPA)           │      │               │
│       │                                              │      │               │
│       ├── live/ua.py (User-Agent parsing)           │      │               │
│       ├── live/geolocation.py (country → coords)    │      │               │
│       │                                              │      │               │
│       └── live/scoring.py ◀── DYNAMIC IMPORT ──┐   │      │               │
│            │                                    │   │      │               │
│            │  loads at runtime:                 │   │      │               │
│            │  ├── src/02 → feature_sql() ───────┘   │      │               │
│            │  ├── src/04 → score_sql() ─────────────┘      │               │
│            │  ├── src/_shared → FEATURE_COLS ──────────────┘               │
│            │  └── models/xgboost_model.joblib (lazy)                      │
│            │                                                               │
│            ▼                                                               │
│  Decision chain:                                                           │
│    blocklist IP → BLOCK                                                    │
│    ml_score >= threshold → FLAG                                            │
│    rule_score >= 90 → BLOCK                                                │
│    rule_score >= 45 → FLAG                                                 │
│    otherwise → ALLOW                                                       │
│                                                                             │
│  live/web/ (React SPA: dashboard, login form, alerts)                     │
│       │                                                                    │
│       └── SSE: GET /events/stream ← _live_feed queue                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Layer 3: Sub-Project Forks (three parallel paths)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     THREE SUB-PROJECT ARCHITECTURE                          │
│                                                                             │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌───────────────────┐ │
│  │    rba-anomaly/      │  │    rba-xgboost/      │  │   lanl-anomaly/   │ │
│  │    (port 5000)       │  │    (port 5001)       │  │   (port 5002)     │ │
│  ├──────────────────────┤  ├──────────────────────┤  ├───────────────────┤ │
│  │ Dataset: RBA 1M      │  │ Dataset: RBA 1M      │  │ Dataset: LANL 10M │ │
│  │ Models: LOF/IF/      │  │ Models: XGBoost+RF   │  │ Models: LOF/IF/   │ │
│  │   OCSVM/EE (unsup.)  │  │   (supervised)       │  │   OCSVM/EE        │ │
│  │ Label: is_attack_ip  │  │ Label: is_attack_ip  │  │ Label: is_red     │ │
│  │ Features: 19 RBA     │  │ Features: 19 RBA     │  │ Features: 8 LANL  │ │
│  │ Dashboard: shared/   │  │ Dashboard: shared/   │  │ Dashboard: own/   │ │
│  │  web/ (React)        │  │  web/ (React)        │  │  web/ (new React) │ │
│  ├──────────────────────┤  ├──────────────────────┤  ├───────────────────┤ │
│  │ src/ (copy of RBA    │  │ src/ (copy of RBA    │  │ src/ (LANL-       │ │
│  │  pipeline 00-04)     │  │  pipeline 00-04)     │  │  specific)        │ │
│  │ live/scoring.py      │  │ live/scoring.py      │  │ live/scoring.py   │ │
│  │  (loads xgboost)     │  │  (loads xgboost)     │  │  (NOT ADAPTED)    │ │
│  └──────────────────────┘  └──────────────────────┘  └───────────────────┘ │
│                                                                             │
│  RAM: LANL + XGBoost cannot run simultaneously (not enough RAM)           │
│                                                                             │
│  shared/web/ ──────▶ used by rba-anomaly + rba-xgboost                   │
│  lanl-anomaly/web/ ──▶ NEW React dashboard (different schema)             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Layer 4: Key Function Cross-References (the hidden graph)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FUNCTION CALL GRAPH                                      │
│                                                                             │
│  feature_sql(src) [defined: src/02_feature_engineering.py]                │
│       ├── called by: live/scoring.py:score_event()                        │
│       ├── called by: live/app.py:api_investigation()                       │
│       └── concept: "ask 21 questions about a login event"                  │
│                                                                             │
│  score_sql(src, ...) [defined: src/04_rule_baseline.py]                   │
│       ├── called by: live/scoring.py:score_event()                         │
│       ├── called by: live/app.py:api_investigation()                       │
│       └── concept: "10-rule bouncer checklist → 0-100 score"              │
│                                                                             │
│  split_sql(features) [defined: src/_shared.py]                             │
│       ├── called by: src/07_ensemble_full.py:main()                       │
│       ├── overridden in: src/lanl_train.py (local copy)                   │
│       └── concept: "per-user chronological 70/30 train/test split"         │
│                                                                             │
│  tune_threshold(y_true, scores, fpr_budget) [defined: src/_shared.py]     │
│       ├── called by: src/07_ensemble_full.py:main()                       │
│       ├── overridden in: src/lanl_train.py (local copy)                   │
│       └── concept: "best F1 under 5% false positive budget"               │
│                                                                             │
│  score_event(con, ev) [defined: live/scoring.py]                           │
│       ├── called by: live/app.py:login()                                   │
│       ├── called by: live/app.py:burst()                                   │
│       ├── called by: live/app.py:api_events()                              │
│       └── concept: "blocklist → ML → rules → decision → persist"          │
│                                                                             │
│  refresh_profile(con, user_id) [defined: live/db.py]                       │
│       ├── called by: live/scoring.py:score_event() (on ALLOW only)        │
│       └── concept: "update usual country/device/OS from accepted logins"   │
│                                                                             │
│  parse_user_agent(ua) [defined: live/ua.py]                                │
│       ├── called by: live/app.py:_event_from_form()                       │
│       └── concept: "extract OS, device type, browser from UA string"       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Layer 5: Data File Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      DATA FILE GRAPH                                        │
│                                                                             │
│  INPUTS                        INTERMEDIATE                OUTPUTS          │
│  ───────                       ────────────                ───────          │
│  rba-dataset.csv ──────▶ rba_clean.parquet                                    │
│                              │                                               │
│                              ▼                                               │
│                        rba_features.parquet                                  │
│                              │                                               │
│                    ┌─────────┼──────────┐                                    │
│                    ▼         ▼          ▼                                    │
│              sample.parquet  features.parquet  user_baselines.parquet       │
│                    │         │                                              │
│                    │         ├──▶ rule_baseline_scores.parquet               │
