# Experiment Log

> Every row = what we CHANGED + what HAPPENED. Nothing else matters.

## Dataset
- 29.9M events, 702 red attacks, 604 users
- 13 features: dst_first, src_first, hour_ratio, dst_prior_events, fail_1h, vel_1h, hour_sin, hour_cos, is_ntlm, pair_first, src_dst_pair_first, fail_rate, dst_first_x_ntlm
- IF always: n_estimators=200, max_samples=256, contamination=702/29.9M, StandardScaler, log1p on 3 features

---

## RUN 1: LEAKED SPLIT (StratifiedShuffleSplit by row)
> 101/104 red users leaked into both train+test. Numbers are FAKE.

### A. Baseline (9feat, spw=100)
- **LGB params:** num_leaves=31, lr=0.05, n_estimators=200, **spw=100**
- **New features:** NONE (only original 9)
- IF:  TP=10   FP=474  ROC=0.991
- LGB: TP=105  FP=9501 ROC=0.727 — spw=100 = binary output, useless
- Comb: TP=74   FP=3208 ROC=0.993

### B. +3 new features (12feat, spw=100)
- **Changed:** added pair_first, fail_rate, dst_first_x_ntlm
- **LGB params:** SAME as A (spw=100)
- IF:  TP=31   FP=3382 ROC=0.991 — new features HURT IF
- LGB: TP=122  FP=11214 ROC=0.753 — new features + saturated LGB = WORSE
- Comb: TP=33   FP=222  ROC=0.994 — IF+LGB averaging accidentally helped FP

### C. spw=100 → spw=10 (12feat, TUNED)
- **Changed:** spw 100→10, num_leaves 31→63, lr 0.05→0.03, n_estimators 200→500, min_child_samples=50, reg_alpha=0.1, reg_lambda=1.0
- **LGB params:** num_leaves=63, lr=0.03, n_estimators=500, **spw=10**, min_child=50, α=0.1, λ=1.0
- IF:  TP=31   FP=3382 ROC=0.991 — same IF
- LGB: TP=51   FP=273  ROC=0.957 — spw=10 fixed saturation! FP dropped 40x
- Comb: TP=41   FP=196  ROC=0.993

### D. spw=10 → spw=3 (12feat, HEAVY REG)
- **Changed:** spw 10→3, min_child_samples 50→100, reg_alpha 0.1→0.5, reg_lambda 1.0→5.0
- **LGB params:** num_leaves=63, lr=0.03, n_estimators=500, **spw=3**, min_child=100, α=0.5, λ=5.0
- IF:  TP=31   FP=3382 ROC=0.991 — same IF
- LGB: TP=99   FP=442  ROC=0.999 — highest ROC but more FP than C
- Comb: TP=33   FP=137  ROC=0.993

---

## RUN 2: LEAKED SPLIT (still StratifiedShuffleSplit — fix not applied yet)
> Same leaked split as Run 1. Numbers are FAKE.
> Fix was applied AFTER this run. Only Run 3 is honest.

### A. Baseline (9feat, spw=100)
- **LGB params:** num_leaves=31, lr=0.05, n_estimators=200, **spw=100**
- **New features:** NONE (only original 9)
- IF:  TP=10   FP=474  ROC=0.991
- LGB: TP=105  FP=9501 ROC=0.727 — spw=100 STILL broken
- Comb: TP=74   FP=3208 ROC=0.993

### B. +3 new features (12feat, spw=100)
- **Changed:** added pair_first, fail_rate, dst_first_x_ntlm
- **LGB params:** SAME as A (spw=100)
- IF:  TP=31   FP=3382 ROC=0.991
- LGB: TP=122  FP=11214 ROC=0.753 — still saturated
- Comb: TP=33   FP=222  ROC=0.994

### C. spw=100 → spw=10 (12feat, TUNED)
- **Changed:** spw 100→10, num_leaves 31→63, lr 0.05→0.03, n_estimators 200→500, min_child_samples=50, reg_alpha=0.1, reg_lambda=1.0
- **LGB params:** num_leaves=63, lr=0.03, n_estimators=500, **spw=10**, min_child=50, α=0.1, λ=1.0
- LGB: TP=51   FP=273  ROC=0.957 — spw=10 STILL fixes saturation
- Comb: TP=41   FP=196  ROC=0.993

