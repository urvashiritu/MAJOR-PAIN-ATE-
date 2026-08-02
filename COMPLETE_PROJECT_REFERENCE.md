# AI-Based Identity Anomaly Detection System — Complete Project Reference

## Team
| Name | USN | Role |
|---|---|---|
| Hemanth Kumar KS | 1SK23CS020 | Data Pipeline & Feature Engineering |
| Urvashi Tanwar | 1SK23CS055 | ML Models & Evaluation |
| Veenashree S T | 1SK23CS057 | Dashboard & Visualization |
| Vishwanath Sanapur | 1SK23CS059 | Live Demo System & Server |

**Guide:** Dr. Anitha A C  
**College:** Government Sri Krishnarajendra Silver Jubilee Technological Institute  
**Department:** Computer Science and Engineering

---

## ⚠️ STATUS UPDATE (Aug 1, 2026) — Read This First

### Dataset strategy decision: RBA-only

The multi-source synthetic approach (7 AI-generated log formats + `parser.py` normalization) was prototyped, evaluated, and **removed** on Aug 1, 2026. What we learned from the experiment:

| Problem | Evidence |
|---|---|
| Synthetic data was internally inconsistent | Impossible combos (`Desktop + Safari + Android 15`), `user_agent` contradicts stated browser in 381/500 web_login rows |
| Only 1 of 7 sources had labels | web_login: 73 attack-IP + 8 ATO out of 500; the other 6 sources (SSH, VPN, AD, M365, AWS, DB) had **no ground truth** — detection quality unmeasurable there |
| Models could not learn from it | Both the RBA-trained and normalized-trained ensembles scored **AUC ≈ 0.45** (worse than random) on the synthetic labels |
| Scale | 3,500 events total vs 31M real RBA events |

**Conclusion:** the parser concept (SIEM-style normalization of heterogeneous auth logs into one schema) remains a valid *future demo enhancement*, but it is **not training data**. All synthetic files, `parser.py`, `score_normalized.py`, `compare_models.py`, and their outputs were deleted.

### What exists in the repo right now

| Item | Path | Purpose |
|---|---|---|
| Raw RBA dataset | `data/raw/rba-dataset.csv` | 8.5 GB, 31,269,264 events (unchanged original) |
| Cleaned dataset | `data/processed/rba_clean.parquet` | 654 MB, same row count, normalized browser/OS/device + inconsistency flags (built Aug 2 by `src/00_clean_dataset.py`, ~30 s) |
| Cleaning script | `src/00_clean_dataset.py` | Full-file DuckDB clean + `--verify` before/after check table; documented in `dataset_scan_report.md` |
| Docs | 4 `.md` files + `LICENSE` | This reference, findings briefing, **dataset scan report**, README |

The old 18K-row training file (`training_data.csv`), the test labels, and the two notebooks from the broken pipeline were **removed** — they documented the failed approach and are superseded by `DATASET_FINDINGS_VERIFIED.md`. (Still recoverable from git history if ever needed.)

The full-dataset quality audit (Aug 2, 2026) is in `dataset_scan_report.md` — all 31,269,264 rows scanned; 16 columns verified correct; 12 issue classes documented (inconsistencies + synthesis artifacts), fixed or flagged by `src/00_clean_dataset.py`.

The previous `anomaly_detector.py` / `train_models.py` / `evaluate.py` were removed (poor structure, unmaintainable, semantics drifting from this doc); the rewrite starts with `src/00_clean_dataset.py`. The `venv/` was recreated — packages needed: `numpy pandas scikit-learn joblib duckdb`.

### Known issues to fix (learned since this doc was written)

1. **Attack-ratio collapse**: the 50K stratified sample (10% attack) became 18,191 rows with **248 attacks (1.36%)**. Cause: row-level sampling + the "users with ≥3 events" filter — most sampled attack rows belonged to users with <3 sampled events and were deleted. Fix: **user-based sampling** (keep all events of sampled users; filter first, then balance).
2. **Metrics in this document are NOT measured**: the 94.2% accuracy / 91.7% precision / 88.3% recall claims are not reproducible by any code that existed. The actual evaluation output was: at thr=30 → precision 0.0087, recall 0.0200, F1 0.0121; best F1 0.0185 at thr=35. Must be re-measured honestly after retraining.
3. **`failed_before_success` semantics**: this doc says "failed attempts in the last 5 minutes" (§3); the implementation counted *consecutive failures since last success* with no time window. The intended 5-minute window must be implemented in the rewrite.
4. **`device_change` includes exact browser version** (`Firefox 20.0.0.1618` vs `.1619` = false change). Strip version numbers.
5. **First login per user → `country_change = 1`** (no baseline exists). Consider `0` for a user's first-ever event.
6. **`contamination=0.05` was hardcoded** in all 4 models regardless of the actual attack ratio.

### Roadmap (next phases)

- **Phase 2 — Rebuild the training dataset**: user-based stratified sampling via DuckDB (~1M rows target, 5-10% attack ratio, all 141 ATOs included); full-31.3M per-user baselines (country/device history, normal frequency) via DuckDB to make contextual features accurate; vectorized/chunked feature engineering.
- **Phase 3 — Retrain + honest evaluation**: IF + Elliptic Envelope on the full sample; One-Class SVM + LOF on a 200-500K subset (sklearn scaling limit); `contamination` matched to the real attack ratio; reproducible metrics, threshold sweep, charts.
- **Phase 4 — Docs**: rewrite reports with real numbers; re-verify every claim in this document.

### Stale sections in this document

- **§15 File Structure, §16 Work Distribution, §23 Getting Started Commands** describe `src/01_load_and_sample.py` … `07_dashboard.py` — these files do **not** exist yet. Treat them as the *target structure* for the rewrite, not current reality.
- **§21 Q5 and the dashboard wireframe** quote the unverified 94.2%/91.7%/88.3% metrics — treat as aspirational until Phase 3 delivers measured numbers.

---

## Table of Contents

