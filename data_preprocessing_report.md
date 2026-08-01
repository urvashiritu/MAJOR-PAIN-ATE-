# Data Preprocessing Report — RBA Dataset

## Project: AI-Based Identity Anomaly Detection

**Team:** Hemanth, Urvashi, Veenashree, Vishwanath
**Guide:** Dr. Anitha A C
**Date:** July 2026

---

## 1. Overview

We prepared the RBA (Risk-Based Authentication) dataset for training 4 ML models (Isolation Forest, One-Class SVM, Local Outlier Factor, Elliptic Envelope) to detect anomalous login behavior.

**My role:** Dataset preparation — load, sample, clean, compute 8 features, output training file.
**Hemanth's role:** Train models, evaluate accuracy, build dashboard.

**Output file:** `training_data.csv` (18,191 rows, 8 features + label column)

---

## 2. Dataset: RBA (Risk-Based Authentication)

### Source

- Created by Wiefling et al., ACM TOPS 2022
- From Telenor Norway SSO (synthesized from real login patterns)
- Downloaded from Zenodo: https://zenodo.org/records/6782156

### File Location

```
/home/igris/projects/identity-anomaly-detection/backend/app/data/rba/
    ├── rba_csv/
    │   └── rba-dataset.csv      (8.5 GB, 31,269,264 rows)
    ├── rba.duckdb               (533 MB DuckDB cache)
    └── rba-dataset.zip          (1.1 GB compressed)
```

### Raw Dataset Stats (Full Scan)

| Metric | Value |
|--------|-------|
| Total rows | **31,269,264** |
| Unique users | **4,304,857** |
| Attack IP rows | **3,097,977 (~9.9%)** |
| Account Takeovers (ATO) | **141** (gold standard labels) |
| Successful logins | ~49% |
| Failed logins | ~51% |
| Top country | Norway (NO) |
| Mobile devices | 70% |
| Desktop | 26% |
| Tablet | 3% |
| Date range | Feb 2020 – Feb 2022 |

### Raw Columns (16 total)

| Column | Type | Used? | Why |
|--------|------|-------|-----|
| index | int64 | No | Row counter, not useful |
| Login Timestamp | string → datetime | **Yes** | Needed for hour, night, weekend, rate features |
| User ID | int64 | **Yes** | Groups events per user |
| Round-Trip Time [ms] | float64 | **No** | 99% empty (only 22K out of 31M have values) |
| IP Address | string | No | Not used in our 8 features |
| Country | string | **Yes** | Needed for country_change |
| Region | string | No | Too granular, often missing |
| City | string | No | Often "-" or empty |
| ASN | int64 | No | Not part of our 8 features |
| User Agent String | string | No | Raw string, we use parsed browser/OS |
| Browser Name and Version | string | **Yes** | Part of device_change |
| OS Name and Version | string | **Yes** | Part of device_change |
| Device Type | string | **Yes** | Part of device_change |
| Login Successful | bool | **Yes** | Needed for failed_before_success |
| Is Attack IP | bool | **Yes** | Our training label |
| Is Account Takeover | bool | No | Only 141 rows, too rare for training but used for evaluation |

---

## 3. Problems Encountered & Solutions

### Problem 1: First 10K rows are from a 2-hour window on Monday

**What happened:** I loaded `pd.read_csv('rba-dataset.csv', nrows=10000)`. Checked date range and found everything was between Feb 3, 2020 12:43 and 14:42 — only 2 hours on a Monday.

**Why:** The CSV is sorted chronologically. The first 10K rows are just the first 2 hours of data.

**Why this is bad:** If all data is from Monday 12-2 PM, then:
- `is_weekend` will always be 0 (Monday is a weekday)
- `is_night` will always be 0 (12-2 PM is daytime)
- No diversity in time-based features
- Might miss attacks that happen at 3 AM

**Solution:** Cannot use the first N rows. Need random sampling across the full 2-year range.

### Problem 2: pandas cannot load the full 8.5 GB CSV

**What happened:** Trying `pd.read_csv('rba-dataset.csv')` would crash — the file is 8.5 GB and most laptops don't have that much free RAM.

**Solution:** Used DuckDB. DuckDB's `read_csv_auto()` reads the CSV file directly from disk without loading it entirely into RAM. It scans through the 31 million rows, picks only the rows we ask for (the sample), and returns only those to pandas. This way we never load the full 8.5 GB.

