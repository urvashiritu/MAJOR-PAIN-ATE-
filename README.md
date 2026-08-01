# AI-Based Identity Anomaly Detection System

**Team:** Hemanth Kumar KS (1SK23CS020) | Urvashi Tanwar (1SK23CS055) | Veenashree S T (1SK23CS057) | Vishwanath Sanapur (1SK23CS059)
**Guide:** Dr. Anitha A C — Government Sri Krishnarajendra Silver Jubilee Technological Institute, CSE

---

## Current State (Aug 1, 2026)

- **Dataset strategy: RBA-only.** The multi-source synthetic experiment (7 AI-generated log formats + parser.py) was prototyped, evaluated, and **removed** — the synthetic data was inconsistent and unlabelable (details in `COMPLETE_PROJECT_REFERENCE.md`).
- **Repo contents:**
  - `data/raw/rba-dataset.csv` — raw RBA dataset (8.5 GB, 31.3M events, Zenodo)
  - 4 docs (see below) + `LICENSE`
- **No .py scripts right now** — the broken pipeline scripts and the old 18K-row training file (248 attacks) were removed; a clean rewrite is planned (see roadmap in `COMPLETE_PROJECT_REFERENCE.md` status section).

## Docs

| Doc | What it covers |
|---|---|
| `DATASET_FINDINGS_VERIFIED.md` | **Read this first** — verified facts from the full 31.3M scan, beginner-friendly, what's next |
| `COMPLETE_PROJECT_REFERENCE.md` | Full project reference + **status update & roadmap** (read the status section first) |
| `dataset_analysis.md` | Why RBA was chosen over LANL and CERT |

## Known Issues (must fix in next phase)

1. Training data has only 248 attack examples (1.36%) — row-level sampling collapsed the 10% attack ratio
2. Documented metrics (94.2%/91.7%/88.3%) are not reproducible — actual recall is ~2%
3. `failed_before_success` semantics: docs say "5-min window", implementation used "since last success"
