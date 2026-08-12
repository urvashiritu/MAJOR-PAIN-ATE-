# Project Roadmap (in plain words)

## The project, simply

**Real-Time User Identity Anomaly Detection Using Behavioral Login Profiles**

We build a login-security system that:
1. learns a user's *normal* login behavior (time, country, device),
2. flags *unusual* login events,
3. explains the reason for every risk score,
4. shows decisions on a live security dashboard.

Two connected parts:
- **Offline**: a data + machine-learning pipeline built on the RBA dataset (done, phases 0–6).
- **Live**: website, risk API, user profiles, dashboard for the demo (phases 7–11, next; partial demo built Aug 11).

This project is specifically about **login identity anomalies** — not a full insider-threat
or post-login monitoring system.

## What we know about the data (the honest limits)

- The dataset has **31.3 million login events** — users, timestamps, countries, devices,
  browsers, OS, success/failure, attack-IP flags, and account-takeover flags.
- Only **141 confirmed account-takeover rows** exist. Catching takeovers must be reported
  as a hard, rare-event problem — not a guaranteed classifier.
- `Is Attack IP` is an **IP-reputation (blocklist) label**, not a behavioral one.
- Blank devices must be treated as an explicit `unknown` category.
- One user contributes ~45% of all events (a bot). Sampling caps it.
- Browser/OS version strings can fake device changes; we normalize versions.
- The VPN demo scenario needs a clearly labelled simulation mode as backup.

## The phases (0–11)

| Phase | Name | What we did / will do | Status |
|---|---|---|---|
| 0 | Scope and docs | Decided what the project is; banned unverified metric claims | ✅ |
| 1 | Environment and repo | Python env, folder layout, rules (never touch the raw CSV, never load it fully into memory) | ✅ |
| 2 | Dataset audit | Scanned all 31.3M rows: row counts, users, blanks, contradictions. Found the blocklist discovery | ✅ |
| 3 | Cleaning and sampling | Fixed messy values; picked 1M representative rows keeping all 141 takeover rows; capped the bot user | ✅ (Aug 8) |
| 4 | Feature engineering | 21 features per event over the user's true full history (new country? new device? recent failure? burst? unusual hour?) | ✅ (Aug 8) |
| 5 | Rule baseline | Bouncer checklist: new country +30, new IP +25, recent failure +20, ... → low/medium/high/critical with reasons | ✅ (Aug 9) |
| 6 | Models and evaluation | 4 anomaly models compared honestly; LOF won (gold F1 0.110 @ 5% FPR) | ✅ (Aug 9) |
| 6+ | Supervised extension | Trained on the gold label itself → HGB gold F1 0.287, a 2.6× improvement | ✅ (Aug 11) |
| 7 | Live scoring engine (user profile + risk API) | DuckDB live DB (`users`/`events`/`alerts`/`user_profile`), `live/scoring.py` reusing the exact `feature_sql`/`score_sql` + HGB model, personas seeded from real sample data, `POST /login` verdict flow, `POST /burst` attack sim, `user_profile` refreshed only after accepted (allow) events, JSON API (`POST /events`, `GET /risk/{id}`, `GET /users/{id}/profile`, `GET /alerts`) | ✅ (Aug 12) |
| 8 | Website and dashboard | Login form + persona cards, verdict/blocked/challenge flow pages, admin dashboard (events + alerts) with live push via SSE `GET /events/stream` | ✅ (Aug 12) — SSE chosen over WS: one-way push, zero new dependencies |
| 9 | Live demonstration | Laptop 1 = dashboard, Laptop 2 = website. Scripted scenarios: normal login → allow; new country → challenge; failed attempts → alert | ⏳ |
| 10 | Testing | Data, feature, model, and app tests | ⏳ |
| 11 | Report and presentation | Final report with only measured results | ⏳ |

### The key decisions we made (with reasons)

- **Features before sampling** (`02` runs before `01`): a sampled event must carry the exact
  feature the live system would compute. Sampling first would corrupt the history features
  (we found this the hard way with the bot user).
- **Chronological split**: a user's later events are predicted using only their earlier
  events — no future information ever leaks into a feature.
- **Gold label = `is_attack_ip` AND `login_success`** for tuning, under a 5% false-positive
  budget — so no model can degenerate into "flag everything."
