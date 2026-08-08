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
  - `data/processed/sample.parquet` — stratified sample (1,000,000 rows, 193,688 users) + `sampling_report.json`
  - `data/processed/user_baselines.parquet` — per-user history over all 31.3M rows (for contextual features)
  - `data/processed/features.parquet` — sample + the 8 behavioral features + `features_report.json`
  - `src/00_clean_dataset.py` — cleaning script (full-file DuckDB, ~30 s)
  - `src/01_load_and_sample.py` — whole-user stratified sampling + baselines (~2 min)
  - `src/02_feature_engineering.py` — shared feature function (offline/live identical, ~5 s)
  - 4 docs (this README + 3 below, see reading order) + `LICENSE`
- **Reclean done (Aug 5):** the cleaned parquet was rebuilt with two fixes — Android devices now default to `mobile` (only real tablet signatures become `tablet`), and ChromeOS detection no longer matches `SamsungBrowser/CrossApp`. Verified in `dataset_scan_report.md` §6 (`src/00_clean_dataset.py --verify`).
- **Revalidation fixes (Aug 8):** rebuilt again with three more OS/device mislabel fixes (~164K rows) — Windows Phone no longer caught by the iOS spoof token, KaiOS no longer matched by the `iOS` fallback, and `android@` tokens no longer classify ChromeOS desktops as Android mobile. Verified: `wp_as_ios=0`, `kaios_as_ios=0`, `cros_as_android=0`; `ua_os_conflict` 1,223,315 → 1,079,367.
- **Blind re-audit (Aug 8):** the full dataset was re-scanned from scratch (no doc context) — every documented number re-verified, plus 8 previously-missed issues found (KaiOS scale 339,945, `device=tablet` w/o marker 691,864, `os_raw="Other "` 2.88M, silent-UA rows 3.0M, etc.). Full findings: `dataset_scan_report.md` §7.
- **Exhaustive coverage audit (Aug 8, `dataset_scan_report.md` §8):** the loop-closing pass — every column's formats, every mapping's coverage, every cross-tab enumerated. One gap found and fixed: 6 legacy OS families (BlackBerry 7,809 / MeeGo 3,110 / Roku / Symbian / WebTV / Firefox OS = 11,055 rows) were falling to `unknown`; `os_family` branches added, parquet rebuilt, guard `legacy_os_rows=11,055`. **Dataset declared audit-complete.**
- **Pipeline rewrite started:** the broken pipeline scripts and the old 18K-row training file (248 attacks) were removed; the clean rewrite is now `src/00_clean_dataset.py` → `src/01_load_and_sample.py` → `src/02_feature_engineering.py` (roadmap in `COMPLETE_PROJECT_REFERENCE.md` status section).
- **Sampling done (Aug 8, Phase 3):** whole-user stratified sampling to 1,000,000 rows — all 138 ATO users (141/141 rows), all 8,110 attack-heavy users, robot capped at 50,000 (flag `is_robot_sampled`), random light + normal users, 10K per-user cap. Gates all PASS: attack share 24.70% (natural, not forced), gold rows 152,863, all 4.3M users covered by full-dataset baselines. Design validated by two audit agents before implementation.
- **Features done (Aug 8, Phase 4):** shared feature function (`feature_sql`) computes `hour`, `is_night`, `is_weekend`, `country_change`, `device_change`, `failed_before_success` (true 5-min window), `rapid_login_rate` (60 s), `login_frequency_today` — only strictly-earlier events per user, first-ever event → `country_change=0`/`device_change=0` by explicit policy. Counts match the independent validator exactly (49,936 / 209,892 / 124,001 / max 11 / max 386). No future leakage: per-event features never use `user_baselines`.

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

1. ~~Training data has only 248 attack examples (1.36%)~~ — **RESOLVED (Aug 8):** whole-user sampling now yields 1,000,000 rows with a 24.70% natural attack share.
2. ~~Documented metrics (94.2%/91.7%/88.3%) are not reproducible — actual recall is ~2%~~ — **SUPERSEDED:** the old model artifacts were removed; honest metrics come from Phase 6 (models & evaluation) and will be reported as measured.
3. ~~`failed_before_success` semantics: docs say "5-min window", implementation used "since last success"~~ — **RESOLVED (Aug 8):** the shared feature function uses a real 5-minute lookback (strictly earlier events only).
4. **Open:** `contamination` for the anomaly models (Phase 6) must be set from the measured attack ratio, never hardcoded.
5. **Open:** rule-baseline point values (Phase 5) must be tuned on validation data, not presented as constants.