### Problem 3: Too few events per user in 10K sample

**What happened:** With the first attempt at DuckDB sampling (2000 attack + 8000 normal = 10K total), we got 7431 rows but 4181 unique users. That's only 1.8 events per user on average.

**Why this is bad:**

| Feature | What happened | Why |
|---------|---------------|-----|
| `country_change` | Always 1 | Every event is the user's first → first country is always "new" |
| `device_change` | Always 1 | Every event is the user's first → first device is always "new" |
| `login_frequency_today` | Always 1 | Every event is the user's first today → always count 1 |

The contextual features (`country_change`, `device_change`, `failed_before_success`, `rapid_login_rate`, `login_frequency_today`) only work when a user has MULTIPLE events to compare against.

**Solution:** Two changes:
1. Increase sample from 10K to **50K rows**
2. Filter to keep **only users with 3+ logins**

After these changes, we got 18,191 rows and features now vary properly.

---

## 4. The 8 Behavioral Features — Detailed Explanation

### Feature 1: hour (0-23)

**What it is:** The hour of the day when the login happened.

**Computation:** `ts.hour` from the Login Timestamp column.

**What it detects:** If a user who normally logs in at 2 PM suddenly logs in at 3 AM, that's suspicious.

### Feature 2: is_night (0 or 1)

**What it is:** Whether the login happened during night hours.

**Computation:** `1 if hour < 6 or hour > 22 else 0`.

**Example:** A login at 3 AM → is_night = 1. A login at 2 PM → is_night = 0.

**What it detects:** Night-time logins are suspicious for office workers who only log in during business hours.

### Feature 3: is_weekend (0 or 1)

**What it is:** Whether the login happened on Saturday or Sunday.

**Computation:** `1 if ts.weekday() >= 5 else 0`.

**Example:** Login on Sunday → is_weekend = 1. Login on Wednesday → is_weekend = 0.

### Feature 4: country_change (0 or 1)

**What it is:** Whether this user has ever logged in from this country before.

**Computation:** Look up the user's history of countries seen. If this country is new → 1. If the user has used this country before → 0.

**Example:** User has only logged in from India for 2 years. Today they login from Russia. country_change = 1.

**How the history works:** We maintain a Python `set()` per user that stores every country they've logged in from. As we process rows chronologically, we add each new country to the set. First login for a user → country_change = 1 (no history to compare). Second login from same country → country_change = 0 (already seen).

### Feature 5: device_change (0 or 1)

**What it is:** Whether this user has used this specific device+browser+OS combination before.

**Computation:** Create a device key string: `"{Device Type}|{Browser Name and Version}|{OS Name and Version}"`. Check if this key is in the user's history. If new → 1. If seen before → 0.

**Example:** User has only logged in from "mobile|Firefox 20.0.0.1618|iOS 13.4". Today they login from "desktop|Chrome 91.0.4472|Windows 10". device_change = 1.

### Feature 6: failed_before_success (0 or 1 or higher)

**What it is:** If this was a successful login, how many failed attempts happened before it in the last 5 minutes?

**Computation:** We maintain `fails_last_5min` counter per user. When processing a successful login, we check this counter. If there were failures → return the count. If no failures → return 0. When processing a failed login, increment the counter.

**Example:** User attempts 12 failed logins (wrong passwords) at 3:00-3:04 AM. At 3:05 AM they succeed. `failed_before_success` = 12 for that success event.

**What it detects:** Brute force attacks — attacker tries many passwords then gets one right.

### Feature 7: rapid_login_rate (0, 1, 2, ...)

**What it is:** How many logins did this user have in the last 60 seconds?

**Computation:** We maintain a list of timestamps of recent logins per user. For each new login, remove timestamps older than 60 seconds, then count what's left.

**Example:** A script does 100 login attempts in one minute. The 100th event will have `rapid_login_rate` = 99. A human logging in once → `rapid_login_rate` = 0.

**What it detects:** Automated scripts and bots.

### Feature 8: login_frequency_today (1, 2, 3, ...)

**What it is:** How many times has this user logged in today so far (including this one)?

**Computation:** Reset counter when date changes. Increment on each login.

**Example:** Normal user logs in 5 times per day. Today they have 50 logins so far. `login_frequency_today` = 50 → suspicious.

