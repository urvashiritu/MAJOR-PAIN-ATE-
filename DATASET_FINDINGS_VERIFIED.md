# Dataset Findings — Verified on the Real Data 

**Team:** Hemanth | Urvashi | Veenashree | Vishwanath
**Guide:** Dr. Anitha A C
**Last verified:** Aug 1, 2026


---

## 1. The project in one paragraph

We are building a system that watches login events (like "someone logged in from India on an iPhone at 2pm") and flags the suspicious ones ("someone logged in from Russia at 3am on an Android — that's weird for this user"). We use 4 machine learning models trained on **31 million real login events** from a published academic dataset (RBA, Telenor Norway). During the demo, login events arrive live from a second laptop, get scored by the models, and show up on a dashboard as green (safe) or red (alert).

---

## 2. Plain-English glossary

| Word | What it means, simply |
|---|---|
| **Dataset** | A big table of data. Ours is one giant CSV file with 31.2 million rows, one row per login event |
| **Row / event** | One login attempt: who, when, from which country, on which device, did it succeed |
| **Feature** | A single number we compute from a row. Example: `hour` (what time of day), `country_change` (was this a country the user never logged in from before) |
| **Label** | The truth: is this row an attack (1) or not (0). The model tries to predict this |
| **Model** | A program that learns patterns from data. We use 4 of them (Isolation Forest, One-Class SVM, LOF, Elliptic Envelope) |
| **Training** | Showing the model labeled examples so it learns "what attacks look like" |
| **Anomaly** | Something unusual. A login from a new country at 3am is an anomaly |
| **Sampling** | Picking a smaller, representative chunk out of the big dataset (we can't fit 31M rows in RAM) |
| **Train/test split** | Cut the data in two: train the model on part A, test it on part B it never saw. If it works on part B, it works on *new* events |
| **Attack ratio** | What fraction of rows are attacks. If 10% of rows are attacks, ratio = 0.10 |
| **ATO** | Account Takeover — a real account got hacked (the gold-standard label in our data) |

---

## 3. Our dataset — the VERIFIED facts

Someone actually scanned all 31,269,264 rows (it takes only 5 seconds on our laptop with DuckDB). These numbers are real, not from memory or old notes:

| Fact | Value |
|---|---|
| Total login events | **31,269,264** |
| Unique users | **4,304,857** |
| Date range | **Feb 2020 → Feb 2021 (~1 year)** ⚠️ old docs said 2 years — wrong |
| Account takeovers (ATOs) | **141** (from 138 users) ⚠️ old docs said 87 — wrong |
| Attack-IP flagged rows | **3,096,977 (~9.9%)** |
| — of which SUCCESSFUL logins | **804,491** (the real "compromised account" signal) |
| Missing values in key columns | 0 (data is complete, but see §4.4 for quality issues) |
| Countries seen | 229 |
| Device types | 5 (mobile, desktop, tablet, +2) |
| Median events per user | 2 |
| p90 events per user | 9 |

---

## 4. Key Dataset Discoveries

Our full analysis of the **31.3 million event RBA dataset** uncovered several findings that significantly influenced our preprocessing, sampling strategy, and feature engineering pipeline.

### 4.1 The Robot User (Most Important)

One single user accounts for **14,025,899 login events (44.86% of the entire dataset)**.

Further analysis showed that this user:

- Logs in **300,000–800,000 times every hour**, 24×7 for nearly a year.
- Appears from **~200 different countries**.
- Uses hundreds of browser and operating system combinations.
- Frequently appears with automated user agents such as **ZipppBot**, **startmebot**, and **VLC**.
- Contributes **23% of all Browser–OS inconsistencies** found in the dataset.

This user is clearly not representative of normal human behavior and is likely a synthetic service account or automated background actor.

**Why it matters:** Random row sampling would result in nearly half of the training data coming from this single identity. The model would learn one robot's behavior instead of general human login behavior. This user also contributes over **53% of all Attack IP events**, making it critical to handle carefully during preprocessing.

**Our approach:** Rather than removing the user, we cap its contribution during sampling and compare model performance with and without the dominant account to determine the least biased training strategy.

---

### 4.2 Highly Imbalanced User Activity

The dataset contains **4,304,857 unique users**, but login activity is extremely skewed.

| Statistic | Value |
|-----------|------:|
| Total Users | 4,304,857 |
| Mean Logins/User | 7.26 |
| Median | 2 |
| 90th Percentile | 9 |
| 95th Percentile | 13 |
| 99th Percentile | 28 |
| Maximum | 14,025,899 |

Most users perform only a handful of logins, while one account dominates nearly half of the dataset.

Further analysis also revealed:

- **41 users account for approximately 1.66 million Attack IP events (54% of all attacks).**
- **8,122 users have at least 10 attack events.**
- **More than 742,000 attack users have only one or two attack events.**

**Why it matters:** Attack behaviour is highly concentrated. Simple random sampling would overrepresent a few highly active users while underrepresenting millions of normal users. A user-aware, tiered sampling strategy is therefore required.

---

### 4.3 The Gold Signal: Successful Logins from Bad IPs

The dataset contains valuable real-world attack scenarios:

- **3,096,977 Attack IP events**
- **804,491 successful logins from Attack IP addresses**
- **141 confirmed Account Takeover (ATO) events**
- **140 of the 141 ATO events are successful logins**
- Only **77 events overlap** between the Attack IP and Account Takeover labels, meaning Attack IP alone does not capture every takeover.

**Why it matters:** These are the most valuable training examples for identity anomaly detection. Successful logins from malicious IPs closely resemble real account compromise scenarios, making them essential for training and evaluation.

---

### 4.4 Dataset Quality Issues

Comprehensive profiling identified several data quality characteristics that require preprocessing.

- **95.92% of Round-Trip Time (RTT) values are missing**, while all other important columns are nearly complete.
- **4,549 distinct browser strings** exist, many differing only by version numbers (e.g., `Firefox 20.0.0.1618`), which would artificially create new devices after every browser update.
- Automated user agents such as **ZipppBot**, **Linkbot**, **startmebot**, **AwarioSmartBot**, and **VLC** appear throughout the dataset.
- The Browser column occasionally contains operating system names (e.g., **Android**) instead of actual browsers.

**Why it matters:** Without normalization, features such as `device_change`, `browser_change`, and user profiling would generate many false anomalies.

---

### 4.5 Browser–OS Inconsistencies

Our analysis uncovered widespread inconsistencies between browser and operating system values.

- **1,126,457 login events (3.60% of the dataset)** contain impossible Browser–OS combinations such as **Android Browser + iOS OS**.
- The dominant user contributes only **23%** of these inconsistencies, while the remaining **77%** are distributed across the rest of the dataset.
- The original project documentation attributed these inconsistencies only to synthetic data generation, but our full-dataset analysis confirmed that they are present throughout the actual RBA dataset as well.

**Why it matters:** Browser and operating system values cannot be used directly for behavioral features. They must first be normalized into browser and OS families before features such as `device_change` are computed.

---

### 4.6 Data Integrity Verification

Before preprocessing, we verified the integrity of the original dataset.

- **31,269,264 login events**
- **0 duplicate rows**
- **No missing or invalid timestamps**
- Dataset spans **03 February 2020 – 28 February 2021**
- Events are already **chronologically sorted**

**Why it matters:** These checks confirm that the dataset is structurally reliable and does not require duplicate removal or timestamp correction. Preprocessing can therefore focus on behavioral normalization and feature engineering rather than repairing corrupted records.

---

### 4.7 Preprocessing Strategy

Based on these findings, our preprocessing pipeline performs the following steps before model training:

- Normalize browser names by removing version numbers.
- Normalize operating systems into major OS families.
- Preserve known automated user agents as separate categories.
- Handle Browser–OS inconsistencies before feature engineering.
- Apply user-aware sampling to reduce bias from the dominant account.
- Retain all Account Takeover events and successful attack logins.
- Generate behavioral features such as `country_change`, `device_change`, `failed_before_success`, `rapid_login_rate`, and `login_frequency_today` on the cleaned dataset.

These preprocessing decisions ensure that the downstream anomaly detection models learn representative user behavior rather than artifacts introduced by dataset imbalance or synthetic characteristics.


## 5. Why the old training file is broken

The current `data/processed/training_data.csv` (18,191 rows) is broken and will be replaced. Step by step:

1. We sampled 50,000 rows aiming for 10% attacks → 5,000 attack rows ✓
2. We kept only users with 3+ events → 18,191 rows survived
3. **But only 248 attack rows survived — the attack ratio collapsed from 10% to 1.36%**

**Why:** attacks are spread thin across users (most attack users have 1–2 attack rows). Deleting users with few events deleted most attack rows with them.

**Result:** models trained on this file basically never saw attacks → measured recall was ~2% (the 94.2% accuracy in the docs was never actually achieved — that's fixed in this doc, see §8 FAQ).

**The fix:** sample by **user** (pick users, keep their events), filter first, then balance — not by row.

---

## 6. The plan going forward (Phase 2 + 3 + 4)

1. **Clean the data** — strip browser/OS versions, handle impossible combos, drop junk rows if needed
2. **Tiered user-based sampling (~1M rows)**:
   - ALL 138 ATO users (the gold)
   - Attack-heavy users (≥10 attacks) — keep most
   - Random light-attack users + pure-normal users
   - The robot user: capped (e.g. 50K rows) + A/B test with/without
   - Per-user event cap (~10K) so no single user dominates
   - Target attack ratio 5–10%
3. **Full-dataset baselines** — per-user "countries seen / devices seen" computed from ALL 31.3M rows via DuckDB (cheap, ~5s scans), so `country_change` / `device_change` are accurate even in a 1M-row sample
4. **Feature engineering fixes** (from the verified issues):
   - `device_change`: no version numbers
   - `failed_before_success`: true 5-minute window (old code counted "since last success" — wrong)
   - First-ever login per user → `country_change = 0`
5. **User-based 80/20 split** — train on 80% of users, test on 20% of users NEVER seen in training. This is the honest proof for "new login events shouldn't fail": if the model works on strangers' logins, it works on new logins
6. **Train 4 models + honest evaluation** — threshold sweep, real precision/recall/F1, charts; `contamination` set from the real attack ratio (was hardcoded to 0.05 before)
7. **Docs phase** — rewrite reports with measured numbers (no more fake 94%)

---

## 7. What each teammate should do

| Member | Role | What to do |
|---|---|---|
| **Hemanth** | Data Pipeline | Own the clean + sample + feature engineering code (`src/01_build_training_data.py`) |
| **Urvashi** | ML Models | Own training + evaluation (`src/02_train_models.py`, `src/03_evaluate.py`) — train on Hemanth's output, report REAL numbers |
| **Veenashree** | Dashboard | Own the dashboard (Streamlit) that shows live events + alerts |
| **Vishwanath** | Live Demo | Own the FastAPI server + client + device fingerprinting |

Dependency chain: **Hemanth → Urvashi → Vishwanath & Veenashree** (data first, models second, demo/dashboard last).

---

## 8. FAQ

**Q: Is the ML real, or just rules?**
A: Real. The features are computed by rules (e.g. "new country = 1"), but the 4 models learn patterns across ALL 8 features at once from real labeled data. Rules can't capture "new country + 3am + new device = very suspicious, but new country + 2pm + same device = probably travel."

**Q: Why 4 models instead of 1?**
A: They catch different kinds of weirdness (rare events, boundary cases, local oddities, statistical outliers). Averaging their scores reduces false alarms — one model saying "weird" isn't enough, four agreeing is.

**Q: Why not use all 31M rows for training?**
A: Because 45% of them are one robot's repeated failures — the same pattern millions of times. A well-chosen ~1M-row sample contains the same information (all attack patterns, all ATO users, representative normal behavior) and trains in minutes instead of hours. Baselines are still computed over ALL 31M rows.

**Q: What if a real user travels and logs in from a new country?**
A: It will look suspicious at first (that's correct behavior), then the system "learns" — once a country/device is seen, it's no longer flagged. Plus the dashboard has a "This was me" button to confirm. We alert, we never block.

**Q: The old docs say 94.2% accuracy. Where did that come from?**
A: It was never measured — no code produced it. The real measured output was ~2% recall. Those numbers are now marked as unverified in the docs and will be replaced with real measurements after retraining.

**Q: What can't the system detect?**
A: Honest answer: perfect mimic (stolen laptop + password + identical typing), MFA bypass, and post-login insider activity. Everyone has these limits — Google and Microsoft handle them with extra controls (MFA, hardware keys, endpoint monitoring), which we document as future scope.

**Q: How is this better than the 5M-row cache in the old project folder?**
A: That cache is a transformed sample from an old experiment (engineered columns, only 5M rows) — it is NOT the raw data and can't be used to rebuild. We build a fresh cache from the raw CSV (takes ~1 minute).

---

*Anything in the old docs that contradicts this file is wrong. This file is the verified truth as of Aug 1, 2026.*