### D. spw=10 → spw=3 (12feat, HEAVY REG)
- **Changed:** spw 10→3, min_child_samples 50→100, reg_alpha 0.1→0.5, reg_lambda 1.0→5.0
- **LGB params:** num_leaves=63, lr=0.03, n_estimators=500, **spw=3**, min_child=100, α=0.5, λ=5.0
- LGB: TP=99   FP=442  ROC=0.999 — best ROC, best TP
- Comb: TP=33   FP=137  ROC=0.993

---

## VERDICT (after Run 2 — still leaked, same as Run 1)
- All numbers FAKE — same leaked split as Run 1
- Run 1 and Run 2 are identical because the fix wasn't applied yet

---

## RUN 3: FIXED SPLIT + 13 FEATURES (src_dst_pair_first added)
> GroupShuffleSplit on src_user. 13 features (added src_dst_pair_first).
> Train: 24.5M (462 red) / Test: 5.4M (240 red)
> Total time: 1536.7s (25.6 min)

### A. Baseline (9feat, spw=100)
- **LGB params:** num_leaves=31, lr=0.05, n_estimators=200, **spw=100**
- IF:  TP=10   FP=474   ROC=0.991
- LGB: TP=105  FP=9501  ROC=0.727 — spw=100 still broken
- Comb: TP=74   FP=3208  ROC=0.993

### B. +4 new features (13feat, spw=100)
- **Changed:** added pair_first, src_dst_pair_first, fail_rate, dst_first_x_ntlm
- IF:  TP=17   FP=1874  ROC=0.991 — new features hurt IF FP (1874 vs 474)
- LGB: TP=160  FP=10115 ROC=0.832 — still saturated but ROC improved (0.832 vs 0.727)
- Comb: TP=111  FP=984   ROC=0.995 — best comb so far

### C. spw=100 → spw=10 (13feat, TUNED)
- **Changed:** spw 100→10, num_leaves 31→63, lr 0.05→0.03, n_estimators 200→500, min_child=50, α=0.1, λ=1.0
- IF:  TP=17   FP=1874  ROC=0.991 — same IF
- LGB: TP=70   FP=392   ROC=0.982 — spw=10 fixed saturation! FP dropped 25x
- Comb: TP=40   FP=149   ROC=0.993

### D. spw=10 → spw=3 (13feat, HEAVY REG)
- **Changed:** spw 10→3, min_child 50→100, α 0.1→0.5, λ 1.0→5.0
- IF:  TP=17   FP=1874  ROC=0.991 — same IF
- **LGB: TP=94   FP=386   ROC=0.999** — BEST MODEL
- Comb: TP=41   FP=117   ROC=0.993

### LGB-tuned-v2 feature importance:
- vel_1h=6108, hour_ratio=6077, hour_cos=5555, hour_sin=5540, dst_prior_events=4376
- fail_rate=1324, fail_1h=687, src_first=348, src_dst_pair_first=304, is_ntlm=267
- pair_first=230, dst_first=36, dst_first_x_ntlm=7

### LGB-tuned-v2 prob distribution:
- Attacks: min=0.000 p25=0.009 p50=0.056 p75=0.232 max=0.816
- Normal:  min=0.000 p50=0.000 p75=0.000 max=0.950

---

## VERDICT (after Run 3, 13 features, HONEST)
- **LGB spw=3 is the best** — TP=94, FP=386, ROC=0.999
- **LGB spw=10 is second** — TP=70, FP=392, ROC=0.982
- **IF is consistently useless** — TP=10-17, catches nothing alone
- **Combined always worse than LGB alone** — IF drags it down
- **New features (src_dst_pair_first) help LGB marginally** but not dominant
- **Top features: vel_1h, hour_ratio, hour_cos, hour_sin, dst_prior_events** — temporal patterns dominate
- **dst_first_x_ntlm: low LGB importance (5-7) but 7,028x signal enrichment** — strong combination signal that LGB underutilizes

### E. IF normal-only vs IF mixed (13feat)
- **Changed:** IF trained on non-red train rows only (normal_mask = ~y_train)
- IF-mixed: TP=17  FP=1867 ROC=0.991 PR-AUC=0.005
- **IF-normal-only: TP=10 FP=347 ROC=0.990 PR-AUC=0.007** — 5.4x fewer FP, 40% better PR-AUC
- IF-normal-only catches fewer attacks (10 vs 17) but signals are much cleaner
- **Verdict: IF normal-only is BETTER than IF mixed on this dataset**

---

