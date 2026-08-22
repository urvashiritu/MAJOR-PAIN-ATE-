# 3 Paths Experiment Results — MAJOR-PAIN-ATE-

## Overview

Three independent experiment paths were built to compare different approaches to login anomaly detection on the RBA and LANL datasets.

| Path | Dataset | Models | Dashboard | Port |
|---|---|---|---|---|
| `rba-anomaly/` | RBA 1M sample | LOF/IF/OCSVM/EE (anomaly) | Shared React | 5000 |
| `rba-xgboost/` | RBA 1M sample | XGBoost+RF (supervised) | Shared React | 5001 |
| `lanl-anomaly/` | LANL 10M | LOF/IF/OCSVM/EE (anomaly) | New React (auth events) | 5002 |

---

## Datasets

### RBA (primary)

- **Source:** Zenodo 6782156
- **Full size:** 31,269,264 rows, 8.5 GB CSV
- **Users:** 4,304,857 unique, 229 countries
- **Time span:** Feb 2020 — Feb 2021 (13 months)
- **Takeovers:** 141 confirmed account-takeover events
- **Attack IP events:** 3,096,977 (IP blocklist, NOT behavioral label)
- **Key finding:** `is_attack_ip` is an IP blocklist lookup, not a behavioral ground-truth label

### LANL cyber1

- **Source:** Kaggle (MITRE CERT dataset)
- **Full auth events:** 1,051,430,459
- **Slice used:** 29,905,488 events, 604 users (104 red-team + 500 normal)
- **Training subset:** 10,038,139 rows (`feat_10m.parquet`)
- **Red-team events:** 749 total
- **Key finding:** No blocklist possible — pure behavioral detection

---

## Experiment A: RBA Rule Baseline

**1,000,003 rows scored. Gates: PASS.**

| Level | Rows | Avg Score | Bounds |
|---|---|---|---|
| Low | 524,885 | 11.7 | 0–29 |
| Medium | 392,819 | 47.4 | 30–64 |
| High | 67,365 | 75.1 | 65–89 |
| Critical | 14,934 | 103.8 | 90+ |
| Normal (score 0) | 212,869 | 0.0 | — |

**Rule points:** country=30, new_ip=25, failed=20, hour=15, rapid=15, new_asn=15, device=10, freq=10, new_os=7, new_browser=7

**Practical result:** ~79% of real ATOs caught at 10% challenge rate, ~11% of normal users bothered.

---

## Experiment B: RBA Anomaly Models (1M sample, 21 features)

**Split:** 787,770 train / 212,233 test (per-user 70/30 chronological)  
**Contamination:** 25.04% (train attack-IP share)  
**FPR budget:** 5%  
**Tuned on:** gold = `is_attack_ip` AND `login_success`  
**Features (21):** is_night, is_weekend, country_change, device_change, failed_recently, rapid_login_rate, login_frequency_today, hour_sin, hour_cos, geo_unreliable, is_generator_bot, ua_os_conflict, is_private_ip, rtt_missing, is_vlc, ip_seen_before, country_seen_before, asn_seen_before, device_seen_before, os_seen_before, browser_seen_before

| Model | Gold F1 | Precision | Recall | FPR | ROC-AUC | PR-AUC | ATO Detected |
|---|---|---|---|---|---|---|---|
| **Ensemble Trimmed (LOF+OCSVM+EE)** | **0.111** | 0.213 | 0.075 | 0.050 | 0.536 | 0.176 | 1/14 |
| Local Outlier Factor | 0.092 | 0.182 | 0.062 | 0.050 | 0.524 | 0.164 | 1/14 |
| One-Class SVM | 0.092 | 0.183 | 0.061 | 0.049 | 0.518 | 0.159 | 1/14 |
| Ensemble All (4 models) | 0.074 | 0.150 | 0.049 | 0.050 | 0.505 | 0.150 | 1/14 |
| Elliptic Envelope | 0.000 | 0.000 | 0.000 | 0.050 | 0.532 | 0.160 | 0/14 |
| Isolation Forest | 0.003 | 0.006 | 0.002 | 0.049 | 0.437 | 0.125 | 0/14 |

**Best single:** LOF (F1 0.092)  
**Best ensemble:** Trimmed ensemble (F1 0.111) — beats best single  
**Blocklist baseline:** F1 0.747 — beats everything  

**Saved:** `rba-anomaly/models/rba_anomaly.joblib` (182 MB)

---

## Experiment C: RBA Anomaly Models (float32 variant)

Same data, float32 dtype, n_jobs=4.

