# Logs-Lab: Multi-Source Login Anomaly Detection Experiment

## What Is This Experiment?

We took login data from 6 different systems and asked one question:

**Can a computer learn to spot failed logins on its own — without being told what attacks look like?**

This is a building block for real security. If you can reliably detect failed logins, you can detect brute-force attacks, credential stuffing, and account takeover attempts.

---

## The Data

We parsed 6 different login log files into one unified dataset:

| Source | What It Is | Events | Success Rate |
|---|---|---|---|
| AWS | Cloud console logins | 100,000 | 90.3% |
| Entra | Microsoft identity logins | 100,000 | 90.6% |
| Windows | Domain/PC logins | 100,000 | 89.9% |
| Web | Web application logins | 100,000 | 89.6% |
| MySQL | Database connections | 99,999 | 90.6% |
| SSH | Server logins | 100,000 | 84.0% |
| **Total** | | **599,999** | **89.2%** |

**Key observation:** About 10% of logins failed across all sources (SSH had the highest failure rate at 16%). This is realistic — real systems typically see 1-15% failure rates.

> **Note (parsing fix):** Earlier versions of this experiment reported SSH as 1,866 events / 0% success. That was a parser bug — the SSH log actually contains 100,000 auth lines (84,007 accepted, 15,993 failed). A regex that required a space after `user` only matched the `for invalid user X` lines and silently dropped the other 98%. This was fixed in `parse_logs.py` and the dataset regenerated.

---

## What We Asked the Computer to Do

The computer needs to learn the difference between:

- **Normal successful login** — "this is fine, let them in"
- **Normal failed login** — "user probably typo'd their password"
- **Suspicious failed login** — "someone might be trying to break in"

We don't have attack labels — just success/failure. So we're training the model to detect **failure patterns**, not specific attacks.

---

## The 3 Models We Used

### 1. Hist Gradient Boosting (The Winner)

**How it works:** Imagine 200 detectives sitting in a room. Each detective looks at a login and votes "suspicious" or "normal." But here's the twist — each detective only looks at what the previous detectives MISSED. So they build on each other.

**Why it won:** Real attacks aren't just one weird thing. They're multiple weird things together: new country + nighttime + new device + rapid logins. This model catches those combinations.

**Think of it like:** A team of specialists where each one catches what the others miss.

---

### 2. Logistic Regression

**How it works:** Like a teacher with a simple checklist. It looks at each feature one at a time and assigns points:

- "Is it nighttime?" → +1 suspicious point
- "New country?" → +2 suspicious points
- "New device?" → +1 suspicious point

Then it adds up the points. If the total is high enough → "this looks weird."

**Why it lost:** It can only see one thing at a time. It doesn't notice that "nighttime AND new country AND new device" is way worse than any of those alone.

**Think of it like:** A single person checking items off a list one by one.

---

### 3. Isolation Forest

**How it works:** This one is different. It never sees what failures look like. It only studies successful logins and memorizes what "normal" looks like. When a weird login comes in, it stands out — like someone wearing a swimsuit to a business meeting.

**Why it lost:** It doesn't know what attacks look like. It only knows what success looks like. So it can only catch failures that look very different from normal, not subtle ones.

**Think of it like:** A bouncer who only knows what "regular customers" look like. Anything unusual gets flagged, but subtle attempts slip through.

---

## The Results

### Overall Scores

Scores are measured on a **held-out test set** (per-user chronological split), with the decision threshold
tuned on a separate validation slice so the numbers aren't optimistic.

| Model | F1 Score | Precision | Recall | ROC-AUC |
|---|---|---|---|---|
| **Hist Gradient Boosting** | **0.155** | 0.224 | 0.118 | 0.693 |
| Logistic Regression | 0.109 | 0.148 | 0.087 | 0.663 |
| Isolation Forest | 0.086 | 0.149 | 0.060 | 0.532 |

All models were tuned to keep false alarms under 5% (the FPR budget).

> **Note:** These are lower than the experiment's earlier numbers (F1 0.199, ROC-AUC 0.711). That is a
> *good* change: the old figure was inflated by the SSH parsing bug (which made SSH look 100% failed and gave
> the model a free `source=ssh → suspicious` shortcut) *and* by tuning the threshold on the test set itself.
> Both were fixed, so the current numbers are the honest ones.

### What These Numbers Mean (In Plain English)

#### F1 Score (The Main Metric)
- **Range:** 0 = terrible, 1 = perfect
- **What it means:** Balance between catching failures and not flagging successes
- **Our best:** 0.155
- **Translation:** The model catches about 1 out of every 6-7 failed logins correctly

#### Precision (Quality of Flags)
- **Range:** 0-1
- **What it means:** When the model says "this looks suspicious," how often is it right?
- **Our best:** 0.224
- **Translation:** When the model flags something, it's right only 22.4% of the time. That means 77.6% of its flags are false alarms.

#### Recall (Coverage of Failures)
- **Range:** 0-1
- **What it means:** Of all actual failures, how many did the model catch?
- **Our best:** 0.118
- **Translation:** The model only catches 12% of actual failures. It misses 88% of them.