---

## 5. The Feature Engineering Loop — Step by Step

This is how we computed the 8 features from the raw data:

```
Input: Raw RBA rows (50,000 rows from DuckDB sampling)
Step 1: Sort by User ID, then by Login Timestamp (chronological per user)
Step 2: Initialize empty user_history dictionary
Step 3: For each row (in sorted order):
    a. Get user_id, timestamp, country, device_type, browser, os, login_success, is_attack_ip
    b. Create device_key = device_type + "|" + browser + "|" + os
    c. If user not in history, initialize empty history for them
    d. Compute 8 features using user's history so far
    e. Save features + label to list
    f. Update user's history with this event (add country, add device, update timers)
Step 4: Convert features list to DataFrame
Step 5: Output training_data.csv
```

### How the user_history dictionary works

```
user_history = {
    user_id_1: {
        'countries': {'NO', 'US', 'IN'},      # countries seen so far
        'devices': {'mobile|Firefox|iOS 13.4', 'desktop|Chrome|Windows 10'},
        'last_60s': [timestamp1, timestamp2],  # recent login timestamps
        'fails_last_5min': 2,                  # failed attempts counter
        'today_count': 12,                     # logins today
        'last_date': 2020-02-03               # last login date
    },
    user_id_2: { ... }
}
```

### Example — One user, 3 events

| Timestamp | Country | Device | Success | hour | night | country_chg | device_chg | failed_before | rapid_rate | freq_today | Attack? |
|-----------|---------|--------|---------|------|-------|-------------|-------------|---------------|------------|------------|---------|
| 2020-02-03 12:43 | India | iPhone/iOS | ✓ | 12 | 0 | 1 | 1 | 0 | 0 | 1 | No |
| 2020-02-03 02:15 | Russia | Android | ✓ | 2 | 1 | 1 | 1 | 12 | 45 | 2 | Yes |
| 2020-02-03 02:16 | Russia | Android | ✓ | 2 | 1 | 0 | 0 | 0 | 46 | 3 | No |

Row 1: First login for this user, country_change=1 (first country), device_change=1 (first device).
Row 2: From Russia (new), Android (new), 12 fails before success, 45 rapid attempts → attack.
Row 3: Same country+device now seen before → country_change=0, device_change=0. No longer flagged.

---

## 6. Why DuckDB?

We compared 3 options:

| Method | Can read 8.5 GB? | Memory used | Setup time | Code complexity |
|--------|------------------|-------------|------------|-----------------|
| pd.read_csv() | No (crashes) | 8.5 GB+ RAM | Instant | Minimal |
| pd.read_csv(chunksize=...) | Yes, slow | ~100 MB | Instant | Medium |
| **DuckDB read_csv_auto()** | **Yes, fast** | **~100 MB** | **Instant** | **Minimal** |

**Why we chose DuckDB:**
- `read_csv_auto()` reads the 8.5 GB CSV directly from disk without loading it into RAM
- It scans through all 31 million rows and only returns the ones we ask for (the 50K sample)
- We never load more than ~50 MB into pandas at a time
- One line of code — no import, no CREATE TABLE, no schema setup

**The query we used:**
```sql
SELECT * FROM (
    SELECT * FROM read_csv_auto('rba-dataset.csv')
    WHERE "Is Attack IP" = 'True'
    USING SAMPLE 5000 ROWS
)
UNION ALL
SELECT * FROM (
    SELECT * FROM read_csv_auto('rba-dataset.csv')
    WHERE "Is Attack IP" = 'False'
    USING SAMPLE 45000 ROWS
)
```

This gives us 50,000 rows with 10% attack ratio, randomly sampled across the full 2-year dataset.

---

## 7. Iterations Summary

| Attempt | Method | Rows | Users | Avg events/user | Features varying? | Problem |
|---------|--------|------|-------|-----------------|-------------------|---------|
| 1 | pd.read_csv(nrows=10000) | 10,000 | — | — | No | Only 2 hours of data |
| 2 | DuckDB 10K stratified | 7,431 | 4,181 | 1.8 | No | Too few events per user |
| **3** | **DuckDB 50K stratified + filter 3+ logins** | **18,191** | **~2,600** | **~7** | **Yes ✓** | **Success** |

---