| Model | Gold F1 | ROC-AUC |
|---|---|---|
| **Ensemble Trimmed (LOF+EE)** | **0.131** | 0.565 |
| Local Outlier Factor | 0.101 | 0.549 |
| One-Class SVM | 0.049 | 0.480 |
| Elliptic Envelope | 0.032 | 0.568 |
| Isolation Forest | 0.026 | 0.468 |
| Ensemble All | 0.048 | 0.539 |

---

## Experiment D: LANL Anomaly Models (10M rows, 8 features)

**Split:** 7,026,783 train / 3,011,356 test (per-user 70/30)  
**Contamination:** 0.0083% (580 red events in train)  
**Test reds:** 4 / 3,011,356  
**Features (8):** dst_first, src_first, hour_ratio, dst_prior_events, fail_1h, vel_1h, hour_sin, hour_cos  
**Tuned on:** is_red, FPR ≤ 5%

| Model | F1 | Precision | Recall | FPR | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|
| **Elliptic Envelope** | **0.333** | 0.500 | 0.250 | 0.000 | **1.000** | 0.148 |
| Isolation Forest | 0.001 | 0.000 | 0.750 | 0.004 | 0.994 | 0.000 |
| LOF | 0.003 | 0.002 | 0.250 | 0.000 | 0.814 | 0.000 |
| OCSVM | 0.000 | 0.000 | 0.000 | 0.050 | 0.078 | 0.000 |
| Ensemble Trimmed | 0.003 | 0.002 | 0.250 | 0.000 | 0.946 | 0.000 |
| Oracle (attacker machines known) | 0.011 | 0.006 | 1.000 | 0.000 | 1.000 | 0.006 |

**Best single:** Elliptic Envelope (F1 0.333, ROC-AUC 1.0)  
**Ensemble does NOT beat best single on LANL.**

**Saved:** `lanl-anomaly/models/lanl_ensemble.joblib` (68 MB)

---

## Experiment E: LANL Feasibility Analysis

Per-feature ROC-AUC (702 red events):

| Feature | A vs B (own normal) | A vs C (other users) |
|---|---|---|
| dst_prior_events | **0.970** | **0.905** |
| vel_1h | 0.810 | 0.586 |
| hour_ratio | 0.711 | 0.352 |
| fail_1h | 0.657 | 0.665 |
| dst_first | 0.650 | 0.649 |
| src_first | 0.552 | 0.552 |

**Verdict:** SEPARABLE — PASS. Behavioral signals are real (0.65–0.97 AUCs).

---

## Experiment F: LANL Latency Benchmark (1M sample)

| Model | Fit Time | Score Time | Total | Projected 20M |
|---|---|---|---|---|
| OCSVM | 0.92s | 0.01s | 0.93s | 0.3 min |
| Isolation Forest | 2.0s | 1.58s | 3.58s | 1.2 min |
| Elliptic Envelope | 27.5s | 0.05s | 27.54s | 9.6 min |
| LOF | 51.1s | 49.04s | 100.14s | 42.6 min |

---

## Models Trained and Saved

| Model | Path | Size | Status |
|---|---|---|---|
| RBA anomaly (LOF+EE ensemble) | `rba-anomaly/models/rba_anomaly.joblib` | 182 MB | **TRAINED** |
| LANL anomaly (4 models) | `lanl-anomaly/models/lanl_ensemble.joblib` | 68 MB | **TRAINED** |
| RBA XGBoost (supervised) | `rba-xgboost/models/` | — | **NOT TRAINED** |

---

## Key Conclusions

1. **Rules beat ML on RBA** — blocklist F1=0.747 vs best ML F1=0.111. The label IS the blocklist.
2. **ML works on honest data** — LANL (no IPs, no blocklist) → Elliptic Envelope F1=0.333, ROC-AUC=1.0.
3. **Anomaly models are weak on RBA** — 21 features with no temporal window functions aren't enough.
4. **The real value is the rule engine** — catches 79% of ATOs at 10% challenge rate.
5. **Supervised XGBoost is the next experiment** — uses attack labels, might beat anomaly models significantly.
6. **5 temporal features missing** — hours_since_last_login, login_frequency_24h, hour_deviation, unique_ips_7d, impossible_travel. Rebuild in progress.

---

## What's NOT Done

| Item | Status |
|---|---|
| Feature rebuild (temporal features) | Running now |
| Re-sample after rebuild | Pending |
| Train RBA XGBoost | Pending |
| Adapt scoring.py for model-type detection | Pending |
| LANL custom React dashboard | Not started |
| Live demo test with all 3 models | Pending |
