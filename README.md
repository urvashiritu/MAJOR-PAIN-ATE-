# AI-Based Identity Anomaly Detection System

**Team:** Hemanth Kumar KS (1SK23CS020) | Urvashi Tanwar (1SK23CS055) | Veenashree S T (1SK23CS057) | Vishwanath Sanapur (1SK23CS059)
**Guide:** Dr. Anitha A C — Government Sri Krishnarajendra Silver Jubilee Technological Institute, CSE

## The project in one paragraph

We are building a system that watches login events (like "someone logged in from India on an iPhone at 2pm") and flags the suspicious ones ("someone logged in from Russia at 3am on an Android — that's weird for this user"). We use 4 machine learning models trained on **31 million real login events** from a published academic dataset (RBA, Telenor Norway). During the demo, login events arrive live from a second laptop, get scored by the models, and show up on a dashboard as green (safe) or red (alert).

### Plain-English glossary

| Word | What it means, simply |
|---|---|
| **Row / event** | One login attempt: who, when, from which country, on which device, did it succeed |
| **Feature** | A single number we compute from a row (e.g. `hour`, `country_change`) |
| **Label** | The truth: is this row an attack (1) or not (0). The model tries to predict this |
| **Anomaly** | Something unusual. A login from a new country at 3am is an anomaly |
| **Sampling** | Picking a smaller, representative chunk out of the big dataset (we can't fit 31M rows in RAM) |
| **Train/test split** | Train the model on part A, test it on part B it never saw. If it works on part B, it works on *new* events |
| **Attack ratio** | What fraction of rows are attacks. If 10% of rows are attacks, ratio = 0.10 |
| **ATO** | Account Takeover — a real account got hacked (the gold-standard label in our data) |

---

## Current State (Aug 8, 2026)

- **Dataset strategy: RBA-only.** The multi-source synthetic experiment (7 AI-generated log formats + parser.py) was prototyped, evaluated, and **removed** — the synthetic data was inconsistent and unlabelable (details in `COMPLETE_PROJECT_REFERENCE.md`).
- **Repo contents:**
  - `data/raw/rba-dataset.csv` — raw RBA dataset (8.5 GB, 31.3M events, Zenodo)
  - `data/processed/rba_clean.parquet` — cleaned version (685 MB, 31,269,264 rows preserved, flags added, no deletions) + `cleaning_summary.json`
  - `data/processed/rba_features.parquet` — the 8 behavioral features over **all** 31.3M rows (full-history, so sampled events carry exactly what the live system would have computed) + `features_report.json`
  - `data/processed/sample.parquet` — stratified sample (1,000,003 rows, 192,649 users, features included) + `sampling_report.json`
  - `data/processed/features.parquet` — final training table: the sample minus pipeline artifacts (`rn`, `is_robot_sampled`)
  - `data/processed/user_baselines.parquet` — per-user history over all 31.3M rows (for contextual features)
  - `src/00_clean_dataset.py` — cleaning script (full-file DuckDB, ~30 s)
  - `src/01_load_and_sample.py` — whole-user stratified sampling + baselines (~2 min)
  - `src/02_feature_engineering.py` — shared feature function (offline/live identical, full-dataset pass)
  - `src/03_validate_contract.py` — **schema + cross-column invariant checks** over every artifact (fails on stale/regressed files)
  - 4 docs (this README + 3 below, see reading order) + `LICENSE`
- **Reclean done (Aug 5):** the cleaned parquet was rebuilt with two fixes — Android devices now default to `mobile` (only real tablet signatures become `tablet`), and ChromeOS detection no longer matches `SamsungBrowser/CrossApp`. Verified in `dataset_scan_report.md` §6 (`src/00_clean_dataset.py --verify`).
- **Revalidation fixes (Aug 8):** rebuilt again with three more OS/device mislabel fixes (~164K rows) — Windows Phone no longer caught by the iOS spoof token, KaiOS no longer matched by the `iOS` fallback, and `android@` tokens no longer classify ChromeOS desktops as Android mobile. Verified: `wp_as_ios=0`, `kaios_as_ios=0`, `cros_as_android=0`; `ua_os_conflict` 1,223,315 → 842,170 (final, after the scan-5 iOS-fallback fix).
- **Blind re-audit (Aug 8):** the full dataset was re-scanned from scratch (no doc context) — every documented number re-verified, plus 8 previously-missed issues found (KaiOS scale 339,945, `device=tablet` w/o marker 691,864, `os_raw="Other "` 2.88M, silent-UA rows 3.0M, etc.). Full findings: `dataset_scan_report.md` §7.
- **Exhaustive coverage audit (Aug 8, `dataset_scan_report.md` §8):** the loop-closing pass — every column's formats, every mapping's coverage, every cross-tab enumerated. One gap found and fixed: 6 legacy OS families (BlackBerry 7,837 / MeeGo 3,110 / Roku 649 / Symbian 35 / WebTV 21 / Firefox OS 5 = 11,657 rows) were falling to `unknown`; `os_family` branches added, parquet rebuilt, guard `legacy_os_rows=11,657` (scan-4's 11,055 under-counted version-suffixed `os_raw` values like `Roku 9.10`). **Dataset declared audit-complete.**
- **Pipeline rewrite started:** the broken pipeline scripts and the old 18K-row training file (248 attacks) were removed; the clean rewrite is now `src/00_clean_dataset.py` → `src/02_feature_engineering.py` → `src/01_load_and_sample.py` → `src/03_validate_contract.py` (roadmap in `COMPLETE_PROJECT_REFERENCE.md` status section).
- **Sampling done (Aug 8, Phase 3):** whole-user stratified sampling to 1,000,003 rows — all 138 ATO users (141/141 rows), all 8,110 attack-heavy users, robot capped at 50,000 (flag `is_robot_sampled`), random light + normal users, 10K per-user cap. Gates all PASS: attack share 24.76% (natural, not forced), gold rows 153,352, all 4.3M users covered by full-dataset baselines. Design validated by two audit agents before implementation.
- **Features done (Aug 8, Phase 4):** shared feature function (`feature_sql`) computes `hour`, `is_night`, `is_weekend`, `country_change`, `device_change`, `failed_recently` (a failed login within the 5 minutes before the event — any event, success or failure), `rapid_login_rate` (60 s), `login_frequency_today` — only strictly-earlier events per user, first-ever event → `country_change=0`/`device_change=0` by explicit policy. Features are computed over each user's **true full history** (all 31.3M rows), then the sample is drawn from the featured table — the robot user's features are therefore correct (they were previously computed on its random 50K-row subset: `rapid_login_rate` mean 0.118 vs true 34.0). No future leakage: per-event features never use `user_baselines`.
- **Audit-fix pass (Aug 8, Phase 3.5):** an independent agent audit of the cleaning and feature scripts found 10 more issues, all fixed and regression-checked:
  - `geo_unreliable` was a byte-identical duplicate of `is_private_ip` → now `private IP OR region/city missing` (12.27M rows distinct)
  - `(?i)iOS` substring false positives: 134,393 AwarioSmartBot rows (the name contains "ioS") + 26,263 CriOS-on-Android spoofs were labeled iOS → token-boundary detection; `AwarioSmartBot` added to `is_generator_bot` (140,993 rows)
  - bare `Mobile` substring reclassified 3,402 desktop rows as mobile (the generator appends "Mobile Safari/537.36" to desktop UAs) → token-boundary + desktop-OS guard
  - `device_raw='unknown'`/NULL short-circuited UA checks (1,526 NULL-device rows became `desktop`) → UA checks run first, NULL → `unknown`
  - `Andorid` typo (242 rows) now maps to Android
  - sampling is now deterministic (hash-based ordering — `random()` is not reproducible under threads>1 even with `setseed`) and `fixed_rows` is computed at runtime instead of hardcoded (was wrong by 19,762 rows under `--no-genbots`)
  - features output no longer leaks `prior_fail_ts`; `rn`/`is_robot_sampled` dropped from the training table; `failed_before_success` renamed to `failed_recently` (it flags any event, not just successes)
  - new `src/03_validate_contract.py` catches all of the above on stale or regressed artifacts (verified: fails on the pre-fix parquets, passes on the rebuilt ones)

## Docs

| Doc | What it covers |
|---|---|
| `dataset_scan_report.md` | Full-scan quality report: every inconsistency found in all 31.3M rows + the cleaning solution + blind re-audit (§7) + exhaustive coverage audit (§8) |
| `PROJECT_ROADMAP.md` | **Implementation source of truth** — phases 0–11, build order, definition of done |
| `COMPLETE_PROJECT_REFERENCE.md` | Full project reference + **status update & roadmap** (read the status section first) |

## How to read these docs (recommended order)

1. `README.md` — this overview, current state, known issues
2. `dataset_scan_report.md` — the full quality audit, when you need the numbers
3. `PROJECT_ROADMAP.md` — the implementation plan (phases 0–11)
4. `COMPLETE_PROJECT_REFERENCE.md` — the deep design reference; read its STATUS UPDATE section first

## Known Issues (must fix in next phase)

1. ~~Training data has only 248 attack examples (1.36%)~~ — **RESOLVED (Aug 8):** whole-user sampling now yields 1,000,003 rows with a 24.76% natural attack share.
2. ~~Documented metrics (94.2%/91.7%/88.3%) are not reproducible — actual recall is ~2%~~ — **SUPERSEDED:** the old model artifacts were removed; honest metrics come from Phase 6 (models & evaluation) and will be reported as measured.
3. ~~`failed_before_success` semantics: docs say "5-min window", implementation used "since last success"~~ — **RESOLVED (Aug 8):** the shared feature function uses a real 5-minute lookback (strictly earlier events only). Renamed `failed_recently` in the Aug 8 audit-fix pass.
4. **Open:** `contamination` for the anomaly models (Phase 6) must be set from the measured attack ratio, never hardcoded.
5. **Open:** rule-baseline point values (Phase 5) must be tuned on validation data, not presented as constants.
6. **Resolved (Aug 8):** `geo_unreliable` duplicate, iOS/Mobile substring mislabels, device short-circuit, `Andorid` typo, non-deterministic sampling, hardcoded `fixed_rows`, `prior_fail_ts` leak, `failed_before_success` misnomer — all fixed in the audit-fix pass and guarded by `src/03_validate_contract.py`.