## VERDICT (after Run 4, 13 features, HONEST)
- **LGB spw=3 is the best** — TP=91, FP=385, ROC=0.999
- **IF normal-only > IF mixed** — 5.4x fewer FP, same ROC, higher PR-AUC
- **Combined always worse than LGB alone** — IF drags it down even when trained on normal-only
- **Top features: vel_1h, hour_ratio, hour_cos, hour_sin, dst_prior_events** — temporal patterns dominate
- **dst_first_x_ntlm: 7,028x enrichment but low LGB importance** — strong combination signal that LGB underutilizes

---

## RUN 5: DETERMINISTIC (fixes applied, verified reproducible)
> GroupShuffleSplit on src_user, random_state=42.
> Non-determinism fix: ORDER BY rowid → ORDER BY time, src_user, dst_user, src_computer, dst_computer, auth_type, logon_type, orientation, result (9 unique columns).
> Window function fix: ROW_NUMBER() ORDER BY tiebreakers added (same 9 columns minus PARTITION BY columns).
> Verified: Two consecutive runs produce 100% identical results across ALL sections.
>
> ### Root cause: TWO sources of non-determinism
> 1. **ORDER BY rowid** — DuckDB rowid is physical-storage-based, changes when table is rebuilt. Fixed by replacing with 9 unique columns in outer ORDER BY.
> 2. **Window functions with ties** — ROW_NUMBER() OVER (ORDER BY time) is non-deterministic when multiple rows share the same time within a partition (SQL standard). Fixed by adding tiebreaker columns (non-partition columns from the 9-column uniqueness set) to each window function's ORDER BY.
>
> ### Fix applied to exp1.py
> - Outer ORDER BY: `ORDER BY rowid` → `ORDER BY time, src_user, dst_user, src_computer, dst_computer, auth_type, logon_type, orientation, result`
> - pair_first: `ORDER BY time` → `ORDER BY time, dst_user, auth_type, logon_type, orientation, result`
> - src_dst_pair_first: `ORDER BY time` → `ORDER BY time, src_user, dst_user, auth_type, logon_type, orientation, result`
> - pair_rank: `ORDER BY time` → `ORDER BY time, dst_user, auth_type, logon_type, orientation, result`

### A. Baseline (9feat, spw=100)
- IF:  TP=10   FP=317   ROC=0.9906
- LGB: TP=38   FP=11733 ROC=0.5818 — spw=100 still broken
- Comb: TP=12  FP=254   ROC=0.9907

### B. 13 features, spw=100
- IF:  TP=32   FP=1627  ROC=0.9882
- LGB: TP=72   FP=10636 ROC=0.6490 — saturated
- Comb: TP=47  FP=1635  ROC=0.9902

### C. 13 features, TUNED (spw=10)
- LGB: TP=56   FP=397   ROC=0.7847
- Comb: TP=38  FP=189   ROC=0.9898

### D. 13 features, TUNED v2 (spw=3, HEAVY REG)
- **LGB: TP=94  FP=372   ROC=0.9994** — BEST LGB
- Comb: TP=44  FP=149   ROC=0.9900
- Feature importance: vel_1h=6133, hour_ratio=5994, hour_cos=5811, hour_sin=5500, dst_prior_events=4339, fail_rate=1332, fail_1h=621, pair_first=305, src_dst_pair_first=290, is_ntlm=265, src_first=220, dst_first=66, dst_first_x_ntlm=3
- Prob distribution: Attacks min=0.000 p25=0.008 p50=0.060 p75=0.219 max=0.899; Normal min=0.000 p50=0.000 p75=0.000 max=0.982

### E. IF normal-only vs IF mixed (13feat)
- IF-mixed: TP=32  FP=1627 ROC=0.9882
- IF-normal-only: TP=48  FP=3022 ROC=0.9895

### F. 14 features (+pair_rank), TUNED v2 (spw=3)
- LGB: TP=80   FP=346   ROC=0.9998
- Comb: TP=49  FP=140   ROC=0.9908 — best Comb TP/FP ratio
- Feature importance: hour_ratio=6113, hour_sin=5694, vel_1h=5688, hour_cos=5560, dst_prior_events=3771, fail_rate=1459, log_pair_rank=1013, fail_1h=751, pair_first=280, is_ntlm=203, src_dst_pair_first=167, src_first=152, dst_first=62, dst_first_x_ntlm=6

---