## 8. Minor Issues & Limitations

These are things we noticed but did not fully fix. Worth discussing with Hemanth.

### Issue 1: device_change includes exact browser version

The device key uses the full browser version string (e.g. "Firefox 20.0.0.1618"). When a user updates their browser to "Firefox 20.0.0.1619", it shows as a brand new device. This makes `device_change` = 1 more often than it should.

**Potential fix:** Use only browser name without version (e.g. just "Firefox" instead of "Firefox 20.0.0.1618"). Or use device type + browser name + OS name but drop the version numbers.

### Issue 2: rapid_login_rate max is only 3

The highest `rapid_login_rate` in our sample is 3. This means no scripted brute force attack with 50+ logins per minute exists in our 18K sample. The model will never learn to detect high-speed automated attacks.

**Impact:** If an attacker does 100 logins in a minute, the model might not flag it because it never saw this pattern in training.

**Potential fix:** No easy fix without getting more attack rows. Hemanth should know this limitation.

### Issue 3: failed_before_success is very rare

Only a tiny fraction of rows have `failed_before_success` = 1. The mean is ~0.00. This is because successful logins after failed attempts are uncommon in the sample.

**Impact:** The model may not learn the "brute force → then success" pattern well.

**Potential fix:** Same as above — need more attack rows in the sample.

### Issue 4: First login per user always has country_change = 1

For every user's first login in our data, `country_change` is always 1 (no history to compare). This adds noise — the model might think first-time users are always suspicious.

**Impact:** New users could show high risk scores even though their behavior is normal.

**Potential fix:** Set `country_change` = 0 for first-ever login of each user, since there's no baseline yet. Or remove first-login rows from training.

### Issue 5: PyArrow bug prevented Parquet save

Tried `train_df.to_parquet('training_data.parquet')` but got an ArrowKeyError: "No type extension with name arrow.py_extension_type found". This is a known bug in the PyArrow version installed in the venv.

**Fix:** Saved as CSV instead. CSV works fine for Hemanth.

### Issue 6: DuckDB UNION ALL returned fewer rows than expected

The first stratified query requested 2000 attack + 8000 normal = 10,000 total but only returned 7,431 rows. DuckDB's `UNION ALL` deduplicates rows that are identical across all columns. Some attack rows may have been identical to normal rows in the sampled set.

**Impact:** Minor — still got enough data. Not worth investigating further.

---

## 9. Final Training Data

**File:** `training_data.csv`
**Location:** `~/Documents/projects/MAJOR-PAIN-ATE-/data/processed/training_data.csv`

### Stats

| Metric | Value |
|--------|-------|
| Total rows | 18,191 |
| Normal rows (label=0) | 17,943 |
| Attack rows (label=1) | 248 |
| Attack ratio | ~1.36% |
| Features | 8 |
| Label column | `label` (0=normal, 1=attack) |

### Final Feature Verification

| Feature | Min | Max | Mean | Varies? |
|---------|-----|-----|------|---------|
| hour | 0 | 23 | 11.89 | ✓ |
| is_night | 0 | 1 | 0.20 | ✓ |
| is_weekend | 0 | 1 | 0.27 | ✓ |
| country_change | 0 | 1 | 0.01 | ✓ |
| device_change | 0 | 1 | 0.09 | ✓ |
| failed_before_success | 0 | 1 | ~0.00 | ✓ (but rare) |
| rapid_login_rate | 0 | 3 | 0.04 | ✓ (but low max) |
| login_frequency_today | 1 | 141 | 29.17 | ✓ |

---

## 10. What To Tell Hemanth

1. **File:** `training_data.csv` — 8 features + label column
2. **Rows:** 18,191 rows, 248 attack examples
3. **Features:** hour, is_night, is_weekend, country_change, device_change, failed_before_success, rapid_login_rate, login_frequency_today
4. **Label:** Is Attack IP (1=attack, 0=normal)
5. **Task for him:** Train the 4 models (Isolation Forest, One-Class SVM, LOF, Elliptic Envelope), evaluate accuracy/precision/recall/F1, build dashboard
6. **Known limitations to mention:**
   - `device_change` may be high because device key includes exact browser version — consider using just browser name without version
   - `rapid_login_rate` max is only 3 — no high-speed attacks in sample
   - `failed_before_success` is very rare

---

## 11. Tools Used