#### ROC-AUC (Ranking Quality)
- **Range:** 0.5 = random, 1.0 = perfect
- **What it means:** Can the model rank logins from "most suspicious" to "least suspicious" correctly?
- **Our best:** 0.693
- **Translation:** The model is decent at putting suspicious logins higher on the list, but not perfect.

---

## Why the Scores Are Low

### 1. Class Imbalance
Only 10% of logins are failures. The model has to find 10 bad apples among 90 good ones. This is like finding a needle in a haystack.

### 2. No Attack Labels
We're detecting "failure," not "attack." Many failures are just typos, not attacks. The model has to figure out which failures are suspicious on its own.

### 3. Limited Features
We have 30 features (time, country, device, etc.). Real security systems use 100+ features including behavioral biometrics, network patterns, device fingerprinting, etc.

### 4. One Month of Data
Real systems train on years of data to learn seasonal patterns, user habits, and long-term trends. We only had one month.

---

## Compared to the Main Project

| Metric | Main Project | Logs-Lab | Why Different |
|---|---|---|---|---|
| **Best F1** | 0.287 | 0.155 | Main had attack labels, logs-lab doesn't |
| **Best ROC-AUC** | 0.752 | 0.693 | Similar — both learn real patterns |
| **Isolation Forest F1** | 0.006 | 0.086 | Main's IF was useless (label problem), logs-lab's IF works |
| **Data Size** | 31.3M events | 600K events | Main had ~52x more data |
| **Label Quality** | Blocklist (cheat sheet) | Pure failure detection | Logs-lab is harder but more honest |
| **Sources** | 1 (RBA SSO) | 6 (AWS, Entra, etc.) | Logs-lab is more realistic |

### The Key Difference

The main project had a **cheat sheet** — a list of known bad IP addresses. That's why it scored higher (0.287 vs 0.155). It wasn't really learning behavior; it was just matching IPs — a blocklist-only model already scores 0.747 F1 on that data.

Logs-lab has **no cheat sheet**. It has to figure out what "weird" looks like from scratch. That's harder, but more honest.

---

## What This Means for Real Security

### The Good News
- The models are learning something real — 0.155 F1 vs 0.02 random means there's signal in the data
- The same model hierarchy works across datasets (Gradient Boosting > Logistic Regression > Isolation Forest)
- The approach is scalable to more sources and more data

### The Bad News
- Not production-ready yet — 84% of failures are missed, and 73.5% of flags are false alarms
- Needs more data — one month isn't enough; real systems need 6-12 months minimum
- Needs attack labels — detecting "failure" is different from detecting "attack"
- Needs more features — real security uses device fingerprinting, behavioral biometrics, network analysis, etc.

### What Would Make It Better
1. **More data** — Train on 6-12 months instead of 1
2. **Better labels** — Have humans label which failures are actual attacks
3. **More features** — Add device fingerprinting, behavioral biometrics, network patterns
4. **Ensemble approach** — Combine multiple models (which is what Gradient Boosting already does internally)

---

## Bottom Line

This experiment proves the concept: **machine learning can detect login anomalies**. But it's a prototype, not a product.

The 0.155 F1 score shows there's real signal in the data, but we need better labels, more data, and more features to make it useful for real security.

The main project's higher score (0.287) was partly because it had a cheat sheet (IP blacklist). This logs-lab experiment is the more honest test: can ML detect suspicious behavior without being told what attacks look like?

**The answer: sort of, but not well enough yet.**

---

## Technical Details

### Training Setup
- **Split:** 55% train / 15% validation / 30% test (chronological per user)
- **Threshold tuning:** on the validation slice, so test-set scores aren't optimistic
- **Features:** 30 total (6 numeric, 19 boolean, 5 categorical)
- **FPR Budget:** 5% (false positive rate capped at 5%)

### Features Used
**Numeric:** hour, day_of_week, rapid_login_rate_10m, login_frequency_today, prior_failure_rate, minutes_since_prev

**Boolean:** is_night, is_weekend, country_missing, device_missing, os_missing, browser_missing, ip_missing, country_change, device_change, os_change, browser_change, source_change, failed_recently_30m, ip_seen_before, country_seen_before, device_seen_before, os_seen_before, browser_seen_before, source_seen_before

**Categorical:** source, country, device, os, browser

### Artifacts
- `events.parquet` — Raw parsed events (599,999 rows)
- `featured_events.parquet` — Events with computed features
- `reports/model_comparison.csv` — Model performance comparison
- `reports/evaluation.json` — Full evaluation report
- `models/best_model.joblib` — Best model (Hist Gradient Boosting)
- `ui/` — Standalone explainable web UI (`make logs-lab-ui-bg` → http://127.0.0.1:5001)

### Reproduce
```bash
make logs-lab-prepare   # parse (with per-source verification) -> features -> train
make logs-lab-ui-bg     # launch the explainable UI on http://127.0.0.1:5001
```

---

*Experiment conducted August 2026 as part of the MAJOR-PAIN-ATE- project.*