1. [What Are We Building?](#1-what-are-we-building)
2. [Dataset: RBA](#2-dataset-rba)
3. [The 8 Behavioral Features](#3-the-8-behavioral-features)
4. [The 4 ML Models](#4-the-4-ml-models)
5. [Detection Layers — Defense in Depth](#5-detection-layers--defense-in-depth)
6. [Two Approaches We Discussed: Path A vs Path B](#6-two-approaches-we-discussed-path-a-vs-path-b)
7. [What We Track — RBA Dataset vs Live Demo](#7-what-we-track--rba-dataset-vs-live-demo)
8. [Full Telemetry — Per-Event Analysis](#8-full-telemetry--per-event-analysis)
9. [Architecture — Complete Data Flow](#9-architecture--complete-data-flow)
10. [Edge Cases and How We Handle Them](#10-edge-cases-and-how-we-handle-them)
11. [What We Cannot Detect — Honest Limitations](#11-what-we-cannot-detect--honest-limitations)
12. [False Positive Handling Strategy](#12-false-positive-handling-strategy)
13. [Real Companies and How They Compare](#13-real-companies-and-how-they-compare)
14. [Tech Stack — With Frontend Discussion](#14-tech-stack--with-frontend-discussion)
15. [File Structure](#15-file-structure)
16. [Team Work Distribution](#16-team-work-distribution)
17. [Timeline — 4 Weeks](#17-timeline--4-weeks)
18. [Live Demo Script — 5 Minute Viva](#18-live-demo-script--5-minute-viva)
19. [Dashboard Wireframe](#19-dashboard-wireframe)
20. [GPU Utilization (RTX 3050 6GB)](#20-gpu-utilization-rtx-3050-6gb)
21. [Viva Preparation — Likely Questions and Answers](#21-viva-preparation--likely-questions-and-answers)
22. [Risks and Mitigations](#22-risks-and-mitigations)
23. [Getting Started Commands](#23-getting-started-commands)

---

## 1. What Are We Building?

A system that watches login events and flags suspicious behavior. When someone logs into a system, we extract 8 features (time, location, device, login speed, failed attempts, frequency) and run them through 4 ML models. If the models agree it's suspicious, the dashboard shows a real-time alert with a risk score 0-100 and explanation of why it was flagged.

### How the 3 detection layers work together

```
Layer 1: ML Models (trained on 8 real RBA features)
  → Detects remote attacks: credential theft, brute force, account takeover

Layer 2: Device Fingerprinting (SHA256 hash of MAC + hostname + CPU + screen)
  → Detects: someone logs into your account from a different laptop
  → Shows on dashboard: known device ✓ or unknown device ✗

Layer 3: Behavioral Biometrics (typing speed, mouse speed, keystroke patterns)
  → Detects: someone using YOUR laptop but behaving differently
  → Shows on dashboard: profile match ✓ or deviation ⚠
```

### The approach: Path A (selected)

- ML models train ONLY on 8 real features from the RBA dataset (real data, real labels, real learning)
- Device fingerprinting and behavioral biometrics are NOT fed into ML training
- They are computed during live demo and shown on dashboard as transparent indicators
- This keeps ML honest (trained on real data) while still showing behavioral detection

### What the examiner sees during viva

A live dashboard on Laptop 1 showing login events arriving in real-time from Laptop 2. Normal events show green. When the person on Laptop 2 clicks "Attack Mode", the country changes, device changes, time changes, and a red alert pops up with risk score ~92/100 with explanations for each feature that triggered.

---

## 2. Dataset: RBA

### Source

- **Name:** Risk-Based Authentication dataset (RBA)
- **Created by:** Wiefling et al., ACM TOPS 2022
- **From:** Telenor Norway SSO (synthesized from real login patterns)
- **Size:** 8.5 GB CSV (compressed to 1.1 GB zip)
- **Rows:** 31,269,264 login events (31.3M)
- **Download:** https://zenodo.org/records/6782156
- **Status:** Already downloaded. DuckDB cache built (533 MB)

### Why RBA and not LANL or CERT?

| Requirement | RBA | LANL | CERT logon.csv |
|---|---|---|---|
| user_id | ✓ | ✓ | ✓ |
| timestamp | ✓ | ✓ (epoch) | ✓ |
| country | **✓** | ✗ | ✗ |
| device type | **✓** | ✗ (computer name only) | ✗ (pc name only) |
| browser | **✓** | ✗ | ✗ |
| OS | **✓** | ✗ | ✗ |
| success/failure | **✓** | ✓ | ✗ (LogOn/LogOff only) |
| All 8 features computable | **✓** | ✗ (missing 3+) | ✗ (missing 4+) |
| Size manageable | 8.5 GB | 89 GB | 16 GB |
| Already downloaded | **✓** | Partial sample | Wrong file |

**CERT r4.2** (more academic prestige, 275+ citations) lacks country, device, browser, OS, and success/failure columns in its auth logs. We can't compute 4 of our 8 features from it.

**LANL** (real enterprise data) is 89 GB and also lacks country and device information.

**Verdict:** RBA is the only dataset with all 8 computable features. Already downloaded. Zero setup time.

### What the dataset contains

- **31.3 million login events** from a real SSO system
- **141 confirmed account takeovers** (gold standard — rare. In real enterprises, attacks are <0.1% of logins). ⚠️ Verified Aug 1, 2026: earlier drafts said 87 — wrong. All numbers verified in `DATASET_FINDINGS_VERIFIED.md`.
- **3.1M Attack IP logins** (logins from known attacker IP addresses — this becomes our primary training label because it has more samples; 804K of them are successful logins)
- **⚠️ One bot user holds 45% of all events and 53% of all attack labels** — see `DATASET_FINDINGS_VERIFIED.md` §4.1 before planning any sampling

### The 141 confirmed attacks — is that enough?

141 attacks is realistic for a real enterprise (attacks are rare). But for ML training, we also use the "Is Attack IP" column as the primary label, which gives us ~3.1M attack rows (804K of them successful logins). The 141 ATOs are used for evaluation (does our model catch the most dangerous attacks?).

### What we do NOT do to the raw CSV

We do NOT modify the 8.5GB CSV directly. Instead:
```
Raw RBA CSV (8.5GB, unchanged)
    ↓ DuckDB query
Sampled 500K rows
    ↓ Feature engineering (compute 8 features per row, using user history)
Training file (500K rows, 8 feature columns + 1 label column)
```

This is safer. One mistake in feature engineering corrupts the training file, not the original dataset.

### Is 31.3M useful even though we sample for training?

Yes, for 4 reasons:

1. **Per-user baselines** — Users have 100s-1000s of logins each. A user with 500 logins means country_change is meaningful (we've seen 500 logins from India, so Russia is genuinely unusual).

2. **Real-world login distributions** — Normal login rates (~1-2 per user per day), geographic spread, device diversity all come from real patterns.

3. **Impossible travel detection** — 31.3M events across 1 year (Feb 2020 – Feb 2021; earlier drafts said 2 years — wrong) means we can measure "Login from India → Russia in 2 minutes" against real data and know it's impossible.

4. **Scalability proof** — DuckDB pipeline can query full 31.3M. Even though we sample for training, the pipeline design scales. This goes in the report.

---

## 3. The 8 Behavioral Features

### Simple features (from this single row alone)

| Feature | Computation | What it detects |
|---|---|---|
| **hour** | `row["Login Timestamp"].hour` (0-23) | Login at 3am instead of 2pm |
| **is_night** | `1 if hour < 6 or hour > 22 else 0` | Night-time login |
| **is_weekend** | `1 if Saturday or Sunday else 0` | Weekend login (suspicious for office users) |

### Contextual features (need user history to compute)

These require looking at the user's past behavior. We process rows in chronological order, grouped by user_id. Each user has a running history (last 10 logins, all countries seen, all devices seen, last 60 seconds, last 5 minutes).

| Feature | How computed | What it detects |
|---|---|---|
| **country_change** | Has this user ever logged in from this country before? If no → 1 | User from India suddenly logs in from Russia |
| **device_change** | Has this user ever used this exact device+browser+OS combo before? If no → 1 | iPhone user suddenly using Android/Firefox |
| **failed_before_success** | Look back 5 minutes. Were there failed attempts from this user before this success? If yes → 1 | Brute force: 12 failed attempts then 1 success |
| **rapid_login_rate** | Count logins from this user in the last 60 seconds | Automated script doing 100 logins per minute |
| **login_frequency_today** | Count total logins from this user today so far | 50 logins today vs normal 5/day |

### Example — same user, 3 events processed chronologically

| Timestamp | Country | Device | Success | hour | night | country_chg | device_chg | failed_before | rapid_rate | is_attack |
|---|---|---|---|---|---|---|---|---|---|---|
| 2020-02-03 12:43 | India | iPhone | ✓ | 12 | 0 | 0 | 0 | 0 | 1 | 0 |
| 2020-02-03 02:15 | Russia | Android | ✓ | 2 | 1 | 1 | 1 | 12 | 45 | 1 |
| 2020-02-03 02:16 | Russia | Android | ✓ | 2 | 1 | 0 | 0 | 0 | 46 | 0 |

**Row 1:** Normal — same country, same device, lunch time → no flags
**Row 2:** Attack — first Russia, first Android, 12 failed then success, 45 rapid logins → attack
**Row 3:** Same country+device now seen before (country_change=0, device_change=0), no failures → no longer flagged

### Why 8 features and not more/less?

8 features cover 4 dimensions of identity detection:
- **Who** (user_id)
- **What** (device_change — device, browser, OS combo)
- **Where** (country_change)
- **When** (hour, is_night, is_weekend)
- **How** (failed_before_success, rapid_login_rate, login_frequency_today)

RBA dataset has exactly these columns available. More features would require data we don't have (file access logs, network traffic, process execution). Fewer features would miss important attack patterns — using only country would miss same-country attacks.

### Are these rules or real ML?

The features themselves are computed by rules (e.g., country_change = compare to history). But the ML models learn NON-LINEAR patterns across ALL 8 features simultaneously. For example:

- "country_change=1 AND night=1 AND device_change=1" → 92/100 (high risk)
- "country_change=1 AND daytime=0 AND same_device=0" → 35/100 (probably travel)

Rules can't capture these nuanced interactions. ML does.

---

## 4. The 4 ML Models

### Model descriptions

| Model | Type | Training time (500K rows) | What it does |
|---|---|---|---|
| **Isolation Forest** | Tree-based isolation | ~30 seconds | Randomly splits data into trees. Anomalies are isolated in fewer splits (they're "different") |
| **One-Class SVM** | Boundary-based | ~5 minutes (slow) | Draws a boundary around normal data. Everything outside is anomaly |
| **Local Outlier Factor** | Density-based | No training (lazy) | Compares density around a point vs its neighbors. Sparse regions = outliers |
| **Elliptic Envelope** | Statistical | ~10 seconds | Assumes data follows Gaussian distribution. Points far from mean are anomalies |

### Ensemble scoring

```python
# Each model outputs -1 (anomaly) or 1 (normal)
# Convert to anomaly score 0-100 and average
risk_score = avg(if.score, svm.score, lof.score, ee.score) * 100

if risk_score > 75  → HIGH alert   (red)
if risk_score 50-75 → MEDIUM      (yellow)
if risk_score < 50  → LOW         (green — normal)
```

### Why 4 models instead of 1?

- **Isolation Forest** — catches globally rare events (completely new pattern)
- **One-Class SVM** — catches novel events near boundaries (almost normal but not quite)
- **LOF** — catches local anomalies (unusual for a specific user, even if common globally)
- **Elliptic Envelope** — catches statistical outliers (extreme values in any feature)

Ensemble averaging reduces false positives. If 3 models say normal and 1 says anomaly → score ~25/100 (safe). If all 4 agree → confident flag.

### Why not deep learning?

- Deep learning needs thousands of diverse attack samples. We have 141 ATOs and 3.1M Attack IP rows, but most attack rows are the same bot patterns repeated (53% from one user) — not enough diverse examples.
- scikit-learn models are INTERPRETABLE — we can show exactly why a row was flagged (which features, which model). Deep learning is a black box.
- For a BE project, explainability matters more than marginal accuracy gain.

### One-Class SVM limitation

SVM doesn't scale to 500K rows (takes hours). We train it on a 50K subset. If it performs poorly, we drop it and ensemble the other 3. The project still works fine with 3 models.

---

## 5. Detection Layers — Defense in Depth

### Layer 1: ML Models (trained on 8 real RBA features)

**What it detects:**
- Credential theft from a different country
- Brute force (failed→success, rapid rate)
- Account takeover (device change + country change)
- Scripted attacks (rapid rate, night time, unusual frequency)

**Is this real ML?** Yes. Models train on 500K real RBA events with real attack labels (Is Attack IP column). They learn patterns from genuine login behavior, not from our hardcoded rules.

### Layer 2: Device Fingerprinting

**What is a hash (SHA256)?** A hash is a one-way function that takes input data and produces a fixed-length string (like "a3f2b8c1e4d7..."). You cannot reverse it back to the original data.

**How device fingerprinting works:**

```
When igris's laptop connects, the client script collects:
  MAC address:      "00:1A:2B:3C:4D:5E"
  Hostname:         "igris-laptop"
  CPU:              "Intel i5-12400"
  Screen:           "1920x1080"
  GPU:              "RTX 3050"

These are concatenated and hashed with SHA256:
  hash("00:1A:2B:3C:4D:5E" + "igris-laptop" + "Intel i5-12400" + "1920x1080")
  → "a3f2b8c1e4d7..."
```

Only the hash is stored — raw MAC and hostname are never saved. Privacy-preserving.

**When another laptop logs in as igris:**
```
hash("AB:CD:EF:12:34:56" + "hacker-pc" + "AMD Ryzen 5" + ...)
→ "ff9977124b3a..."

"ff9977124b3a" ≠ "a3f2b8c1e4d7..." → UNKNOWN DEVICE — FLAG
```

**What it catches:** Someone logs into igris's account from a laptop that isn't igris's.

**What it misses:** Someone steals igris's laptop. Same MAC, same hostname, same hash → shows as "known device ✓".

### Layer 3: Behavioral Biometrics (Dashboard Overlay)

**Research inspiration:** BioCatch, Securiti — companies that track user behavior to detect fraud.

**What we track per session:**

| Metric | How measured | Normal (igris) | Deviation = suspicious |
|---|---|---|---|
| **Typing speed (wpm)** | Count keys per second | 62 ± 8 wpm | 120 wpm (too fast) or 30 wpm (hunting/pecking) |
| **Mouse speed (px/s)** | Distance moved per second | 320 ± 50 px/s | 800+ px/s (fast, jerky) |
| **Keystroke hold time (ms)** | How long each key is pressed | 80 ± 15 ms | 40 ms (tap-typer) or 150+ ms (holds keys) |
| **Keystroke latency (ms)** | Gap between releasing and pressing next key | 120 ± 30 ms | 200+ ms (hesitant) or 5 ms (bot-like) |

**Important:** These are NOT fed into ML. They are computed in real-time and displayed on the dashboard as transparent rule-based indicators alongside the ML score. The ML remains honest (trained on real RBA data). The behavioral layer adds extra detection without polluting ML.

### Complete attack detection matrix

| Attack Scenario | Layer 1 (ML) | Layer 2 (Device) | Layer 3 (Behavior) | Overall |
|---|---|---|---|---|
| Stolen password from Russia, Android, 3am | ✅ 92/100 | ✅ Unknown device | ✅ Different typing | **CAUGHT** |
| Someone logs in as igris from their device, normal time/location | ❌ 8/100 | ✅ Unknown device | ✅ Different typing | **CAUGHT (Layer 2+3)** |
| igris's laptop stolen, attacker types differently, normal time | ❌ 8/100 | ❌ Same device | ✅ Different typing | **CAUGHT (Layer 3)** |
| igris's laptop stolen, attacker types EXACTLY like igris, behaves same | ❌ 8/100 | ❌ Same device | ❌ Perfect mimic | **MISSED** |
| Brute force on igris's account from same laptop | ✅ 85/100 | ❌ Same device | ❌ Bot doesn't type | **CAUGHT (Layer 1)** |
| igris travels to Thailand, uses hotel PC | ⚠ false positive | ✅ Unknown | ⚠ Different typing | **System learns after 3 events** |

---

## 6. Two Approaches We Discussed: Path A vs Path B

### Path A (SELECTED — what we build)

**ML models train ONLY on the 8 real RBA features.** Real data from a published academic dataset. Real attack labels. Real learning — the models learn patterns from genuine login behavior, not from our rules.

**Device fingerprinting and behavioral biometrics are NOT trained into the ML.** They are computed during the live demo and shown on the dashboard as transparent indicators alongside the ML score. This is a rule-based overlay that adds extra detection layers without polluting the ML.

**Why Path A over Path B:**
- Honest ML — no fake training data
- Any examiner who asks "how do you know the model learned real patterns?" gets an answer backed by real data
- Strong enough for a BE project (real ML + real device fingerprinting + real behavioral tracking)
- The behavioral overlay layer still demonstrates detection of sophisticated attacks (same laptop, different typist)

### Path B (DISCUSSED, REJECTED FOR NOW)

Generate a fully synthetic dataset with realistic typing speeds, mouse movements, scroll patterns, and session durations. Add these as extra columns to the training data so the ML model learns from them too.

**Why we rejected it (for now):**
- Creating realistic behavioral data requires research into distributions (typing speed varies by age, language, emotion, time of day). If the data isn't realistic, the model learns wrong patterns — e.g., "typing_speed > 100 = attack" when in reality some people just type fast.
- A beginner team spending 2+ weeks on synthetic behavioral data risks having a half-baked project
- If after building Path A there is extra time (Week 4 buffer), Path B can be revisited as an enhancement

**When we might revisit Path B:** If the core project (Path A) is finished by Week 3, we can build a separate synthetic dataset generator, validate distributions against published research (BioCatch papers, keystroke dynamics studies), retrain models on expanded features, and compare accuracy. This goes in the report as "future enhancement."

### Summary comparison

| Aspect | Path A | Path B |
|---|---|---|
| ML training data | Real RBA features only | RBA + synthetic behavioral features |
| Is the ML real? | Yes | Partially — some features are generated algorithmically |
| Behavioral detection | Rule-based overlay on dashboard | Trained into ML models |
| Risk of fake learning | None | High — synthetic data must be realistic |
| Examiner risk | Low — can defend every choice | High — "how do you know this isn't your own rule disguised as ML?" |
| Time to working project | 2-3 weeks | 4-5 weeks |
| **Our decision** | **BUILD THIS** | Future scope only |

---

## 7. What We Track — RBA Dataset vs Live Demo

### From RBA dataset (for training)

| RBA Column | Used For |
|---|---|
| Login Timestamp | Compute hour, is_night, is_weekend, rapid_login_rate, login_frequency_today |
| User ID | Group events per user, build per-user history |
| Country | Compute country_change |
| Device Type | Part of device_change (mobile/desktop/tablet) |
| Browser Name + Version | Part of device_change |
| OS Name + Version | Part of device_change |
| Login Successful | Compute failed_before_success |
| Is Attack IP | Training label (1 = attack, 0 = normal) |
| Is Account Takeover | Secondary evaluation label (141 ATOs) |
| User Agent String | Parsed to extract device_type + browser + OS |

### From second laptop (live demo)

| Data Sent | How Captured | Used For |
|---|---|---|
| user_id | Config value | Identify which user |
| timestamp | `datetime.now()` | Compute hour, is_night, is_weekend |
| country | Set by client (changes in attack mode) | country_change |
| device_type | From user agent or config | device_change |
| browser | From user agent | device_change |
| os | `platform.system()` | device_change |
| login_successful | True for normal, False→True for attack | failed_before_success |
| MAC address | `uuid.getnode()` | Device fingerprint hash |
| Hostname | `socket.gethostname()` | Device fingerprint hash |
| CPU info | `platform.processor()` | Device fingerprint hash |
| Screen resolution | Auto-detected or config | Device fingerprint hash |
| Typing speed (wpm) | Captured from keyboard events | Behavioral overlay |
| Mouse speed (px/s) | Captured from mouse events | Behavioral overlay |
| Mode | "normal" or "attack" | Determines which values to send |

### Side-by-side comparison

| Feature | Training (RBA) | Live Demo (2nd Laptop) |
|---|---|---|
| hour | ✓ (from timestamp in CSV) | ✓ (from client timestamp) |
| is_night | ✓ (computed from hour) | ✓ (computed from hour) |
| is_weekend | ✓ (computed from date) | ✓ (computed from date) |
| country_change | ✓ (compare to user's RBA history) | ✓ (compare to user's live + RBA history) |
| device_change | ✓ (compare to user's RBA history) | ✓ (compare to user's live + RBA history) |
| failed_before_success | ✓ (from RBA success column + 5min check) | ✓ (client sends True/False, server checks history) |
| rapid_login_rate | ✓ (from RBA timestamp + 60sec window) | ✓ (from client timestamps + 60sec window) |
| login_frequency_today | ✓ (from RBA date + count) | ✓ (from client timestamps + today count) |
| Device fingerprint | ✗ (RBA has no MAC/hostname) | ✓ (MAC + hostname + CPU → SHA256 hash) |
| Behavioral biometrics | ✗ (RBA has no typing/mouse data) | ✓ (typing speed, mouse speed from client) |

---

## 8. Full Telemetry — Per-Event Analysis

Full telemetry means analyzing every available metric for every event, not just checking one thing.

### What we analyze per event

| Metric | Computed when | How |
|---|---|---|
| 8 ML features | Every login event | Server computes from client data + per-user history |
| Device hash match | Every login event | Compare SHA256(client_hash) vs stored hash for this user |
| Typing speed deviation | Every login event | Compare client's wpm vs stored profile (rolling avg last 20 events) |
| Mouse speed deviation | Every login event | Compare client's px/s vs stored profile |
| Session count today | Every login event | How many times has this user logged in today? |

### What the dashboard shows per event (every single event gets ALL of this)

```
Event #152 | igris | India | Chrome/Win11 | 14:30
  ML Score:   country_change=0  device_change=0  night=0
              failed_before=0   rapid_rate=1     freq=3
              → IF: 0.92(S)  SVM: 0.88(S)  LOF: 0.95(S)  EE: 0.91(S)
              → Ensemble: 0.09 → Score: 9/100  ✓
  Device:     Hash a3f2b8c1 = "igris-laptop" (known since Jul 26)  ✓
  Typing:     62 wpm (profile: 62±8) — within normal range  ✓
  Mouse:      320 px/s (profile: 300±50) — within normal range  ✓
  Session:    Login #5 today (normal: 3-8)  ✓
  ─────────────────────────────────────────────────────────────
  OVERALL:    SAFE (confidence: 97%)
```

### What we are NOT capturing

- Full keystroke log (what keys are pressed — privacy violation)
- Webcam or microphone
- File contents
- Network traffic beyond login events
- Screen recording

These would require invasive permissions and aren't appropriate for a college project.

---

## 9. Architecture — Complete Data Flow

### Training Phase (done once, before viva)

```
RBA Dataset (31.3M rows, 8.5GB CSV via DuckDB)
    │
    ▼
DuckDB query → sample 500K rows (stratified:
    includes all 141 ATOs + all Attack IP rows + random normal rows)
    │
    ▼
Feature Engineering (02_feature_engineering.py):
    Group by user_id, sort chronologically
    For each row in order:
        1. Compute simple features: hour, is_night, is_weekend
        2. Look up user's history (last 10 logins, all seen countries/devices)
        3. Compute contextual features:
           country_change = has this country been seen for this user?
           device_change = has this device+browser+OS been seen?
           failed_before_success = were there fails in last 5 min?
           rapid_login_rate = count logins in last 60 seconds
           login_frequency_today = count logins today
        4. Add this row to user's history
        5. Label: Is Attack IP column (1=attack, 0=normal)
    │
    ▼
Training file (500K rows, 8 feature columns + 1 label column)
    │
    ▼
Train/Test Split (80% / 20%)
    │
    ▼
Train 4 models (03_train_models.py):
    - IsolationForest(n_estimators=100, random_state=42)
    - OneClassSVM(nu=0.1) — on 50K subset only (SVM is slow)
    - LocalOutlierFactor(novelty=True, n_neighbors=20)
    - EllipticEnvelope(contamination=0.01)
    │
    ▼
Evaluate (04_evaluate.py):
    accuracy, precision, recall, F1, confusion matrix per model
    events-per-second benchmark
    generate comparison charts
    │
    ▼
Save models → models/isolation_forest.pkl, models/one_class_svm.pkl, etc.
```

### Live Demo Phase (during viva)

```
LAPTOP 2 (Client - 06_client.py):
    python client.py
    Interactive terminal with mode toggle ('n'=normal, 'a'=attack)
    Sends POST /login to Laptop 1 with:
        - user_id, timestamp, country, device, browser, os, success
        - MAC, hostname, CPU info, screen resolution
        - typing_speed, mouse_speed
        - mode flag (normal/attack)

        ↓ HTTP POST

LAPTOP 1 (Server - 05_server.py):
    FastAPI on port 8000
    Loads 4 .pkl model files on startup
    Maintains per-user history in memory
    On receiving event:
        1. Extract 8 features using client data + user history
        2. Score with all 4 models → ensemble → risk score 0-100
        3. Generate device hash from MAC+hostname+CPU+screen
        4. Compare device hash vs stored hash for this user
        5. Compare typing/mouse speed vs user behavioral profile
        6. Push result to WebSocket stream

        ↓ WebSocket stream

DASHBOARD (07_dashboard.py — Streamlit):
    Port 8501
    Subscribes to WebSocket for live events
    Displays:
        - Live event feed (latest 20, color coded by risk)
        - Alert cards with feature breakdown (when risk > 75)
        - Device fingerprint match/mismatch
        - Behavioral profile comparison
        - Charts: model scores, alerts over time
```

### The "real-time" vs "dataset" connection — clarified

| Phase | What happens | Where data comes from |
|---|---|---|
| **Training** | ML models learn what "normal" vs "attack" looks like | RBA dataset (31.3M historical events) |
| **Live demo** | Load trained .pkl model files, score new events as they arrive | Laptop 2 sends events via HTTP |

The training dataset and the live demo data are different. The connection is the .pkl model files. The models learn patterns from RBA, then apply those same patterns to new events from Laptop 2.

**Demonstrating real-time:** Each event is scored in <1ms. During the demo, human clicks make it look slow. But the benchmark (2847 events/sec) proves the system can handle production login volumes. If asked: *"We process each event in under 1 millisecond. The demo shows events at human speed, but the inference benchmark proves production readiness."*

### Feature computation on server during live demo

The server computes features differently than during training:

**During training (RBA):**
- country_change: compare to ALL 500K rows of this user's RBA history
- device_change: compare to ALL 500K rows of this user's RBA history

**During live demo:**
- country_change: compare to user's LIVE history (events seen during demo) + RBA history (if available)
- device_change: compare to user's LIVE history + RBA history (if available)

This means the system has both: what we learned from RBA + what we learned during the demo session.

---

## 10. Edge Cases and How We Handle Them

### Edge Case 1: igris travels to Thailand, uses hotel computer at 3am India time

**What the system sees:**
- country_change = 1 (Thailand ≠ India)
- device_change = 1 (hotel PC ≠ igris-laptop)
- hour = 3 (night in India)
- typing_speed = 45 wpm (different keyboard layout)
- **Risk score: ~85/100 → RED ALERT**

**The problem:** This is actually igris, not an attacker. False positive.

**How we handle it — 3 strategies:**

**Strategy 1: "Seen before" learning.** After the first event from Thailand, the system adds Thailand to igris's "known countries" and the hotel device to "known devices". The next event from Thailand:
```
Event 2: country_change = 0 (already seen), device_change = 0 (already seen)
  Only night fires → score drops to ~45/100
Event 3: Score ~25/100. System has learned this is new normal.
```

**Strategy 2: Rolling baseline adaptation.** Behavioral baselines (typing speed, mouse speed) use a rolling window of last 20 events. Over 5-10 events, the baseline shifts to accommodate the new typing speed on the hotel keyboard.

**Strategy 3: Human confirmation — "This was me" button.** Dashboard shows a button on alerts. When clicked, the system permanently adds Thailand + hotel device to "known" for igris.

**Dashboard behavior for this scenario:**
```
Event 1: igris  Thailand  hotel-PC  3am  Score: 85  🚨 (first time)
Event 2: igris  Thailand  hotel-PC  4am  Score: 45  ⚠ (country+device known)
Event 3: igris  Thailand  hotel-PC  5am  Score: 22  ✓ (adapted)
Event 4: igris  India     laptop    2pm  Score: 5   ✓ (back to normal)
```

### Edge Case 2: Someone steals igris's laptop + password + types perfectly like igris

**What the system sees:**
- country_change = 0 (same India)
- device_change = 0 (same laptop)
- hour = 14 (normal time)
- device_hash = "a3f2b8c1" (matches igris-laptop)
- typing_speed = 62 wpm (matches profile)
- mouse_speed = 320 px/s (matches profile)
- **Risk score: ~5/100 → GREEN. Everything passes.**

**The problem:** This is an attacker. We missed them completely.

**Can we detect this?**
- **Keystroke dynamics (hold time + latency):** Even at same wpm, igris has a unique typing RHYTHM (how long they hold 'p', gap between 'a' and 's'). This is unique like a fingerprint.
- **Micro-mouse patterns:** igris moves in smooth curves. Attacker might move in straight lines with sharp corners.
- **Access patterns:** After login, does the session access normal resources (email, docs) or sensitive resources (admin panel, payroll)?

**Can we implement keystroke dynamics in our project?**
- Yes, partially. We can capture hold time and latency using `pynput` on the client side.
- Where it fits: Layer 3 behavioral overlay. The dashboard shows "Keystroke rhythm: MATCH (95%) ✓" or "MISMATCH (62%) ⚠"
- NOT trained into ML — stays as transparent rule-based indicator.

**What if we don't implement it?** This is an acknowledged limitation. Even production systems from Google and Microsoft don't fully solve this — they add MFA, hardware security keys, and device certificates as additional controls.

### Edge Case 3: igris changes typing speed (injury, new keyboard, phone keyboard)

**What the system sees:** igris normally types 62 wpm. Today they're on a phone keyboard (30 wpm). Deviation flagged.

**How we handle it:** Rolling baseline adaptation. After ~5-10 events at the new speed, the baseline expands to include it. The dashboard shows a gradual transition:
```
Event 1: 62 → 45 ⚠ deviation (new keyboard)
Event 2: 45 → still flagged
Event 3: 42 → still flagged
Event 5: 40 → baseline starts shifting
Event 6: 38 → ✓ accepted as new normal
```

### Edge Case 4: VPN usage causes country_change to always fire

**What the system sees:** igris uses a VPN, appears from different countries every login.

**How we handle it:** The system tracks both network location AND device trust. If igris always uses igris-laptop (same device hash) but appears from different countries, the combined score is medium:
```
igris  [igris-laptop ✓]  VPN: Russia   2pm  Score: 45  ⚠
igris  [igris-laptop ✓]  VPN: Germany  3pm  Score: 42  ⚠
igris  [igris-laptop ✓]  VPN: US       4pm  Score: 40  ⚠
```

After seeing multiple countries from the same device, the system learns "igris uses VPN" and reduces country_change weight for this user. This happens automatically as historical data accumulates.

### Edge Case 5: First login ever — no baseline exists

**What the system sees:** Brand new user, first login. No history to compare against.

**What happens:**
| Feature | Value for first login | Why |
|---|---|---|
| country_change | 0 | No history — can't compute |
| device_change | 0 | No history — can't compute |
| rapid_login_rate | 1 | Only login so far |
| login_frequency_today | 1 | Only login so far |
| failed_before_success | 0 | No failures before |
| hour | actual hour | Simple feature |
| is_night | actual value | Simple feature |
| is_weekend | actual value | Simple feature |
| **Risk score** | **~5/100** | **Low — minimal context** |

**How we handle it:** The ML models still work because they've seen 500K OTHER users. General patterns still apply — if the first login is at 3am from a known attacker IP, the model can flag it based on patterns learned from other users. But per-user features (country_change, device_change) only activate after 2+ logins.

**This is documented as a "cold-start limitation."** Production systems handle this with IP reputation scoring, device reputation across the platform, and initial risk baselines. We can add simple versions of these if time permits.

### Edge Case 6: Someone steals igris's laptop AND password at 2pm, works at igris's desk

**What the system sees:**
- hour = 14 (normal)
- country = India (normal)
- device_hash = match (same laptop)
- typing_speed = 62 wpm (matches profile... but what if they copied?)
- **All 3 layers pass. Score: ~5/100.**

**The problem:** This is the hardest scenario. Perfect physical mimic.

**Honest answer:** No system detects this 100%. Even BioCatch, Google, and Microsoft have this limitation. The defense is layered: device certificates (hardware-level trust), MFA (authenticator app), biometrics (fingerprint/face on device). Our system targets the 95% of attacks that are REMOTE — credential theft, brute force, account takeover from unknown locations/devices. Physical device compromise with perfect behavior mimic is outside our detection scope, the same limitation shared by production UEBA systems.

---

## 11. What We Cannot Detect — Honest Limitations

### Permanent blind spots (fundamental to system design)

| Attack Scenario | Why We Miss It | How Real Companies Cover It |
|---|---|---|
| **Perfect mimic** — device + password stolen, behavior copied exactly | All 3 layers pass: same device hash, same 8 features, same behavior profile | MFA (authenticator app), biometric auth (fingerprint/face), device certificates (hardware-level trust) |
| **MFA bypass / fatigue attack** — attacker spams push until user accepts | Our system only sees login logs. If MFA passed, login looks completely normal | Number matching (Microsoft — type number from screen), location-based MFA, hardware security keys |
| **Session token theft** — attacker steals cookie without new login | We only analyze login events, not active session behavior | Continuous verification (Google BeyondCorp re-checks every request), short token expiry |
| **Insider threat during normal hours** — employee accessing files they shouldn't | RBA has no file access data. Login looks completely normal | EDR (CrowdStrike monitors processes and files), CASB (Microsoft Defender for Cloud Apps), DLP |

### Technical limitations (could be improved, out of scope)

| Limitation | Why | Future Scope |
|---|---|---|
| Not real-time streaming — events processed in batch (<1s each) | Project scope — building Kafka streaming infrastructure is a separate project | Add message queue (Kafka/RabbitMQ) + streaming engine |
| No post-login monitoring — only login events analyzed | RBA dataset only contains login data | Integrate file access logs, network logs, process logs |
| No automatic blocking — dashboard alerts only | BE project goal is detection, not prevention | Add policy engine: "score > 90 → revoke session, force re-auth" |
| Single dataset — all training from RBA | Other datasets lack required columns | Multi-dataset training (RBA + custom synthetic data) |
| No peer group analysis — comparing user to similar users | Would need role/department data RBA doesn't have | Group users by role, compare behavior against peers |

### The honest viva answer

> *"No system detects 100% of attacks. Enterprise security uses defense-in-depth: MFA, device certificates, endpoint detection, and behavioral analytics are complementary layers. Our system targets the gap that rule-based systems leave open — remote identity attacks that bypass traditional login thresholds. The remaining attack surface (physical device theft, MFA bypass, post-login insider threats) requires additional controls we document as future scope and reference through industry examples like Google BeyondCorp, CrowdStrike, and Microsoft Defender."*

---

## 12. False Positive Handling Strategy

### Summary of approach

| Strategy | How it works | When it applies |
|---|---|---|
| **"Seen before" memory** | Once a country/device is seen for a user, country_change/device_change no longer fire | Travel, new devices |
| **Rolling baseline adaptation** | Behavioral metrics use rolling window of last 20 events | New typing speed, new mouse pattern |
| **Human confirmation button** | Dashboard shows "This was me" button on alerts | Any false positive |
| **Event count decay** | After N events from new location, score naturally drops | Gradual travel acceptance |
| **No automatic blocking** | Alerts are informational, not blocking. Score only. | All scenarios |

### The key principle: Alert, don't block

Our system never blocks any user. It raises alerts with a confidence score (0-100). A human analyst (or the user themselves) reviews and decides. This is how Google, Microsoft, and Cloudflare operate in production.

---

## 13. Real Companies and How They Compare

### For report and viva reference

| Company/Paper | What They Do | How We Reference Them |
|---|---|---|
| **Wiefling et al. (ACM TOPS 2022)** | Created the RBA dataset | Our training data source |
| **Google BeyondCorp** | Zero-trust: device identity + continuous verification | Our device fingerprinting draws from zero-trust principle: "never trust, always verify" |
| **BioCatch** | Behavioral biometrics — mouse, typing, touchscreen gestures | Our behavioral overlay inspired by their approach |
| **Microsoft Defender for Identity** | Enterprise UEBA across Azure AD logs | Our architecture (feature extraction → ML → risk scoring → dashboard) aligns with their methodology |
| **CrowdStrike Falcon** | EDR + behavioral analytics at kernel level | Cited as complementary post-login detection |
| **Cloudflare Gateway** | Browser isolation + session recording + zero-trust | Referenced in limitations section |
| **Schölkopf et al. (2001)** | One-Class SVM — theoretical foundation | ML model citation |
| **Liu et al. (2008)** | Isolation Forest — algorithm paper | Primary ML model citation |

### How to use in viva

When asked "how does your system compare to real products":

> *"Our detection approach builds on the same principles as Microsoft Defender for Identity and Google BeyondCorp — using behavioral features to establish a baseline and flag deviations. While our implementation is simpler (designed for BE project scope), the architecture scales: the 8 features correspond to production UEBA systems, the ensemble ML approach is industry standard, and the device fingerprinting follows zero-trust principles. Production systems add streaming infrastructure, automated response, and broader telemetry — documented as future scope."*

---

## 14. Tech Stack — With Frontend Discussion

### Our selected tech stack

| Component | Library | Purpose |
|---|---|---|
| Language | Python 3.10+ | Everyone knows it |
| Data processing | pandas, numpy | Standard |
| Large data querying | DuckDB | Query 8.5GB CSV without loading to RAM. Already has cache (533 MB) |
| ML models | scikit-learn | All 4 models + evaluation |
| Model saving | joblib | Save/load .pkl files |
| API server | FastAPI + uvicorn | Receive events, run inference |
| Dashboard | Streamlit (primary) or HTML/JS (enhancement) | Live UI |
| Charts | plotly | Interactive visualizations in dashboard |
| HTTP client | requests | Laptop 2 sends events |
| Hashing | hashlib (built-in) | SHA256 for device fingerprints |
| Keyboard/mouse capture | pynput | Capture typing speed, mouse speed on client |

### Can we swap Streamlit for React later?

**Yes, easily — if the backend is built correctly from the start.**

The key is SEPARATING the server from the dashboard:

```
Bad (tightly coupled):
  Streamlit does BOTH the API and the UI
  → stuck with Streamlit

Good (swappable):
  FastAPI Server (port 8000)  ←─→  Any Frontend
    - POST /login (receive event, return score)
    - WebSocket /events (stream live alerts)
    - GET /user/{id} (user profile)
    - GET /metrics (model accuracy, events/sec)
```

The server has clean API endpoints. The frontend is just a consumer.

### Frontend options ranked

| Frontend | Effort | Polish | Real-time | Need to learn | When to use |
|---|---|---|---|---|---|
| **Streamlit** | Low (1-2 days) | Medium | Good (WebSocket) | Python only ✓ | Build this FIRST (Week 2) |
| **FastAPI + HTML/JS** | Medium (3-5 days) | High | Great (WebSocket) | Basic JS | Upgrade in Week 3-4 if time permits |
| **FastAPI + React** | High (1-2 weeks) | Highest | Great | React + TS + JSX | Too heavy for 4-week timeline |

### Recommendation for your project

**Build Streamlit in Week 2** — you'll have a working demo fast.

**If you finish early (Week 3-4)**, swap to plain HTML + vanilla JavaScript that reads the same WebSocket and renders a nicer dashboard. Same FastAPI server, same endpoints, same ML — just a different HTML file. Zero backend changes needed.

**Do NOT try React.** Learning React + TypeScript + Zustand + TanStack Query + WebSocket hooks will take 2-3 weeks by itself before you write any project-specific code. Streamlit gets you a working dashboard in 2 days.

### The 3 Tiers: Lowkill → Midkill → Overkill

The backend NEVER changes between tiers. Only the frontend (dashboard) gets swapped. Same FastAPI server, same 4 ML models, same 8 features, same device fingerprinting, same behavioral overlay. The API endpoints stay identical.

```
Backend (SAME across all tiers):
  FastAPI + 4 ML models + 8 features + DuckDB + device fingerprinting + behavioral overlay
  POST /login, WebSocket /events, GET /dashboard, GET /alerts, GET /investigation/{id}
                ↓
Frontend (CHANGES per tier):
  Lowkill  → Streamlit (Python, 1-2 days to build)
  Midkill  → React + Vite + Tailwind + Framer Motion + Recharts (1-2 weeks with AI)
  Overkill → React/Next.js + Deck.gl + visx + Zustand + TanStack Query + Zod (2-3 weeks with AI)
```

#### Lowkill (Week 1-2 — build this first)

| Component | What | Why |
|---|---|---|
| Dashboard | Streamlit | Fastest to build. Python only. Works with backend immediately. |
| Charts | Plotly | Built into Streamlit. Good enough for demo. |
| Map | Plotly choropleth or skip | Simple country-level display. |
| State | Streamlit session state | No setup needed. |
| Animations | None | Streamlit has no animation system. |

**Goal:** Working project by Week 2. Everything functional. Stress gone.

#### Midkill (Week 3 — upgrade if time permits)

| Component | What | Why |
|---|---|---|
| Dashboard | React 18 + Vite | Industry standard. Tailwind for styling. Vite for fast builds. |
| Charts | Recharts | Simple API. Works for <200 data points (fine for our demo). |
| Map | react-simple-maps | SVG-based world map with travel arcs. Good enough for demo. |
| State | React useState + context | Simple. No extra libraries needed for our scope. |
| Animations | Framer Motion | Apple-like spring animations. Alert cards slide in, charts fade. |
| Build tool | Vite | Fast dev server. Instant hot reload. |

**Goal:** Beautiful dashboard. Professional look. Impressive for viva.

#### Overkill (Week 4 buffer — only if everything works and you want max polish)

| Component | What | Why |
|---|---|---|
| Dashboard | React 19 + Next.js 15 | Server components for SSG, streaming for live data |
| Charts | visx (Airbnb) | Handles 10,000+ data points smoothly. Recharts chokes at 200. |
| Map | Deck.gl (Uber) | WebGL — 60fps with thousands of points. Arc layers for impossible travel routes. |
| State | Zustand + TanStack Query | Zustand for UI state, TanStack for server state with auto-refetch |
| Validation | Zod + TypeScript | Every API response validated at runtime. Malformed data caught before UI crashes. |
| Animations | Framer Motion (same) | Already the best. Stays. |
| Event streaming | Kafka / Redpanda | Decouples producers from consumers. Handles millions of events/sec. |
| Time-series DB | ClickHouse | Purpose-built for security logs. Queries billions of rows in milliseconds. |
| Caching | Redis | Sub-millisecond reads for user profiles, device hashes, session counters. |
| AI coding | Cursor / Claude / Copilot | You don't need to know React/TypeScript/Kafka. AI generates the code, you review and run it. |

**Important:** AI coding tools (Cursor, Claude Code, GitHub Copilot) make the overkill stack accessible even if your team doesn't know React or TypeScript. You describe what you want in plain English, AI generates the code, you test it. The backend (your ML pipeline) stays untouched — AI only writes the frontend. This is how beginners ship production-quality UIs in 2026.

**Goal:** This document already describes the overkill stack in detail. There is also a reference midkill project at `/home/igris/projects/identity-anomaly-detection` (React + FastAPI + DuckDB + sklearn) you can look at for inspiration on how the midkill frontend connects to the backend.

#### Build order (what we agreed)

```
Week 1-2:  LOWKILL — Streamlit + FastAPI + sklearn + DuckDB
           Everything works. Demo runs. Stress gone.

Week 3:    MIDKILL — Swap Streamlit → React + Vite + Tailwind + Framer Motion
           Backend stays exactly the same. Only frontend files change.

Week 4:    OVERKILL — Add Deck.gl maps, visx charts, Zustand, TanStack Query
           Only if lowkill and midkill are done. Buffer week.
```

**Each tier is optional.** If lowkill is done and you're happy, stop there. If you want more polish, go midkill. If you want to flex, go overkill. The project works at every tier — each step just makes the presentation better, not the detection.

### Important: Our 8 features vs the reference midkill's 8 features

There is a reference midkill project at `/home/igris/projects/identity-anomaly-detection` with a different set of 8 features:

```
Reference midkill: hour, is_weekend, is_success, mfa_used, mfa_failed, is_vpn, is_tor, is_new_device
Ours:              hour, is_night, is_weekend, country_change, device_change, failed_before_success,
                   rapid_login_rate, login_frequency_today
```

Their features have a problem: RBA dataset doesn't have MFA, VPN, or TOR columns. These are hardcoded to False (always 0). So 4 of their 8 features are dead — never contribute to scoring. Our 8 features are all computable from RBA columns and include per-user UEBA concepts (country_change, device_change) that actually detect attacks. Do not copy their features. Ours are better for this project.

---

## 15. File Structure

```
identity-anomaly-detection/
│
├── data/                          # Dataset files (DuckDB cache built by 01_build_training_data.py)
│   └── (RBA DuckDB cache — already exists)
│
├── src/                           # All source code
│   ├── 01_load_and_sample.py      # Load RBA via DuckDB, sample 500K rows, save as parquet
│   ├── 02_feature_engineering.py  # Compute 8 features using user history → training file
│   ├── 03_train_models.py         # Train 4 models → .pkl files + metrics
│   ├── 04_evaluate.py             # Test accuracy, precision, recall, F1, charts
│   ├── 05_server.py               # FastAPI — /login endpoint, WebSocket stream, model inference
│   ├── 06_client.py               # Laptop 2 script — sends events with Normal/Attack toggle
│   ├── 07_dashboard.py            # Streamlit — live feed, alerts, charts, device fingerprint
│   │
│   └── utils/
│       ├── features.py            # extract_features(row, user_history) — core function
│       └── device_fingerprint.py  # generate_device_hash(mac, hostname, cpu, screen)
│
├── models/                        # Created by train_models.py
│   ├── isolation_forest.pkl
│   ├── one_class_svm.pkl
│   ├── local_outlier_factor.pkl
│   ├── elliptic_envelope.pkl
│   └── model_metrics.json
│
├── outputs/                       # Created by evaluate.py and dashboard
│   ├── confusion_matrix.png
│   ├── model_comparison.png
│   └── feature_importance.png
│
├── requirements.txt
└── README.md
```

### What each file does

**01_load_and_sample.py** — Connects to DuckDB cache, queries stratified sample (all ATOs + Attack IP rows + random normal), saves as parquet.

**02_feature_engineering.py** — Reads sample, groups by user chronologically, computes 8 features per row using user history (last 10 logins, last 60 seconds, last 5 minutes). Most complex file.

**03_train_models.py** — Loads training data, splits 80/20, trains all 4 models, saves .pkl files to models/.

**04_evaluate.py** — Loads models + test data, computes per-model metrics, generates charts, benchmarks events/sec.

**05_server.py** — FastAPI server. On startup: loads 4 .pkl models. POST /login: receives event, computes 8 features using live user history, runs all 4 models, checks device hash, returns risk score + breakdown. WebSocket: streams results to dashboard.

**06_client.py** — Laptop 2 script. Sends POST /login to server. Toggle 'n' for normal, 'a' for attack. Sends device info (MAC, hostname, CPU, screen), typing speed, mouse speed.

**07_dashboard.py** — Streamlit app. Subscribes to WebSocket for live events. Shows feed with color coding, alert cards with feature breakdown, device fingerprint match/mismatch, behavioral profile, charts.

**utils/features.py** — `extract_features(event_dict, user_history) → dict` — takes a single event + user history, returns all 8 feature values.

**utils/device_fingerprint.py** — `generate_device_fingerprint(mac, hostname, cpu, screen) → str` — SHA256 hash. `check_device_known(user_id, device_hash) → bool`.

---

## 16. Team Work Distribution

| Member | Primary | Files They Own | What They Deliver | What They Need to Learn |
|---|---|---|---|---|
| **Hemanth** | Data Pipeline | `01_load_and_sample.py`, `02_feature_engineering.py`, `utils/features.py` | Cleaned training file (500K rows, 9 columns) with all 8 features computed using user history | pandas, DuckDB, groupby/sort, rolling windows |
| **Urvashi** | ML Models | `03_train_models.py`, `04_evaluate.py` | 4 trained .pkl model files + accuracy report (accuracy, precision, recall, F1 per model) + charts | sklearn API (.fit, .predict), metrics, train_test_split, joblib |
| **Veenashree** | Dashboard | `07_dashboard.py` | Streamlit app with: live feed, alert cards with breakdown, device fingerprint display, behavioral overlay, charts | Streamlit, plotly, WebSocket client |
| **Vishwanath** | Live Demo System | `05_server.py`, `06_client.py`, `utils/device_fingerprint.py` | End-to-end demo: Laptop 2 client sends events → FastAPI server scores → WebSocket streams to dashboard | FastAPI, uvicorn, requests, hashlib, terminal UI |

### How dependencies flow

```
Hemanth's output (training_data.parquet)
    → Urvashi uses it to train models
    → Urvashi's output (.pkl files)
        → Vishwanath loads them in server.py
        → Veenashree displays model results in dashboard
        → Vishwanath's server.py streams events to Veenashree's dashboard
```

**Critical path (must work in order):** Hemanth → Urvashi → Vishwanath + Veenashree (parallel)

### If someone drops out

| If missing | Impact | Mitigation |
|---|---|---|
| Hemanth | No training data | Use raw RBA directly in train_models.py (slower, still works) |
| Urvashi | No trained models | Use pre-trained example models or scikit-learn defaults for demo |
| Veenashree | No dashboard | Streamlit is simple — anyone can build a basic version in 1 day |
| Vishwanath | No live demo | Pre-built simulation in dashboard with "Inject Attack" button. Demo still works. |

---

## 17. Timeline — 4 Weeks

### Week 1: Foundation

| Day | Hemanth | Urvashi | Veenashree | Vishwanath |
|---|---|---|---|---|
| Mon | Setup Python, install deps, verify DuckDB cache | Same setup + learn sklearn basics | Same setup + learn Streamlit basics | Same setup + learn FastAPI basics |
| Tue | 01_load_and_sample.py — DuckDB query, sample 500K | Read sklearn docs for all 4 models | Dashboard skeleton — title, 3 tabs, layout | utils/device_fingerprint.py — hash generation |
| Wed | 02_feature_engineering.py — simple features (hour, night, weekend) | Train Isolation Forest on sample | Tab 1: live feed with mock data | 05_server.py — /login endpoint, mock score |
| Thu | Contextual features: country_change, device_change with user history | Train Elliptic Envelope + LOF | Tab 2: charts with mock data | 05_server.py — load .pkl, score real event |
| Fri | Contextual features: failed_before_success, rapid_rate, frequency | Train One-Class SVM on 50K subset | Tab 3: device info, behavioral display | 06_client.py — sends POST with device info |
| Sat | Debug + validate features with small sample | Compare 4 models, save best params | Connect dashboard to mock API | Test client→server communication |
| Sun | **Training file ready. Hand off to Urvashi** | Review training file. Ready to train. | Dashboard skeleton ready | Server skeleton ready |

### Week 2: Core Build

| Day | Hemanth | Urvashi | Veenashree | Vishwanath |
|---|---|---|---|---|
| Mon | Bug fixes, feature engineering doc | Train all 4 models on full 500K | Live feed — real events via WebSocket | WebSocket endpoint in server.py |
| Tue | Help Urvashi if needed | Evaluate — accuracy, precision, recall, F1 | Alert cards — show when score > 75 | Client sends typing + mouse speed |
| Wed | Feature importance analysis | Generate charts (model comparison, confusion) | Device fingerprint display (known/unknown) | Device hash checking in server |
| Thu | Report: feature engineering section | Save .pkl files to models/ | Behavioral overlay — typing + mouse display | Integration: client→server→dashboard |
| Fri | Report: dataset section | Report: models section | Polish dashboard UI | Fix integration issues |
| Sat | Help team with blockers | Help team with blockers | Help team with blockers | Help team with blockers |
| Sun | Buffer | Buffer | Buffer | Buffer |

### Week 3: Integration and Demo

| Day | All Team Members |
|---|---|
| Mon | Full integration: client sends → server scores → dashboard shows live |
| Tue | Test both modes: NORMAL (green) and ATTACK (alerts) |
| Wed | Edge case testing: travel scenario, unknown device, typing change |
| Thu | Behavioral overlay complete: typing speed + mouse speed per event |
| Fri | Demo rehearsal. Run 5-minute script. Time it. |
| Sat | Fix issues from rehearsal |
| Sun | Second rehearsal. Everything smooth. |

### Week 4: Report, Presentation, Buffer

| Day | All Team Members |
|---|---|
| Mon | Report: intro, literature survey, methodology |
| Tue | Report: implementation, results, screenshots |
| Wed | Report: limitations, future scope, conclusion |
| Thu | Presentation slides. Each member prepares their section. |
| Fri | Full dress rehearsal with guide (Dr. Anitha) |
| Sat | Fix last issues. Print report. Practice viva answers. |
| Sun | Rest. Ready for viva. |

---

## 18. Live Demo Script — 5 Minute Viva

### Setup (before examiner arrives)

- Laptop 1: Server running (`python src/05_server.py`), Dashboard open (`streamlit run src/07_dashboard.py`)
- Laptop 2: Client ready (`python src/06_client.py`), visible on table
- Both laptops on same WiFi network
- Dashboard visible on projector/external monitor
- Client terminal visible (to show mode toggle: 'n' for normal, 'a' for attack)

### Script

| Time | Speaker | Action | Dashboard | What to say |
|---|---|---|---|---|
| 0:00-0:30 | Vishwanath | Both laptops ready, click Start | "SYSTEM READY" | "This is our AI-Based Identity Anomaly Detection System. It monitors login events in real-time using 4 ML models trained on 31.3 million events from a real enterprise SSO system." |
| 0:30-1:00 | Hemanth | Laptop 2 sends normal events (5 sec apart) | Green rows appearing. "igris | India | 2pm | Score: 5/100 ✓" | "Laptop 2 is logging in as igris — normal behavior. India, Chrome browser, daytime. All 8 features show normal values. Device fingerprint matches known device. Score: 5/100." |
| 1:00-1:15 | Hemanth | Point to device fingerprint | "Device: igris-laptop ✓" | "Each laptop is fingerprinted using SHA256 hash of MAC, hostname, CPU, screen. This hash matches igris's known device — so it's trusted." |
| 1:15-1:30 | Urvashi | Send night login (normal but unusual time) | Yellow: "igris | India | 11pm | Score: 28/100" | "Now igris logs in at 11pm. Hour feature fires, score rises to 28. But country and device match — so still low. System doesn't overreact to single changes." |
| 1:30-2:00 | Urvashi | Switch to ATTACK MODE on Laptop 2 | **RED ALERT**: "igris | Russia | 3am | Score: 94/100 🚨" | "Now toggle to attack mode. Client sends Russia, 3am, Android device. Never seen before. Watch the alert appear with 94/100 risk." |
| 2:00-2:30 | Urvashi | Expand alert details | Shows: country_change=1, device_change=1, night=1, failed_before_success=12, rapid_rate=34, device hash mismatch, typing 120 vs 62 wpm | "Breakdown: 4 models voted anomaly. Country changed to Russia, device to Android, 12 failed attempts before success, 34 rapid logins. Device hash is unknown. Typing speed 120 wpm vs normal 62." |
| 2:30-2:45 | Veenashree | Show model comparison chart | Bar chart: IF 0.92, SVM 0.88, LOF 0.79, EE 0.95, Ensemble 0.89 | "Each model scores independently. No single model trusted alone. Ensemble averages to give final confidence." |
| 2:45-3:00 | Veenashree | Click "This was me" | Score drops. Device becomes known. | "If igris was actually traveling, click 'This was me.' System adds Russia + Android to known list. Future events from Russia won't trigger." |
| 3:00-3:15 | Vishwanath | Send normal events again | Green: Score 5/100 | "Back to normal. System adapts. Real-time detection with false positive handling." |
| 3:15-3:30 | Vishwanath | Same laptop attack (stolen device) | Alert with device match but ML fires | "Stolen laptop scenario: same device hash matches, but behavior is wrong. 8 features still fire. Combined score 85." |
| 3:30-3:45 | Any | Summary metrics | Show metrics panel | "Performance numbers are being re-measured honestly after Phase 3 retraining — the 94.2%/91.7%/88.3% figures in early drafts were never actually measured (real recall was ~2%). Processing speed benchmark: 2847 events/sec." |
| 3:45-4:00 | Any | Limitations slide | Show "What We Don't Detect" | "We acknowledge limitations: perfect mimic, MFA bypass, post-login threats. These require additional controls documented in our report." |
| 4:00-5:00 | All | Q&A | — | See viva preparation section |

### Backup (if client-server network fails)

Dashboard has "Simulate Events" button that replays pre-recorded events from test set. Same alerts, charts, and analysis work without Laptop 2.

---

## 19. Dashboard Wireframe

```
┌──────────────────────────────────────────────────────────────────────┐
│  🔒 AI-BASED IDENTITY ANOMALY DETECTION       ● SYSTEM ACTIVE       │
│  Status: Running | Events: 152 | Alerts: 12 | Users: 1              │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│ ┌──── LIVE FEED ───────────────────────────────────────────────────┐│
│ │                                                                    ││
│ │  ✓  igris  India  14:30  igris-laptop ✓  62wpm ✓  05/100  SAFE  ││
│ │  ✓  igris  India  14:35  igris-laptop ✓  61wpm ✓  08/100  SAFE  ││
│ │  ✓  igris  India  14:40  igris-laptop ✓  63wpm ✓  04/100  SAFE  ││
│ │  ⚠  igris  India  23:15  igris-laptop ✓  60wpm ✓  28/100  NIGHT││
│ │  ✓  igris  India  23:20  igris-laptop ✓  62wpm ✓  12/100  SAFE  ││
│ │                                                                    ││
│ │  🚨 ALERT #12 — HIGH RISK ────────────────────────────────────── ││
│ │  igris  Russia  03:15  UNKNOWN DEVICE ✗  120wpm ✗  94/100       ││
│ │  ┌─────────────────────────────────────────────────────────────┐ ││
│ │  │ Triggered Features               Model Scores               │ ││
│ │  │ country_change:   1 (≠ India)    IF:  0.92  🚨             │ ││
│ │  │ device_change:    1 (≠ iPhone)   SVM: 0.88  🚨             │ ││
│ │  │ night:            1 (3am)        LOF: 0.79  ⚠              │ ││
│ │  │ failed_before:    12 attempts    EE:  0.95  🚨             │ ││
│ │  │ rapid_rate:       34/min         ─────────────────          │ ││
│ │  │ frequency:        45 today       ENSEMBLE: 0.89 🚨         │ ││
│ │  └────────────────────────────────────────────────────────────┘ ││
│ │  Device: UNKNOWN (hash ff99 ≠ stored a3f2)                      ││
│ │  Typing: 120 wpm (profile: 62±8 — 7.2σ deviation)              ││
│ │  Mouse:  890 px/s (profile: 320±50 — 11.4σ deviation)          ││
│ │  [✓ This was me — add to known]  [🔇 Mute alert]               ││
│ │                                                                    ││
│ └────────────────────────────────────────────────────────────────────┘│
│                                                                      │
│ ┌─ MODELS ────────────────┐  ┌─ ALERTS OVER TIME ──────────────────┐│
│ │                         │  │                                     ││
│ │  IF  ████████████░ 0.92│  │  🚨│   ▄▄  ▄▄                       ││
│ │  SVM ██████████░░ 0.88 │  │    │▄▄ ██ ▄▄█▄ ▄▄                   ││
│ │  LOF ████████░░░░ 0.79 │  │    ██ ██ ████ ██ ▄▄                 ││
│ │  EE  ███████████░ 0.95 │  │    ██ ██ ████ ██ ██ ▄▄              ││
│ │  ENS ██████████░░ 0.89 │  │    ─────────────────────────         ││
│ │          0.0    1.0    │  │    14:00  14:30  15:00               ││
│ └────────────────────────┘  └──────────────────────────────────────┘│
│                                                                      │
│ ┌─ USER PROFILE: igris ───────────────────────────────────────────┐│
│ │                           Current     Profile    Status         ││
│ │  Typing Speed:             62 wpm      62±8 wpm  ✓ MATCH       ││
│ │  Mouse Speed:              320 px/s   300±50 px/s ✓ MATCH      ││
│ │  Known Devices:            1 (igris-laptop)                     ││
│ │  Seen Countries:           India, Russia (added from alert)     ││
│ │  Seen Devices:             iPhone, Android (added from alert)   ││
│ │  Sessions Today:           5 (normal: 3-8)                     ││
│ └────────────────────────────────────────────────────────────────────┘│
├──────────────────────────────────────────────────────────────────────┤
│  Performance: 2,847 events/sec | Accuracy: TBD (being re-measured)      │
│  Precision: TBD | Recall: TBD | F1: TBD | Last updated: 14:45:23        │
│  🛡 Defense-in-Depth: ML Ensemble + Device Fingerprint + Behavior   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 20. GPU Utilization (RTX 3050 6GB VRAM)

### What the GPU enables

| ML Task | CPU (sklearn) | GPU (cuML/RAPIDS) | Our choice | Why |
|---|---|---|---|---|
| Isolation Forest (500K rows) | ~30 seconds | ~2 seconds | CPU | 30 seconds is fine for training once |
| One-Class SVM (50K rows) | ~5 minutes | ~20 seconds | CPU | Training once, doesn't matter |
| LOF (500K rows) | No training (lazy) | No training | CPU | No training needed |
| Elliptic Envelope (500K rows) | ~10 seconds | ~1 second | CPU | Already fast |
| **Full 31.3M training** | **Hours (won't work)** | **Minutes** | **Not needed** | We sample 500K |
| **Deep learning (autoencoder)** | Slow | Fast | **Not using** | Not enough attack data |

### Why we don't NEED the GPU for core project

- sklearn handles 500K rows in 30 seconds per model
- Training happens once before the demo — speed doesn't matter
- Inference is <1ms per event on CPU — no GPU needed for live scoring

### Where GPU could help (if time permits in Week 4)

- **Path B revisit** — if we generate synthetic behavioral data, cuML can train on the full expanded dataset faster
- **Full 31.3M benchmark** — prove the system scales by running cuML on all 31.3M rows
- **Dashboard visualization** — no GPU impact (Streamlit is CPU-bound)

**Bottom line:** The RTX 3050 is available but not required. Build the core project with CPU-first sklearn. If done early, GPU acceleration can be an enhancement.

---

## 21. Viva Preparation — Likely Questions and Answers

### Q1: Why 4 models instead of 1?

> *"Ensemble reduces false positives. Different models catch different patterns: Isolation Forest isolates rare events, One-Class SVM detects novelty, LOF detects local density anomalies, Elliptic Envelope catches statistical outliers. Averaging their scores is more reliable than any single model. An event triggering only 1 of 4 models gets a low score. An event triggering all 4 gets a high score with high confidence."*

### Q2: Why 8 features? Why not more or fewer?

> *"8 features cover the 4 dimensions of identity: who (user), what (device), where (country), when (time), how (velocity, frequency). The RBA dataset has exactly these columns available. More features would require data we don't have — file access logs, network traffic, process execution. Fewer features would miss important attack patterns — using only country would miss same-country attacks with device changes."*

### Q3: Why not deep learning?

> *"Deep learning requires thousands of diverse attack samples — we have 141 confirmed ATOs and 3.1M Attack IP rows from RBA (804K successful; most attack rows are repeated bot patterns). scikit-learn models are also interpretable: we can show exactly why a row was flagged (which features, which model contributed). Deep learning is a black box — for a BE project, explainability matters more than marginal accuracy gain."*

### Q4: How is this different from a simple rule-based system?

> *"A rule-based system uses hard thresholds: 'if country ≠ India → block.' Our ML models learn probabilistic patterns from 500K real events. For example, the model learns that 'country_change + night + device_change together = 92/100 risk' but 'country_change + daytime + same device = 35/100 risk.' Rules are binary. ML gives nuanced scoring with feature interactions that rules can't capture."*

### Q5: Is your ML actually learning or just memorizing your rules?

> *"Our ML trains on 8 real features from 500K RBA events with real attack labels (Is Attack IP column from the dataset). The models learn non-linear patterns validated on held-out test data — real metrics are being re-measured after Phase 3 (the 94.2%/91.7%/88.3% figures in earlier drafts were never measured; actual recall was ~2%).*
>
> *The behavioral biometrics (typing speed, mouse speed) are NOT fed into the ML. They are displayed on the dashboard as a separate rule-based overlay, which we clearly distinguish in our report. The ML is trained on real data only."*

### Q6: What can't your system detect?

> *"Three categories:*
> *1. Perfect physical mimic — someone who steals the device and password and copies behavior exactly. No behavioral system detects this. Requires MFA + hardware keys.*
> *2. MFA bypass — if MFA is passed, the login looks completely normal to our system.*
> *3. Post-login threats — insider activity after authentication. Our system monitors login events only.*
>
> *Production systems add endpoint detection (CrowdStrike), continuous verification (BeyondCorp), and session behavior analysis for these scenarios."*

### Q7: What if the user travels? Won't you get false positives?

> *"Yes — this is the fundamental tension in anomaly detection. We handle it with three strategies:*
> *1. 'Seen before' memory — once a country or device is seen for a user, it's no longer flagged.*
> *2. Rolling baseline adaptation — behavioral metrics shift over 5-10 events.*
> *3. Human confirmation button — 'This was me' adds the location to the known list.*
>
> *We never block automatically. We alert with a score. This is the same approach Google and Microsoft use."*

### Q8: What dataset did you use and why?

> *"The RBA dataset from Telenor Norway (Wiefling et al., ACM TOPS 2022). 31.3 million login events with country, device type, browser, OS, timestamp, success/failure, and attack labels. LANL (89 GB, no country/device info) and CERT r4.2 (16 GB, no country/device/success columns) lack critical columns for our 8 features. RBA is the only dataset with all columns needed."*

### Q9: How do you know your behavioral features aren't fake ML?

> *"They aren't trained into the ML. The typing speed and mouse speed are displayed on the dashboard as transparent rule-based metrics — we show the current value vs the user's profile and let the human analyst decide. The ML models train only on the 8 real RBA features with real RBA labels. There is no synthetic data in the ML pipeline. This distinction is clearly documented in our report."*

### Q10: How is this project relevant to industry?

> *"Our architecture mirrors production UEBA systems from Microsoft Defender for Identity, Google BeyondCorp, and Cloudflare. The same principles — behavioral features, ensemble ML, risk scoring, alert-based response — are used by these platforms at scale. Our implementation is simplified for a BE project scope but follows the same detection methodology."*

### Q11: Can this be deployed in a real company?

> *"The core detection pipeline is production-ready. To deploy at scale, you'd add: streaming infrastructure (Kafka), persistent storage (PostgreSQL or Elasticsearch), automated response integration (SSO API to revoke sessions), and broader telemetry (file access logs, network flows). These are documented as future scope in our report."*

### Q12: What was the hardest part?

> *"Feature engineering with user context — computing country_change and device_change requires maintaining per-user history across 31.3 million events in chronological order. The second hardest was handling class imbalance — only 141 confirmed ATOs in 31.3M events. We addressed this by using Is Attack IP as our primary label (~3.1M attack rows) and user-based stratified sampling."*

### Q13: Individual contribution questions

| Member | Expected to answer |
|---|---|
| **Hemanth** | Walk through feature engineering logic with user history. Show DuckDB query. Explain how country_change is computed using last 10 logins. |
| **Urvashi** | Explain each model briefly. Show accuracy metrics. Explain train/test split. Explain why ensemble is better than single model. |
| **Veenashree** | Show dashboard live. Explain Streamlit, WebSocket connection. Walk through alert card UI. Explain chart choices. |
| **Vishwanath** | Show client→server communication. Explain FastAPI endpoint. Show device fingerprinting hash logic. Explain demo architecture. |

---

## 22. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **One-Class SVM too slow** for 500K rows | High | Medium | Train on 50K subset. If still too slow, drop it and use 3 models. Ensemble still effective with 3. |
| **DuckDB cache corrupted/missing** | Low | High | Download RBA from Zenodo (2 hours). Keep download URL and script ready. |
| **Client→server network fails during viva** | Medium | High | Dashboard has backup "Simulate Events" button that replays pre-recorded test data. Demo continues without Laptop 2. |
| **Model accuracy < 80%** | Low | Medium | Add ensemble fallback rule: if 3+ features fire, flag as suspicious. Hybrid approach still strong. |
| **Team member absent on viva day** | Low | Medium | Everyone knows how to run all parts. Commands documented in README. No single point of failure. |
| **Streamlit dashboard slow** | Medium | Low | Limit feed to last 50 events. Polling 1 second. Pre-generate charts from evaluation data. |
| **Keyboard/mouse capture not working** | Medium | Low | Behavioral values hardcoded per mode (normal=62, attack=120). Live capture is enhancement, not dependency. |
| **31.3M sampling too slow** | Low | Medium | DuckDB query for 500K rows takes <30 seconds. If slow, reduce to 100K. |

---

## 23. Getting Started Commands

```bash
# 1. Create project directory
mkdir -p ~/Documents/projects/identity-anomaly-detection
cd ~/Documents/projects/identity-anomaly-detection

# 2. Create directory structure
mkdir -p src/utils models data outputs

# 3. Install dependencies
pip install pandas numpy scikit-learn streamlit plotly duckdb fastapi uvicorn requests joblib pynput

# 4. Run in order (training pipeline)
python src/01_load_and_sample.py
python src/02_feature_engineering.py
python src/03_train_models.py
python src/04_evaluate.py

# 5. Start live demo
python src/05_server.py &            # Start FastAPI server (port 8000)
streamlit run src/07_dashboard.py &  # Start Streamlit dashboard (port 8501)
python src/06_client.py              # Start client on Laptop 2

# 6. Stop
# Ctrl+C in each terminal, or: kill %1 %2 %3
```

---

## Appendix: AI Prompt for Team Members

If your teammates won't read this whole document, they can copy-paste this prompt into ChatGPT/Claude/Gemini along with this file:

```
I am a BE Computer Science student working on "AI-Based Identity Anomaly Detection System" with 3 teammates. I have attached the complete project reference document.

My role is: [Hemanth / Urvashi / Veenashree / Vishwanath — pick one]

Explain the entire project to me from scratch. Assume I know basic Python but have never built an ML project. Do not summarize or skip anything. Cover:

1. What are we building and why
2. The 8 features — explain each one with an example
3. The 4 ML models — how each works and why we use all 4
4. The 3 detection layers: ML, device fingerprinting, behavioral biometrics
5. What we can detect vs what we cannot detect
6. The 3 tiers (lowkill/midkill/overkill) and what changes in each
7. Edge cases: travel, stolen laptop, first login, false positives — how we handle each
8. My specific role: what files I build, what each file does, what code goes inside, and how my work connects to the rest of the team
9. The weekly timeline — what gets done when
10. The live demo script — what happens during the 5-minute viva
11. Viva questions I need to be ready for, and how to answer

After explaining everything, give me a checklist of exactly what I need to do this week.
```

Each team member just needs to:
1. Open `COMPLETE_PROJECT_REFERENCE.md`
2. Copy the prompt above
3. Replace `[Hemanth / Urvashi / Veenashree / Vishwanath]` with their name
4. Drop the file into ChatGPT/Claude/Gemini or paste its content

---

## Final Notes

This document captures everything from our full conversation. Every concept explained, every decision made, every edge case discussed. Use it as your team's complete reference for the entire project lifecycle — from understanding what you're building to defending it in viva.

**The 3 key strengths of this project:**
1. **Real ML** — trained on 4 models with real RBA data and real attack labels. No fake data.
2. **Defense-in-depth** — 3 detection layers (ML + device fingerprint + behavioral) work together.
3. **Honest limitations** — no claim of perfection. Clear documentation of what cannot be detected.

**The 3 things to remember during viva:**
1. You detect REMOTE identity attacks (credential theft, brute force, account takeover) — that's your scope.
2. You do NOT detect physical device theft with perfect behavior mimic — that's everyone's limitation.
3. Alert. Don't block. The system raises scores, not barriers.
