# Experiment Log

> Every row = what we CHANGED + what HAPPENED. Nothing else matters.

## Dataset
- 29.9M events, 702 red attacks, 604 users
- 12 features: dst_first, src_first, hour_ratio, dst_prior_events, fail_1h, vel_1h, hour_sin, hour_cos, is_ntlm, pair_first, fail_rate, dst_first_x_ntlm
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

## RUN 2: FIXED SPLIT (GroupShuffleSplit on src_user)
> No user in both train+test. Numbers are HONEST.
> Train: 24.5M (462 red) / Test: 5.4M (240 red)

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

## VERDICT (after leak fix)
- **LGB spw=100 is broken** — binary output, model can't learn. Change this FIRST.
- **spw=10 = best precision** (TP=51, FP=273)
- **spw=3 = best recall** (TP=99, FP=442)
- **IF is useless alone** — TP=10-31, catches nothing
- **Combined always worse than LGB alone** — IF drags it down
- **New features help IF marginally** but IF is still bad
