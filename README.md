# AI-Based Identity Anomaly Detection System

**Team:** Hemanth Kumar KS (1SK23CS020) | Urvashi Tanwar (1SK23CS055) | Veenashree S T (1SK23CS057) | Vishwanath Sanapur (1SK23CS059)
**Guide:** Dr. Anitha A C — Government Sri Krishnarajendra Silver Jubilee Technological Institute, CSE

---

## Current State (Aug 5, 2026)

- **Dataset strategy: RBA-only.** The multi-source synthetic experiment (7 AI-generated log formats + parser.py) was prototyped, evaluated, and **removed** — the synthetic data was inconsistent and unlabelable (details in `COMPLETE_PROJECT_REFERENCE.md`).
- **Repo contents:**
  - `data/raw/rba-dataset.csv` — raw RBA dataset (8.5 GB, 31.3M events, Zenodo)
  - `data/processed/rba_clean.parquet` — cleaned version (654 MB, 31,269,264 rows preserved, flags added, no deletions) + `cleaning_summary.json`
  - `src/00_clean_dataset.py` — the cleaning script (full-file DuckDB, ~30 s)
  - 5 docs (this README + 4 below, see reading order) + `LICENSE`
- **Reclean done (Aug 5):** the cleaned parquet was rebuilt with two fixes — Android devices now default to `mobile` (only real tablet signatures become `tablet`), and ChromeOS detection no longer matches `SamsungBrowser/CrossApp`. Verified in `dataset_scan_report.md` §6 (`src/00_clean_dataset.py --verify`).
- **Revalidation fixes (Aug 8):** rebuilt again with three more OS/device mislabel fixes (~164K rows) — Windows Phone no longer caught by the iOS spoof token, KaiOS no longer matched by the `iOS` fallback, and `android@` tokens no longer classify ChromeOS desktops as Android mobile. Verified: `wp_as_ios=0`, `kaios_as_ios=0`, `cros_as_android=0`; `ua_os_conflict` 1,223,315 → 1,079,367.
- **Pipeline rewrite started:** the broken pipeline scripts and the old 18K-row training file (248 attacks) were removed; the clean rewrite begins with `src/00_clean_dataset.py` (roadmap in `COMPLETE_PROJECT_REFERENCE.md` status section).

## Docs

| Doc | What it covers |
|---|---|
| `DATASET_FINDINGS_VERIFIED.md` | Verified facts from the full 31.3M scan, beginner-friendly, what's next |
| `dataset_scan_report.md` | Full-scan quality report: every inconsistency found in all 31.3M rows + the cleaning solution |
| `PROJECT_ROADMAP.md` | **Implementation source of truth** — phases 0–11, build order, definition of done |
| `COMPLETE_PROJECT_REFERENCE.md` | Full project reference + **status update & roadmap** (read the status section first) |

## How to read these docs (recommended order)

1. `README.md` — this overview, current state, known issues
2. `DATASET_FINDINGS_VERIFIED.md` — the verified dataset facts, plain English
3. `dataset_scan_report.md` — the full quality audit, when you need the numbers
4. `PROJECT_ROADMAP.md` — the implementation plan (phases 0–11)
5. `COMPLETE_PROJECT_REFERENCE.md` — the deep design reference; read its STATUS UPDATE section first

## Known Issues (must fix in next phase)

1. Training data has only 248 attack examples (1.36%) — row-level sampling collapsed the 10% attack ratio
2. Documented metrics (94.2%/91.7%/88.3%) are not reproducible — actual recall is ~2%
3. `failed_before_success` semantics: docs say "5-min window", implementation used "since last success"
