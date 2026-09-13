# LANL Anomaly Detection: The Story

29.9M events. 702 attacks. 604 users. We caught 56.7% of them with 0.003% false positives. here's how.

---

## the beginning was a disaster

we split data by row instead of by user. same user in train AND test. every number was fake. spent 2 runs before we noticed.

**fix:** `GroupShuffleSplit` by `src_user`. no user in both splits. honest numbers finally.

## spw=100 is criminal

`scale_pos_weight=100` made LGB output binary 0/1. useless. FP dropped 40x when we switched to spw=3.

## Isolation Forest is L

gave it every chance. normal-only training, contamination sweep, overlap test. it adds 6 unique detections at cost of 1,461 extra FPs. dead.

## deterministic nightmare

DuckDB `rowid` is physical-storage-based. window functions with ties are non-deterministic. two runs, different numbers.

**fix:** 9-column ORDER BY with tiebreaker columns. verified 100% reproducible.

## feature engineering = the real W

built 20 features in SQL CTEs. Config E (20feat) jumped F1 from 0.24 to 0.47. the top 3:
- `iat_zscore` — how unusual is this login timing for THIS user
- `velocity_ratio` — burst detection (1H auths / 24H auths)
- `machine_popularity` — shared resource access pattern

feature engineering > model complexity. always.

## LSTM surprisal caught what LGB missed

trained next-token LSTM on Colab T4. catches 80.4% of attacks but 58k FPs.

overlap with LGB: 71 attacks caught ONLY by LSTM. models are complementary.

but score blending fails. alpha=0.0 wins every time. LSTM's FPs poison any blend.

## DabLog paper proved us wrong

next-token prediction has a fundamental flaw: a rare event ≠ abnormal sequence. need to reconstruct the whole sequence, not predict next token.

**solution:** LSTM Autoencoder. reconstruction error = anomaly score.

## AE recon as Feature 21 = BEST MODEL (RUN 9)

didn't use AE standalone. added reconstruction error as Feature 21 to LGB. LGB learns WHEN to trust the AE score.

| metric | RUN 7 (20feat) | RUN 9 (21feat) | delta |
|--------|---------------|---------------|-------|
| F1 | 0.4817 | **0.4866** | **+0.005** |
| FP | 217 | **183** | **-34** |

## latent PCA = L

128-dim bottleneck → PCA → 16 features. F1 dropped, FP jumped +78. too aggressive compression.

## feature engineering ceiling (RUN 11 = L)

research said percentile normalization = +11.5% AUC. we tried smoothed AE + raw auth counts. F1 dropped -0.013, FP +38.

new features were either redundant or lossy. ceiling reached.

## full research blast

across Context7, Tavily, GitHub, Reddit, Kaggle:
- Kaggle 1st place: 75-200 diverse models → LGB stacker
- Google Facade: FPR < 0.01% at 100k+ employees
- CERT decade review: feature engineering > model complexity
- Reddit: "benchmark accuracy ≠ production performance"
- stacking: diversity > individual model quality

---

## the final model

**RUN 9 — LGB-21feat**

```
ROC:       0.9999
F1:        0.4866
TP:        136 / 240 (56.7%)
FP:        183 / 5,399,646 (0.003%)
```

20 hand-crafted features + 1 AE reconstruction error. on a dataset with 0.002% attack rate, catching 56.7% with 183 FPs across 5.4M events is a W.

## what we learned

1. split by user not row (fake numbers otherwise)
2. spw=100 → binary output (use spw=3)
3. IF is dead for this dataset
4. score blending always hurts (structural integration > averaging)
5. feature engineering > model complexity
6. AE recon error as a feature works (LGB learns when to trust it)
7. feature engineering has a ceiling
8. 64 reds (26.7%) genuinely unlcatchable with this data

## timeline

| day | what happened |
|-----|---------------|
| sep 10 | leaked splits, realized the problem |
| sep 11 | fixed split, deterministic fixes, IF fine-tune |
| sep 12 | Config A-E, LSTM trained on Colab |
| sep 13 | RUN 7-10, AE recon as feature = best model |
| sep 14 | research blast, RUN 11 = L, RUN 9 final |