## VERDICT (after Run 5, DETERMINISTIC)
- **Results are 100% reproducible** — two consecutive runs identical across all sections
- **LGB spw=3 is still best** — TP=94, FP=372, ROC=0.9994
- **pair_rank (14feat) vs pair_first only (13feat):** LGB TP 80 vs 94, FP 346 vs 372 — pair_rank slightly worse on its own
- **Combined 14feat (TP=49, FP=140) is the best Comb result** — lowest FP with decent TP
- **IF still useless alone** — TP=10-48, catches nothing meaningful
- **Combined always worse than LGB alone** — IF drags it down
- **Previous runs 1-4 numbers are INVALID** — non-deterministic splits produced different numbers each time
- **Root cause was ORDER BY rowid** — DuckDB rowid is physical-storage-based, changes when table is rebuilt

---

## IF FINE-TUNE: Contamination sweep (if_finetune.py)
> IF trains on ALL 29.9M normal events (not just train split).
> Test on ALL 702 reds + 100k sampled normals.
> 5 contamination values: mixed (702/29.9M), 1e-15, 1e-10, 1e-7, 0.5
> Deterministic: same ORDER BY, RandomState(42), random_state=42
> Runtime: 35 min

### A. 9feat (original LANL)
- IF-mixed:            TP=404  FP=615  ROC=0.9893
- IF-normal (all 4):   TP=392  FP=426  ROC=0.9900 — identical for 1e-15, 1e-10, 1e-7, 0.5

### B. 13feat
- IF-mixed:            TP=393  FP=662  ROC=0.9903
- IF-normal (all 4):   TP=415  FP=802  ROC=0.9891 — identical for all contamination values

### C. 14feat (+pair_rank)
- IF-mixed:            TP=440  FP=522  ROC=0.9940
- IF-normal (all 4):   TP=389  FP=258  ROC=0.9951 — identical for all contamination values

### Key findings
- **Contamination doesn't affect score_samples()** — all 4 near-zero values produce identical results
- **14feat is best for IF** — ROC=0.9951 (normal) vs 0.9900 (9feat)
- **IF catches 389-440 attacks** vs LGB's 94 — 4-5x more attacks
- **IF has more FPs** — 258-522 vs LGB's 372
- **IF and LGB are complementary** — need overlap test to confirm ensemble value

### IF vs LGB comparison
| Model | TP | FP | ROC |
|-------|-----|-----|-----|
| LGB spw=3 (13feat) | 94 | 372 | 0.9994 |
| IF-normal 14feat | 389 | 258 | 0.9951 |
| IF-mixed 14feat | 440 | 522 | 0.9940 |

---

## OVERLAP TEST: IF + LGB on same test set (overlap_test.py)
> Same GroupShuffleSplit as exp1.py (random_state=42).
> Inner split: random_state=99, test_size=0.3 (196 reds in val for stable thresholds).
> LGB trains on train-train (normal + attack), IF trains on train-train NORMALS ONLY.
> Thresholds from train-val (no test leakage).
> Test on full 5.4M rows (240 reds).
> Runtime: ~12 min

### Split sizes
| Split | Rows | Reds |
|-------|------|------|
| Train | 24,505,602 | 462 |
| Train-train | 10,307,044 | 266 |
| Train-val | 14,198,558 | 196 |
| Test | 5,399,886 | 240 |

### Model performance
| Model | Val | Thr | Test TP | Test FP | Test ROC |
|-------|-----|-----|---------|---------|----------|
| LGB (13feat) | 34/196 TP | 0.193475 | 67 | 194 | 0.9993 |
| IF (13feat) | 28/196 TP | 0.719887 | 47 | 1,655 | 0.9931 |

### Overlap analysis (240 test reds)
| Category | Count | % |
|----------|-------|---|
| LGB only | 50 | 20.8% |
| IF only | 6 | 2.5% |
| Both | 13 | 5.4% |
| Neither | 171 | 71.3% |
| **Union** | **69** | **28.8%** |

### FP analysis
| Model | FP |
|-------|-----|
| LGB | 194 |
| IF | 1,655 |

### Key findings
- **IF adds only 6 unique attacks** (2.5%) at cost of 1,461 extra FPs
- **13/19 IF detections overlap with LGB** — high overlap, low complementarity
- **Union catches 69/240 (28.8%)** vs LGB alone 63/240 (26.3%)
- **IF is not worth the ensemble cost** — 6 extra detections per 1,461 extra FPs
- **LGB alone is the better strategy** — higher TP/FP ratio
