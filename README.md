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
  - `data/processed/rba_clean.parquet` — cleaned version (654 MB, 31,269,264 rows preserved, flags added, no deletions) + `cleaning_summary.json`
  - `src/00_clean_dataset.py` — the cleaning script (full-file DuckDB, ~30 s)
  - 4 docs (this README + 3 below, see reading order) + `LICENSE`
- **Reclean done (Aug 5):** the cleaned parquet was rebuilt with two fixes — Android devices now default to `mobile` (only real tablet signatures become `tablet`), and ChromeOS detection no longer matches `SamsungBrowser/CrossApp`. Verified in `dataset_scan_report.md` §6 (`src/00_clean_dataset.py --verify`).
- **Revalidation fixes (Aug 8):** rebuilt again with three more OS/device mislabel fixes (~164K rows) — Windows Phone no longer caught by the iOS spoof token, KaiOS no longer matched by the `iOS` fallback, and `android@` tokens no longer classify ChromeOS desktops as Android mobile. Verified: `wp_as_ios=0`, `kaios_as_ios=0`, `cros_as_android=0`; `ua_os_conflict` 1,223,315 → 1,079,367.
- **Blind re-audit (Aug 8):** the full dataset was re-scanned from scratch (no doc context) — every documented number re-verified, plus 8 previously-missed issues found (KaiOS scale 339,945, `device=tablet` w/o marker 691,864, `os_raw="Other "` 2.88M, silent-UA rows 3.0M, etc.). Full findings: `dataset_scan_report.md` §7.
- **Exhaustive coverage audit (Aug 8, `dataset_scan_report.md` §8):** the loop-closing pass — every column's formats, every mapping's coverage, every cross-tab enumerated. One gap found and fixed: 6 legacy OS families (BlackBerry 7,809 / MeeGo 3,110 / Roku / Symbian / WebTV / Firefox OS = 11,055 rows) were falling to `unknown`; `os_family` branches added, parquet rebuilt, guard `legacy_os_rows=11,055`. **Dataset declared audit-complete.**
- **Pipeline rewrite started:** the broken pipeline scripts and the old 18K-row training file (248 attacks) were removed; the clean rewrite begins with `src/00_clean_dataset.py` (roadmap in `COMPLETE_PROJECT_REFERENCE.md` status section).

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

1. Training data has only 248 attack examples (1.36%) — row-level sampling collapsed the 10% attack ratio
2. Documented metrics (94.2%/91.7%/88.3%) are not reproducible — actual recall is ~2%
3. `failed_before_success` semantics: docs say "5-min window", implementation used "since last success"