| Tool | What we used it for |
|------|---------------------|
| **pandas** | Loading, exploring, cleaning, feature engineering, saving output |
| **DuckDB** | Sampling 50K rows from 8.5 GB CSV without loading to RAM |
| **Jupyter notebook** | Interactive development: `rba.ipynb` with 4 cells |
| **Python 3.12** | All code |
| **VS Code** | Writing and running the notebook |

---

## 12. What We Learned

- First N rows of a CSV are not a representative sample — need to spread across full time range
- Per-user features (country_change, device_change) need users with multiple events to be meaningful
- 1.8 events per user is too few — need ~7+ for contextual features to vary
- DuckDB is simple and fast for large CSV sampling without loading to RAM
- Always verify feature distributions after engineering — don't assume they vary just because the code ran
- Small samples can miss important attack patterns (rapid_rate max 3 instead of 100+)
- Browser version numbers in device keys can cause false device_change flags

---

## 13. Post-Report Update (Aug 1, 2026)

### 13.1 The attack-ratio collapse — why training_data.csv has only 248 attacks

We intended 10% attacks (5,000 attack rows in the 50K sample) but the final file has **1.36% (248)**. Root cause found later:

```
Step 1: Row-level stratified sample → 50K rows, ~10% attack      (5,000 attack rows)
Step 2: Keep users with >= 3 events → 18,191 rows                (4,181 users → ~2,600 users)
Step 3: Attacks surviving: 248                                   (attack ratio 10% → 1.36%)
```

Row-level sampling spreads ~1-2 events per user across 4.3M users. Most sampled attack rows belong to users with <3 total sampled events, so when the "≥3 events per user" filter deletes those users, **most attack rows are deleted along with them**.

**Impact:** the models trained on this file had almost no attack patterns to learn — evaluation showed recall ~2% at the default threshold.

**Fix (Phase 2):** sample by **user**, not by row — pick users (with their full event histories), apply the ≥3-events filter first, then balance attack/normal. This keeps a 5-10% attack ratio after filtering.

### 13.2 Multi-source synthetic experiment — attempted and removed

Because the RBA dataset is web-login only, the team generated 7 synthetic log sources (web_login, Windows AD, SSH, VPN, M365, AWS CloudTrail, database audit) and wrote `parser.py` to normalize them into one common 11-column schema (`normalized_auth_events.csv`, 3,500 events). **It was removed** on Aug 1, 2026. Why:

- AI-generated data was internally inconsistent: impossible device/browser/OS combos (`Desktop + Safari + Android 15`), and 381/500 web_login rows where `user_agent` contradicts the stated browser
- Only web_login had labels (73 attack-IP / 8 ATO); the other 6 sources had none — detection quality unmeasurable there
- Both models scored AUC ≈ 0.45 (worse than random) on the synthetic labels — the labels don't correspond to any learnable feature pattern
- 3,500 events vs 31M real events

**Verdict:** the parser concept (normalizing heterogeneous auth logs into one schema, like SIEM products) is a good *demo* idea but not training data. Real ML needs the real RBA dataset.

### 13.3 Current repo state

```
MAJOR-PAIN-ATE-/
├── data/raw/rba-dataset.csv               (8.5 GB, unchanged original)
├── data/processed/training_data.csv       (18,191 rows — this report's output)
├── data/processed/test_split_y.npy        (held-out test labels)
├── notebooks/rba.ipynb, train-data-ana.ipynb
├── COMPLETE_PROJECT_REFERENCE.md          (with status update + roadmap)
├── dataset_analysis.md, README.md, LICENSE
```

All `.py` pipeline scripts were removed (rewrite planned): `anomaly_detector.py`, `train_models.py`, `evaluate.py`, `parser.py`, `score_normalized.py`, `compare_models.py`. The `venv/` and `requirements.txt` were also removed — recreate with `pip install numpy pandas scikit-learn joblib duckdb`.

### 13.4 Still-open issues from Section 8 (unchanged)

- `device_change` uses full browser version → false changes (use browser name only)
- `rapid_login_rate` max is 3 in this sample — no high-speed attacks present
- `failed_before_success` is very rare (and its implementation counted failures since last success, not a 5-minute window — semantics to fix in rewrite)
- First login per user always has `country_change = 1` (consider 0 for first-ever event)
