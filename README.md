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
  - 6 docs (this README + 5 below, see reading order) + `LICENSE`
- **Reclean done (Aug 5):** the cleaned parquet was rebuilt with two fixes — Android devices now default to `mobile` (only real tablet signatures become `tablet`), and ChromeOS detection no longer matches `SamsungBrowser/CrossApp`. Details + verification in `fullDataset_cleaned_summary.md`.
- **Pipeline rewrite started:** the broken pipeline scripts and the old 18K-row training file (248 attacks) were removed; the clean rewrite begins with `src/00_clean_dataset.py` (roadmap in `COMPLETE_PROJECT_REFERENCE.md` status section).

## Docs

| Doc | What it covers |
|---|---|
| `fullDataset_cleaned_summary.md` | **New (Aug 5)** — what we did in the reclean session + Q&A, the easiest read |
| `DATASET_FINDINGS_VERIFIED.md` | Verified facts from the full 31.3M scan, beginner-friendly, what's next |
| `dataset_scan_report.md` | Full-scan quality report: every inconsistency found in all 31.3M rows + the cleaning solution |
| `PROJECT_ROADMAP.md` | **Implementation source of truth** — phases 0–11, build order, definition of done |
| `COMPLETE_PROJECT_REFERENCE.md` | Full project reference + **status update & roadmap** (read the status section first) |

## How to read these docs (recommended order)

1. `fullDataset_cleaned_summary.md` — what we just did + Q&A, the easiest read
2. `README.md` — this overview, current state, known issues
3. `DATASET_FINDINGS_VERIFIED.md` — the verified dataset facts, plain English
4. `dataset_scan_report.md` — the full quality audit, when you need the numbers
5. `PROJECT_ROADMAP.md` — the implementation plan (phases 0–11)
6. `COMPLETE_PROJECT_REFERENCE.md` — the deep design reference; read its STATUS UPDATE section first

## Known Issues (must fix in next phase)

1. Training data has only 248 attack examples (1.36%) — row-level sampling collapsed the 10% attack ratio
2. Documented metrics (94.2%/91.7%/88.3%) are not reproducible — actual recall is ~2%
3. `failed_before_success` semantics: docs say "5-min window", implementation used "since last success"
