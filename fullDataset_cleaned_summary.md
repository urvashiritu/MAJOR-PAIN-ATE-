# Full Dataset Cleaning — Summary & Session Log (Aug 5, 2026)

A beginner-friendly log of what we did and decided in the reclean session. Written for all teammates — no coding knowledge needed.

---

## 1. What happened (one paragraph)

We decided to clean the RBA dataset again from scratch. We deleted the old cleaned file, reviewed how the cleaning worked, found **two bugs** in the cleaning script by asking questions of the real data, fixed them, re-ran the full clean (all 31,269,264 rows, ~30 seconds, no row deleted), and verified every number in the output. The dataset is now clean and ready for the next phase (building the training sample).

---

## 2. Why we cleaned again

The old cleaned file was built with two small mistakes that would have confused the machine-learning models later. We found them by analysing the real data before fixing anything.

---

## 3. Bug 1 — Android phones were being called tablets

**The bug:** the cleaning script only classified an Android device as `mobile` if its browser signature (User Agent string) contained the word "Mobile". Otherwise it defaulted to `tablet`.

**Why it was wrong:** we scanned all 31.3M rows. Among rows whose signature mentions Android, **94% are tagged `mobile` by the dataset itself** — and the rows missing the word "Mobile" are mostly phones too (e.g. `Galaxy Nexus`, `Android 2.2 Firefox`, `i phone X`). The word "Mobile" is an unreliable marker: many real phones simply don't include it.

**The fix:** Android now means `mobile` by default. It only becomes `tablet` when the signature explicitly says so (e.g. `Tablet`, `SM-T`, `Galaxy Tab`, `Nexus 7`, `Xoom`).

**Effect on the data:**
- ~929,000 phones (Galaxy Nexus and friends) corrected: `tablet` → `mobile`
- ~650,000 real tablets corrected: `mobile` → `tablet`

---

## 4. Bug 2 — ChromeOS detection matched a Samsung browser

**The bug:** the script detected ChromeOS by searching for `CrOS` in the signature. But the text `SamsungBrowser/CrossApp` also contains "CrOS", so ~127,000 Samsung phones would have been mislabelled as ChromeOS.

**The fix:** we now match only the real ChromeOS marker `X11; CrOS`.

**Effect:** verified — **zero** CrossApp rows are mislabelled; they all correctly stay iOS / Android / Windows Phone.

---

## 5. The full clean + verification

Re-ran the cleaning over all 31,269,264 rows (inside DuckDB, streamed, nothing loaded into RAM). The verification table:

| Check | Before (raw) | After (cleaned) |
|---|---|---|
| Total rows | 31,269,264 | 31,269,264 (unchanged ✓) |
| Raw-mobile misclassified | 3,162,207 | 1,307,183 (fix working ✓) |
| Private IPs flagged | 7,291,335 | 7,291,335 ✓ |
| RTT missing | 29,993,329 | 29,993,329 ✓ |
| Generator-bot rows | 3,704,894 | 3,704,894 ✓ |
| VLC rows | 708,927 | 708,927 ✓ |
| Geo set to NULL | — | 13,899,240 ✓ |

Every number matches the full-scan report (`dataset_scan_report.md`) exactly. The cleaned file also passed sanity checks: no NULL timestamps, no duplicate rows, all 4,304,857 users present, date range 2020-02-03 → 2021-02-28.

**Output files:** `data/processed/rba_clean.parquet` (654 MB) + `data/processed/cleaning_summary.json`

---

## 6. Q&A from this session

**Q: Is the RBA dataset "weak"?**
A: Not weak — it's a great source of real login behaviour and one of the only public datasets with country + device + browser + OS together. But it's **hard**: one bot user owns 45% of the rows, most attack labels come from it, and there are only 141 confirmed account takeovers. The difficulty is in sampling and honest evaluation, not in the model. Our plan already handles this (tiered user-based sampling, robot cap).

**Q: Should we add a neural network?**
A: No clear win. We only have 8 simple features, so a neural net rarely beats the 4 sklearn models — and it hurts the "explainable ML" story for the viva. The real problem is label quality and sampling, not model size. Possible later: one small autoencoder as an extra "voter"; deep learning goes in the report as future work.

**Q: What did the docs validation find?**
A: The core facts agree everywhere (31.3M rows, 141 ATOs, robot user, etc.). A few small stale claims exist (a "DuckDB cache" that isn't on disk, a "~1M vs 500K" sample-size mismatch, a 3-vs-4 robot success count). These are tracked for a later docs-fix pass, not urgent.

---

## 7. Where the project stands

- ✅ Raw data intact (9 GB, never modified)
- ✅ Cleaning script fixed (`src/00_clean_dataset.py`)
- ✅ Cleaned dataset built + verified (`data/processed/rba_clean.parquet`)
- ⏳ **Next: Phase 2** — build the training sample (user-based tiered sampling, ~1M rows) + feature engineering
- 🔴 Later: train 4 models, honest evaluation, dashboard, live demo

---

## 8. Recommended reading order for the docs

| Order | File | Why read it |
|---|---|---|
| 1 | `fullDataset_cleaned_summary.md` | This file — what we just did + Q&A, the easiest read |
| 2 | `README.md` | 1-page overview + current state + known issues |
| 3 | `DATASET_FINDINGS_VERIFIED.md` | The verified dataset facts, plain English |
| 4 | `dataset_scan_report.md` | The full quality audit — when you need the numbers |
| 5 | `PROJECT_ROADMAP.md` | Implementation source of truth (phases 0–11, build order) |
| 6 | `COMPLETE_PROJECT_REFERENCE.md` | Deep design reference (features, models, demo, viva) — read its STATUS UPDATE section first |