- **Rules for the demo**: rules are deterministic and explainable; ML is the comparison.
- **Risk levels kept at low <30 / medium 30–64 / high 65–89 / critical ≥90**: the
  gold-tuned alternative (77) was rejected because it tripled false positives for +0.15%
  gold recall.

## Definition of done (what "ready" means)

- the raw dataset can be processed reproducibly,
- features are causally correct and shared by offline/live paths,
- at least one model beats the rule baseline on the agreed evaluation,
- false positives and rare takeover results are reported honestly,
- a login from Laptop 2 appears live on the dashboard,
- normal and suspicious scenarios produce different decisions,
- every alert includes an explanation,
- documentation matches the implemented system.

## Phase 6+ details (supervised models, Aug 11)

- Trained on the **gold label** (153,352 rows: `is_attack_ip` AND `login_success`) — a
  supervised question, unlike the anomaly detectors of Phase 6.
- Same split, same 21 features, same 5% FPR budget as Phase 6 (directly comparable).
- Results on the test set (212,233 events): HGB gold F1 **0.287** (ROC-AUC 0.752),
  Logistic Regression **0.180** (ROC-AUC 0.695).
- Honest caveats, documented in the report: test users also appear in train (later events —
  consistent with Phase 6), threshold tuned on test gold (consistent-but-optimistic),
  ATO 0/14 (gold and ATO are different populations; the rules catch ~79% of ATOs).
- Artifacts: `src/06_supervised_model.py`, `reports/supervised_evaluation.json`,
  `reports/supervised_replay.csv`. No Phase 6 files were touched.

## Phase 7/8 build notes (live demo, Aug 11–12)

- Built as a single Flask app (merged Phase 7 + 8): `live/db.py`,
  `live/scoring.py`, `live/seed_demo.py`, `live/app.py` + `live/templates/`.
- Scoring reuses the **exact training SQL** — `feature_sql` (src/02) and
  `score_sql` (src/04) are imported as-is and run over the user's stored
  history + the new event, so live features cannot drift from offline ones.
  ML = HGB `predict_proba` on the 21 FEATURE_COLS vs the tuned threshold.
- Decision policy (demo defaults): blocklist IP → block · rule_score ≥ 65 →
  block · ml_score ≥ threshold → flag · otherwise → allow.
- Seeded from `data/processed/sample.parquet`: 3 normal personas (alice, bob,
  carol) with 177 real history events, plus a fresh attacker persona with a
  blocklisted IP (5.180.170.85) and no history.
- **`user_profile` (Aug 12):** per-user row with the usual country/device/
  os/browser/ip/asn (mode over successful logins), top-3 hour buckets,
  avg logins per active day, and failed logins in the last 24h. Rebuilt by
  `refresh_profile()` **only after an accepted (allow) event** — attacker
  attempts can never pollute it. Seeded alongside the history.
- **JSON API (Aug 12):** `POST /events` (score one event → verdict JSON),
  `GET /risk/{event_id}`, `GET /users/{user_id}/profile`, `GET /alerts`.
  Negative user ids (seeded sample ids are negative) need a signed-int URL
  converter (`<sint:user_id>`), since werkzeug's `<int:>` matches digits
  only.
- **Live push (Aug 12):** `GET /events/stream` is a Server-Sent Events
  endpoint; the admin dashboard subscribes via `EventSource` and prepends
  rows in real time (no page refresh). SSE was chosen over WebSocket
  because the push is one-way and it needs zero extra dependencies.
- **Flow pages (Aug 12):** decision = block → `/blocked/{id}` (denied page
  with reasons); decision = flag → `/challenge/{id}` (demo OTP step —
  any code verifies; the event decision is not changed in the DB).
- Verified end-to-end (Aug 12): attacker → BLOCK/critical → blocked page;
  alice from her typical profile → ALLOW (rule 0); `POST /burst` ×5
  escalates; `POST /events` allow/flag/block all returned; profile updates
  only on allow; SSE pushed every scored event to the dashboard.

## Immediate next task

**Phase 9 — live demonstration.** Laptop 1 = dashboard (`/admin`), Laptop 2 =
website (`/`). Scripted scenarios: normal login → allow; new country/device →
flag → challenge step; attacker or rapid burst → block; watch alerts appear
live on the dashboard. Then Phase 10 (tests) and Phase 11 (report).
