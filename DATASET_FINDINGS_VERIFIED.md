# Dataset Findings — Verified on the Real Data (Read This First)

**Team:** Hemanth | Urvashi | Veenashree | Vishwanath
**Guide:** Dr. Anitha A C
**Last verified:** Aug 1, 2026

This document is written for everyone, including teammates who haven't seen the code yet. If you only read one file, read this one.

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

## 4. The 4 discoveries that change everything

We found these by scanning the full dataset. The old docs never mentioned them.

### 4.1 The robot user (most important)

One single user has **14,025,899 events — 45% of the ENTIRE dataset**:

- Logs in 300,000–800,000 times EVERY HOUR, 24 hours a day, for a year
- From ~200 different countries
- **14 million failed logins, only 3 successes** (0.00002% success rate)

This is clearly a bot / service account (a machine hammering passwords), not a human.

**Why it matters:** If we sample randomly, half of everything we train on is this one robot's failed logins. The model would learn "one weird robot" instead of "how normal humans behave." It also holds **53% of all attack flags** (1.65M of 3.1M), so how we treat it changes what "attack" means in our training data.

**What we'll do:** keep the bot in the data but limited (cap how many of its rows we take), and run an A/B experiment: model trained with it vs without it — keep whichever is more honest.

### 4.2 Attacks are concentrated in a few users

- 41 users hold **1.66M of the 3.1M attack rows** (54%)
- 8,122 users have ≥10 attack rows (together ~14.2M events)
- Most "attack users" (742K of them) have just 1–2 attack rows

**Why it matters:** Attack patterns aren't spread evenly. If we sample rows randomly we'll mostly get the concentrated bots; if we sample users randomly we may miss attacks entirely. We need **tiered sampling** (see §6).

### 4.3 The gold signal: successful logins from bad IPs

- **804,491 attack rows are SUCCESSFUL logins** — someone logged in successfully from a known-bad IP. That is exactly the account-compromise pattern we want to detect
- **141 ATOs: 140 of 141 are successful logins**, and only 55% of them overlap with the attack-IP flag — meaning attack-IP alone misses half of real takeovers

**Why it matters:** These are the rows that make our model actually useful. Training must include all 138 ATO users and a healthy chunk of the 804K successful-attack rows.

### 4.4 The data is dirty (~25% of rows)

- Browser says Android but OS says iOS (or similar contradictions): **~7.6M rows** with browser/OS mismatches
- **4,549 distinct browser strings** like "Firefox 20.0.0.1618" — version numbers create fake "new devices" every time someone updates their browser
- Old docs blamed these inconsistencies on the *synthetic* data and removed it — but the **real dataset has them too**

**Why it matters:** our `device_change` feature (has this device been seen before?) will flag innocent browser updates as device changes. We must clean: strip version numbers from browser/OS strings and fix impossible combos.

---

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
3. **Full-dataset baselines** — per-user "countries seen / devices seen" computed from ALL 33M rows via DuckDB (cheap, ~5s scans), so `country_change` / `device_change` are accurate even in a 1M-row sample
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
| **Everyone** | — | Read this file. Ask questions if anything is unclear |
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
