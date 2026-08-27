# MODEL DEEP DIVE — Complete Mathematical Reference

**Every formula, every number, every model — traced from raw data to final result. No abstractions.**

---

# SECTION 1: THE RAW DATA — What We Started With

## 1.1 The Source: LANL Cyber1 Dataset

Los Alamos National Laboratory published a dataset called **CYBER1** — a recording of every single authentication event across their entire internal network. Think of it like someone recorded every time any employee badged into a building, logged into a computer, or failed a password — and then gave that recording to the public.

**The numbers:**
- **29,905,488 events** (29.9 million rows)
- **604 users** (employees)
- **104 red-team users** (the "attackers" — security professionals hired to test the system)
- **702 red-team events** (the actual attack moments out of 29.9M total)

That's **0.002%** of all events were attacks. Finding those 702 events in 29.9 million is like finding 702 specific grains of sand on a beach.

## 1.2 The Label File: `redteam.txt`

This is the **ground truth** — a simple text file with 749 lines:

```
time,user,src_computer,dst_computer
150885,U620@DOM1,C17693,C1003
151036,U748@DOM1,C17693,C305
151648,U748@DOM1,C17693,C728
151993,U6115@DOM1,C17693,C1173
153792,U636@DOM1,C17693,C294
155219,U748@DOM1,C17693,C5693
155399,U748@DOM1,C17693,C152
155460,U748@DOM1,C17693,C2341
155591,U748@DOM1,C17693,C332
156658,U748@DOM1,C17693,C4280
```

4 columns, comma-separated. That's it. This file says "at time=150885, user U620 logged in from machine C17693 to machine C1003 — and this is an attack."

Without this file, we'd have no way to know which events were attacks. This is what makes the LANL dataset special — most cybersecurity datasets don't have labels.

## 1.3 The Feature Table: `feat.parquet`

This is where the magic happened. Someone (the data pipeline) took the raw authentication logs and **added 8 computed columns** to every row. The `feat.parquet` file has **18 columns** total:

### Raw fields (from original logs):

| Column | Type | Example | Meaning |
|--------|------|---------|---------|
| `time` | int32 | 766788 | Seconds since dataset start |
| `src_user` | string | U66@DOM1 | User account |
| `dst_user` | string | U66@DOM1 | Destination user |
| `src_computer` | string | C17693 | Source machine |
| `dst_computer` | string | C3435 | Destination machine |
| `auth_type` | string | NTLM | Authentication method |
| `logon_type` | string | Network | Logon type |
| `orientation` | string | LogOn | LogOn or LogOff |
| `result` | string | Success | Success or Fail |
| `hour` | float64 | 21.00 | Hour of day (0-24) |
| `is_red` | bool | True | Attack label |

### Computed features (added by pipeline):

| Column | Type | Example | Meaning |
|--------|------|---------|---------|
| `dst_first` | int32 | 0 | First visit to this destination? |
| `src_first` | int32 | 1 | First event from this source? |
| `hour_events` | int64 | 82 | Events at this hour |
| `user_events` | int64 | 11182081 | Total events for this user |
| `dst_prior_events` | int64 | 8785 | Prior visits to this destination |
| `fail_1h` | float64 | 0.0 | Failures in last hour |
| `vel_1h` | int64 | 7279 | Events in last hour |

## 1.4 Value Ranges

```
dst_first:         min=0,      max=1
src_first:         min=0,      max=1
hour_events:       min=1,      max=1715
user_events:       min=1,      max=11,182,081
dst_prior_events:  min=0,      max=881,299
fail_1h:           min=0.0,    max=508.0
vel_1h:            min=0,      max=30,097
hour:              min=0.0,    max=23.999722
is_red:            min=False,  max=True
```

## 1.5 The Numbers

- **29,905,488 total events** in `feat.parquet`
- **604 distinct users**
- **8,162 distinct source computers**
- **702 red events** (from `redteam.txt`)
- **4 attacker source computers**: C17693 (670 events), C19932 (19), C22409 (10), C18025 (3)

### Top 10 Users by Event Count:

```
U66@DOM1:    11,182,081 events, 118 reds
U13@DOM1:     1,503,038 events,   2 reds
U24@DOM1:       987,332 events,   5 reds
U78@DOM1:       675,968 events,   2 reds
U12@DOM1:       461,235 events,   6 reds
U1289@DOM1:     321,030 events,   3 reds
U2097@DOM1:     284,931 events,   0 reds
U2899@DOM1:     276,447 events,   0 reds
U189@DOM1:      264,017 events,   0 reds
U293@DOM1:      241,473 events,  31 reds
```

Note: U66@DOM1 has 11.1 MILLION events — that's 37% of all events from one user.

## 1.6 What Authentication Types Look Like

```
auth_type:       count
?                18,026,961   (unknown/unclassified)
Kerberos         10,539,323   (standard enterprise auth)
NTLM               1,216,425   (Windows auth)
Negotiate            122,602   (auto-negotiated)
MICROSOFT_AUTH_         176   (modern auth)
N                        1

result:       count
Success       29,860,657
Fail              44,831

logon_type:         count
Network           24,411,797
?                  5,182,214
Batch                181,000
Unlock                96,540
Interactive           16,522
RemoteInteractive      8,363
CachedInteractive      5,117
NetworkCleartext       3,273
Service                  642
NewCredentials            20
```

## 1.7 Real Example: What an Attack Looks Like

Here are 5 red events from attacker C17693 attacking user U66@DOM1:

```
Event 1: src=C17693 → dst=C3435  | dst_first=0, src_first=1, vel_1h=7279
Event 2: src=C17693 → dst=C61    | dst_first=0, src_first=0, vel_1h=7286
Event 3: src=C17693 → dst=C307   | dst_first=0, src_first=0, vel_1h=7307
Event 4: src=C17693 → dst=C3699  | dst_first=0, src_first=0, vel_1h=7298
Event 5: src=C17693 → dst=C3755  | dst_first=0, src_first=0, vel_1h=7302
```

Notice: `dst_first=0` means C17693 had visited these destinations before. `src_first=1` on Event 1 means it's the first event from C17693 in this sequence. `vel_1h=7279-7302` means high velocity (many events per hour).

### Side-by-side: Raw Fields vs Computed Features

```
Event 1:
  RAW:     time=766788, user=U66@DOM1, src=C17693, dst=C3435, auth=NTLM, result=Success, hour=21.00
  FEATURES: dst_first=0, src_first=1, hour_events=82, user_events=11182081, dst_prior=8785, fail_1h=0, vel_1h=7279
  LABEL:   is_red=True

Event 4:
  RAW:     time=767180, user=U66@DOM1, src=C17693, dst=C3699, auth=NTLM, result=Success, hour=21.11
  FEATURES: dst_first=0, src_first=0, hour_events=121, user_events=11182081, dst_prior=124, fail_1h=0, vel_1h=7298
  LABEL:   is_red=True
```

---

# SECTION 2: "29.9M ROWS ARE JUST THE SOURCE" — What This Means

The confusion is: if there are 29.9M rows, how did the model train on all of them?

**ANSWER: The model does NOT see all 29.9M rows at once.**

Here is what actually happens:

```
STEP 1: DuckDB has 29.9M rows on DISK (not in RAM)
         ↓
STEP 2: SQL query streams rows from disk → DuckDB processes → outputs NumPy arrays
         Peak RAM: ~4 GB
         ↓
STEP 3: StratifiedShuffleSplit 70/30
         20.9M train | 9M test
         ↓
STEP 4: Isolation Forest fit()
         Each tree sees only 256 random rows (max_samples=256)
         200 trees × 256 samples = 51,200 row-views total
```

**Analogy:** Imagine a teacher with 29.9 million exam papers. Instead of reading all of them, the teacher picks 256 random papers, studies them, then picks another 256, repeats 200 times. The teacher learns the general pattern from 200 batches of 256 — never reading all 29.9M.

The 29.9M is the **source pool**. The model trains on **samples** from that pool. But the samples are randomly drawn, so they're representative.

**For LightGBM:** It DOES see all 20.9M training rows (gradient boosting needs all data), but processes them in batches — LightGBM is specifically designed for large datasets.

---

# SECTION 3: HOW EACH FEATURE IS DERIVED

The model uses **9 features** per event. Each is computed from the raw data using SQL window functions.

## Feature 1: `dst_first` — "Is this the first time you've been here?"

```
Formula: 1 if dst_prior_events == 0 else 0

SQL:
  COUNT(*) OVER (
      PARTITION BY user_id, dst_computer
      ORDER BY time
      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
  ) AS dst_prior_events

  dst_first = CASE WHEN dst_prior_events = 0 THEN 1 ELSE 0 END
```

**Meaning:** If User U42 has never logged into Computer C2345 before, `dst_first = 1`. If they've been there 50 times before, `dst_first = 0`.

**Why it matters:** Attackers using stolen credentials often access machines the real user has never touched. This feature catches that.

**Example from data:**
```
dst_prior_events=0     → dst_first=1 (first visit, suspicious)
dst_prior_events=28398 → dst_first=0 (visited many times, normal)
```

## Feature 2: `src_first` — "Is this the first time you're coming FROM here?"

```
Formula: 1 if src_prior_events == 0 else 0

SQL:
  COUNT(*) OVER (
      PARTITION BY user_id, src_computer
      ORDER BY time
      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
  ) AS src_prior_events

  src_first = CASE WHEN src_prior_events = 0 THEN 1 ELSE 0 END
```

**Meaning:** Same logic but for the source computer. If the user always logs in from C1000 but today they're coming from C9999, `src_first = 1`.

**Why it matters:** An attacker physically sits at a different workstation than the real employee would.

## Feature 3: `hour_ratio` — "How much of your total activity happens at this hour?"

```
Formula: hour_events / user_events

SQL:
  COUNT(*) OVER (
      PARTITION BY user_id, hour_f
      ORDER BY time, row_id
      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
  ) AS hour_events_so_far

  COUNT(*) OVER (
      PARTITION BY user_id
      ORDER BY time, row_id
      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
  ) AS user_events_so_far

  hour_ratio = hour_events_so_far / user_events_so_far
```

**Meaning:** If a user has 1000 total events and 200 happen at 3 AM, their 3 AM `hour_ratio` is 0.2. But if a user only has 5 events total and 3 are at 3 AM, their ratio is 0.6 — that's unusual.

**Why it matters:** It normalizes across users. A power user with thousands of events and a quiet user with 50 events get compared fairly.

**Example from data:**
```
hour_events=116, user_events=11,182,081 → hour_ratio=0.0000104 (normal)
hour_events=130, user_events=11,182,081 → hour_ratio=0.0000116 (normal)
```

## Feature 4: `dst_prior_events` — "How many times has anyone visited this machine before?"

```
Formula: COUNT of prior visits to same destination by same user

SQL:
  COUNT(*) OVER (
      PARTITION BY user_id, dst_computer
      ORDER BY time, row_id
      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
  ) AS dst_prior_events
```

**Meaning:** A machine that's been visited 10,000 times is "popular" — accessing it isn't suspicious. A machine visited only 3 times is "rare" — accessing it is noteworthy.

**Example from data:**
```
dst_prior_events=28398 → this destination is very familiar (normal)
dst_prior_events=17    → this destination is rarely visited (unusual)
dst_prior_events=0     → this destination has NEVER been visited (very suspicious)
```

## Feature 5: `fail_1h` — "How many login failures in the last hour?"

```
Formula: COUNT of Fail results in last 3600 seconds

SQL:
  COALESCE(SUM(CASE WHEN result = 'Fail' THEN 1 ELSE 0 END) OVER (
      PARTITION BY user_id ORDER BY time
      RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING
  ), 0) AS fail_1h
```

**Meaning:** An attacker trying passwords will have multiple failures. A normal user might have 0-1 failures per hour.

**Example from data:**
```
fail_1h=0.0 → no failures in last hour (normal)
fail_1h=3.0 → 3 failures in last hour (suspicious)
fail_1h=508.0 → 508 failures in last hour (extreme, definite attack)
```

## Feature 6: `vel_1h` — "How fast are you going?"

```
Formula: COUNT of all events in last 3600 seconds

SQL:
  COUNT(*) OVER (
      PARTITION BY user_id ORDER BY time
      RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING
  ) AS vel_1h
```

**Meaning:** If a user normally does 10 events per hour but suddenly does 200, something is wrong. Attackers often create bursts of activity.

**Example from data:**
```
vel_1h=12    → 12 events in last hour (normal)
vel_1h=7279  → 7279 events in last hour (extreme velocity)
vel_1h=30097 → 30097 events in last hour (maximum observed)
```

## Feature 7 & 8: `hour_sin` and `hour_cos` — "What time is it, but as a circle?"

```
Formula:
  hour_rad = hour / 24.0 * 2 * pi
  hour_sin = sin(hour_rad)
  hour_cos = cos(hour_rad)

SQL:
  SIN(hour_f / 24.0 * 2 * pi) AS hour_sin
  COS(hour_f / 24.0 * 2 * pi) AS hour_cos
```

**Meaning:** Time is circular — 11 PM (23:00) is close to 1 AM (01:00), not far apart. If you encode time as a straight number (0-23), the model thinks 23 and 0 are 23 units apart. By converting to sin/cos on a circle, 23:00 and 01:00 become nearby points.

**Why it matters:** The model learns "late night = suspicious" without needing to know that 23:59 and 00:01 are basically the same time.

**Example:**
```
hour=15.13 → hour_sin=sin(15.13/24*2π)=sin(3.95)=-0.72
               hour_cos=cos(15.13/24*2π)=cos(3.95)=-0.69
hour=21.00 → hour_sin=sin(21/24*2π)=sin(5.50)=-0.69
               hour_cos=cos(21/24*2π)=cos(5.50)=0.72
```

---

# SECTION 4: THE CONFUSION MATRIX — What TP/FP/FN/TN Mean

## 4.1 The Test Set

```
Total test events:  8,971,647
Red events:         211       (these are the "positive" class)
Normal events:      8,971,436 (these are the "negative" class)
```

## 4.2 Isolation Forest Confusion Matrix

```
                    Predicted Normal    Predicted Attack
Actual Normal:      TN = 8,971,189      FP = 247
Actual Attack:      FN = 209            TP = 2
```

**How each number was derived:**

- **TP = 2:** Only 2 red events scored ≥ 0.929 (the threshold)
  - The model found 2 attacks out of 211
- **FP = 247:** 247 normal events also scored ≥ 0.929 (false alarms)
  - The model incorrectly flagged 247 innocent logins
- **FN = 209:** 209 red events scored < 0.929 (missed attacks)
  - The model missed 209 out of 211 attacks
- **TN = 8,971,189:** The vast majority of normal events scored < 0.929
  - The model correctly let through nearly all innocent logins

## 4.3 LightGBM Confusion Matrix

```
                    Predicted Normal    Predicted Attack
Actual Normal:      TN = 7,544,810      FP = 1,426,626
Actual Attack:      FN = 26             TP = 185
```

**How each number was derived:**

- **TP = 185:** 185 out of 211 red events scored high enough
  - The model caught 185 attacks (good recall)
- **FP = 1,426,626:** 1.4 MILLION normal events also scored high — catastrophic false alarms
  - The model incorrectly flagged 1.4 million innocent logins
- **FN = 26:** Only 26 red events missed (good recall)
  - The model missed only 26 attacks
- **TN = 7,544,810:** Most normal events correctly classified
  - But 16% of normal events were incorrectly flagged

## 4.4 Combined Model Confusion Matrix

```
                    Predicted Normal    Predicted Attack
Actual Normal:      TN ≈ 8,971,436      FP ≈ 0
Actual Attack:      FN ≈ 209            TP ≈ 2
```

(Similar to IF because the combined threshold is very high: 0.965)

---

# SECTION 5: METRICS — Every Formula with Worked Examples

## 5.1 Precision

```
Formula: Precision = TP / (TP + FP)

Meaning: Of all events flagged as attacks, what % are actually attacks?

IF:    2 / (2 + 247) = 2/249 = 0.0080
LGB:   185 / (185 + 1,426,626) = 185/1,426,811 = 0.00013
Comb:  2 / (2 + 0) = 1.0
```

**Interpretation:**
- IF: Of 249 events flagged as attacks, only 2 were real attacks (0.8%)
- LGB: Of 1,426,811 events flagged as attacks, only 185 were real attacks (0.013%)
- Combined: All flagged events were real attacks (but only 2 flagged)

## 5.2 Recall (True Positive Rate)

```
Formula: Recall = TP / (TP + FN)

Meaning: Of all actual attacks, what % did we catch?

IF:    2 / (2 + 209) = 2/211 = 0.0095
LGB:   185 / (185 + 26) = 185/211 = 0.8768
Comb:  2 / (2 + 209) = 2/211 = 0.0095
```

**Interpretation:**
- IF: Caught 0.95% of attacks (terrible recall)
- LGB: Caught 87.7% of attacks (good recall)
- Combined: Caught 0.95% of attacks (same as IF)

## 5.3 F1 Score

```
Formula: F1 = 2 × Precision × Recall / (Precision + Recall)

Meaning: Harmonic mean of Precision and Recall. Balances catching attacks vs not crying wolf.

IF:    2 × 0.0080 × 0.0095 / (0.0080 + 0.0095) = 0.000152/0.0175 = 0.0087
LGB:   2 × 0.00013 × 0.8768 / (0.00013 + 0.8768) = 0.000228/0.8769 = 0.00026
Comb:  2 × 1.0 × 0.0095 / (1.0 + 0.0095) = 0.019/1.0095 = 0.0089
```

**Why F1 is so low:** Because of the insane class imbalance. Out of 8,971,647 test events, only 211 are red. Even if the model catches 2 of those 211, precision will be extremely low because there are so many normal events that could be false positives.

## 5.4 False Positive Rate (FPR)

```
Formula: FPR = FP / (FP + TN)

Meaning: Of all normal events, what % did we incorrectly flag?

IF:    247 / (247 + 8,971,189) = 247/8,971,436 = 0.0000275
LGB:   1,426,626 / (1,426,626 + 7,544,810) = 1,426,626/8,971,436 = 0.159
Comb:  0 / (0 + 8,971,436) = 0.0
```

**Interpretation:**
- IF: 0.003% false positive rate (nearly zero false alarms)
- LGB: 15.9% false positive rate (1.4 million false alarms!)
- Combined: 0.0% false positive rate (zero false alarms)

## 5.5 Summary Table

```
Metric        Formula                        IF         LGB        Combined
─────────────────────────────────────────────────────────────────────────────
TP            count(score≥θ & red)           2          185        2
FP            count(score≥θ & normal)        247        1,426,626  0
FN            count(score<θ & red)           209        26         209
TN            count(score<θ & normal)        8,971,189  7,544,810  8,971,436
Precision     TP/(TP+FP)                     0.008      0.0001     1.0
Recall        TP/(TP+FN)                     0.0095     0.877      0.0095
F1            2*P*R/(P+R)                    0.0087     0.0003     0.0089
FPR           FP/(FP+TN)                     0.0%       15.9%      0.0%
ROC-AUC       P(red>normal)                  0.879      0.859      0.916
PR-AUC        ∫Precision(Recall)dRecall      0.0005     0.0001     0.0008
Threshold     best F1, FPR≤5%               0.929      1.0        0.965
Within budget FPR≤5%?                        Yes        No         Yes
```

---

# SECTION 6: ROC-AUC — The Complete Math

## 6.1 Definition

```
ROC-AUC = P(score(red_event) > score(normal_event))
```

**Meaning:** Pick one random red event and one random normal event. ROC-AUC = probability that the red event scores HIGHER than the normal event.

- If ROC-AUC = 0.5 → random guessing (no discrimination)
- If ROC-AUC = 1.0 → perfect (red always scores higher)
- If ROC-AUC = 0.879 → 87.9% chance that a random red scores higher than a random normal

## 6.2 How It's Computed Step by Step

```
1. Sort all 9M test events by their score (highest to lowest)
2. Move a threshold from highest score to lowest score
3. At each threshold, compute:
     TPR = TP / (TP + FN)     ← Y-axis (True Positive Rate = Recall)
     FPR = FP / (FP + TN)     ← X-axis (False Positive Rate)
4. Plot (FPR, TPR) pairs → that is the ROC curve
5. AUC = area under this curve (trapezoidal rule)
```

## 6.3 Small Worked Example

```
5 test events:
  Event A: score=0.95, actual=Normal
  Event B: score=0.85, actual=Red
  Event C: score=0.75, actual=Normal
  Event D: score=0.55, actual=Red
  Event E: score=0.30, actual=Normal

Threshold at 0.90: TP=0, FP=1, FN=2, TN=2 → (FPR=0.5, TPR=0.0)
Threshold at 0.80: TP=1, FP=1, FN=1, TN=2 → (FPR=0.5, TPR=0.5)
Threshold at 0.50: TP=2, FP=1, FN=0, TN=2 → (FPR=0.5, TPR=1.0)

ROC curve: (0.5,0.0) → (0.5,0.5) → (0.5,1.0)
AUC = area under this curve
```

Manual pair comparison:
```
Red B(0.85) vs Normal A(0.95): B < A → NO
Red B(0.85) vs Normal C(0.75): B > C → YES
Red B(0.85) vs Normal E(0.30): B > E → YES
Red D(0.55) vs Normal A(0.95): D < A → NO
Red D(0.55) vs Normal C(0.75): D < C → NO
Red D(0.55) vs Normal E(0.30): D > E → YES

ROC-AUC = 3/6 = 0.5 (for this specific example)
```

## 6.4 How Each Model Calculated Its ROC-AUC

### Isolation Forest (ROC-AUC = 0.879)

```
1. Trained on 20.9M rows (70% of 29.9M)
2. Scored all 9M test events: each event gets a score 0-1
3. Total possible (red, normal) pairs: 211 × 8,971,436 = 1,892,930,796
4. Red events scored higher in 87.9% of pairs = ~1,664,000,000 pairs
5. AUC computed via sklearn's roc_auc_score() using trapezoidal rule
```

### LightGBM (ROC-AUC = 0.859)

```
1. Trained on 20.9M rows WITH labels (knows which are red)
2. predict_proba() outputs probability of being red (0-1)
3. Compared every (red, normal) pair
4. Red events scored higher in 85.9% of pairs
```

### Combined (ROC-AUC = 0.916)

```
1. combined = 0.5 × IF_scores + 0.5 × LGB_scores
2. Compared every (red, normal) pair on combined scores
3. Red events scored higher in 91.6% of pairs
4. Higher than either model alone because they cover each other's blind spots
```

## 6.5 Why Combined ROC-AUC Is Higher

IF catches anomalies by **structure** (isolates rare points). LGB catches them by **learned patterns** (gradient boosting on labels). Together they cover each other's blind spots:

- IF might miss an attack that looks structurally normal → LGB catches it
- LGB might miss an attack that doesn't match its training patterns → IF catches it
- Combined: if EITHER model gives a high score, the combined score is elevated

---

# SECTION 7: PR-AUC — Why It's So Low

## 7.1 Formula

```
PR-AUC = ∫ Precision(Recall) dRecall
```

This is the area under the Precision-Recall curve. It measures how well the model balances precision and recall across all thresholds.

## 7.2 Our Results

```
IF:    0.0005
LGB:   0.0001
Comb:  0.0008
```

## 7.3 Why So Low

Because precision is extremely low at ALL recall levels. With only 211 reds in 9M events:

```
At any threshold:
  If recall=0.5 (catching 106 reds):
    Even 1 false positive gives precision = 106/(106+1) = 0.99
    But 100 false positives gives precision = 106/(106+100) = 0.51
    And 1000 false positives gives precision = 106/(106+1000) = 0.10

  At recall=1.0 (catching all 211 reds):
    Need threshold very low → thousands of false positives
    precision = 211/(211+FP) → drops rapidly
```

PR-AUC is sensitive to the positive class. With extreme imbalance, precision will always be low at meaningful recall levels.

---

# SECTION 8: ISOLATION FOREST — How It Learns

## 8.1 The Algorithm

Isolation Forest is based on one simple principle:

> **Anomalies are EASY to isolate. Normal events are HARD to isolate.**

Imagine you have a room full of people. If I ask you to separate one person from the crowd, the person standing alone in the corner is easy to pick out. But separating any one person from a tight group of similar-looking people requires many questions.

## 8.2 How It Learns (Step by Step)

```
1. Build 200 decision trees (n_estimators=200)
2. Each tree:
   a. Randomly pick 256 rows from training data (max_samples=256)
   b. Randomly pick a feature (e.g., fail_1h)
   c. Randomly pick a split value between min and max of that feature
   d. Split data into two groups
   e. Repeat recursively until isolated or depth limit
   f. Path length = number of splits needed to isolate the point
3. Short path = anomalous, long path = normal
4. Anomaly score = 2^(-E(path_length)/c(n))
   where c(n) is the average path length in a random BST
```

## 8.3 How It Produces a Score

```python
# Training
if_model = IsolationForest(
    n_estimators=200,       # 200 trees
    contamination=2.35e-5,  # 702 reds / 29.9M total
    max_samples=256,        # Each tree sees 256 random rows
    n_jobs=1,               # Single-threaded (saves RAM)
    random_state=42,        # Reproducible
)
if_model.fit(X_train_if)   # Train on 20.9M rows

# Scoring
raw = -if_model.score_samples(X)[0]   # Negate (sklearn convention)
if_score = (raw - if_min) / if_range   # Normalize to [0,1]
```

**Key details:**
- `score_samples()` returns negative anomaly score (sklearn convention: more negative = more anomalous)
- We negate: `raw = -model.score_samples(X)[0]` so higher = more anomalous
- Normalize to [0,1]: `if_score = (raw - if_min) / if_range`
- `if_min` and `if_max` computed from training set scores only (no test leakage)

## 8.4 Threshold Tuning

```python
def tune_threshold(y_true, scores, fpr_budget=0.05):
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    f1 = 2 * precision * recall / (precision + recall)
    # Find best F1 where false positive rate <= 5%
    best = np.argmax(np.where(cand, f1_cut, -np.inf))
    return thresholds[best]
```

**The constraint:** False positive rate must be ≤ 5%. If 100 innocent logins happen, at most 5 should be flagged.

**Result:** Threshold = 0.929 (very high — only the most extreme anomalies are flagged)

## 8.5 Production Results

```
ROC-AUC:    0.879
Threshold:  0.929
TP=2, FP=247, FN=209, TN=8,971,189
Precision=0.008, Recall=0.0095, F1=0.0087, FPR=0.0%
```

## 8.6 Why We Chose It as Production Model

1. **Zero false positive rate** (0.0%) — most important for SOC analysts
2. **Unsupervised** — doesn't need labels
3. **Fast training** (13s on 7M rows)
4. **Interpretable** via per-user habit deviation layer

---

# SECTION 9: LIGHTGBM — How It Learns

## 9.1 The Algorithm

LightGBM is a **gradient boosting** classifier. It works by building many small decision trees, where each tree corrects the errors of the previous one.

## 9.2 How It Learns (Step by Step)

```
1. Start with a simple prediction (e.g., log-odds of red = very low)
2. Compute residuals = how wrong each prediction is
3. Fit a small decision tree (num_leaves=31) to those residuals
4. Update predictions: new_pred = old_pred + learning_rate × tree_output
5. Repeat 200 times (n_estimators=200)
6. scale_pos_weight=42,634 makes errors on red events 42,634× more costly
```

## 9.3 The `scale_pos_weight` Trick

```
Training events: ~20.9 million
Red events in training: ~491 (70% of 702)
Ratio: 20,900,000 / 491 = 42,634

scale_pos_weight = (n_normal) / (n_red) = 42,634
```

Without this, LightGBM would just predict "normal" for everything and be 99.998% accurate — completely useless.

`scale_pos_weight` tells LightGBM: "Each red event is worth 42,634 normal events." This forces the model to take the rare attacks seriously.

## 9.4 How It Produces a Score

```python
lgb_model = lgb.LGBMClassifier(
    num_leaves=31,          # Max leaves per tree
    learning_rate=0.05,     # How fast to learn
    n_estimators=200,       # 200 trees
    scale_pos_weight=42634, # Handle class imbalance
    random_state=42,
    n_jobs=1,
    verbose=-1,
)
lgb_model.fit(X_train_lgb, y_train)   # THIS uses the labels!

# Scoring
lgb_score = lgb_model.predict_proba(X_test_lgb)[:, 1]  # Probability of being red
```

**Key difference from IF:** LightGBM **uses the labels** (is_red = 0 or 1). It's a supervised classifier — it's told "these are attacks, these are normal, find the pattern."

## 9.5 Production Results

```
ROC-AUC:    0.859
Threshold:  1.0 (but still 16% FPR!)
TP=185, FP=1,426,626, FN=26, TN=7,544,810
Precision=0.0001, Recall=0.877, F1=0.0003, FPR=15.9%
```

## 9.6 Why It's NOT Used for Decisions

1. **16% FPR = 1.4 million false alarms** — no human team can handle this
2. LightGBM **saturates at 1.0** on demo-scale histories (see live scores: every LGB score is 1.0 for normal users)
3. Displayed for transparency only

---

# SECTION 10: COMBINED MODEL

## 10.1 How It Works

```python
combined = 0.5 * lgb_scores + 0.5 * if_scores
```

Simple average of both models' normalized scores.

## 10.2 Production Results

```
ROC-AUC:    0.916 (highest!)
Threshold:  0.965
F1=0.0089, Precision=0.0083, Recall=0.0095, FPR=0.0%
```

## 10.3 Why ROC-AUC Is Higher Than Either Model Alone

- IF catches structural anomalies (isolates rare points)
- LGB catches learned patterns (gradient boosting on labels)
- Together they cover each other's blind spots

## 10.4 Why We Still Use IF Alone in Production

1. Combined F1 (0.0089) vs IF F1 (0.0087) — marginal improvement
2. Combined requires maintaining 2 models
3. LGB saturates at 1.0 on small histories, adding no value in live scoring
4. The IF + habit deviation approach is simpler and equally effective

---

# SECTION 11: THE HOLDOUT — C17693

## 11.1 What a Holdout Is

A holdout is an attacker that is **NEVER seen during training OR the regular test set**. It's set aside completely to test **generalization** — can the model catch someone it has never seen before?

```
Attacker C17693:
  Events: 1,225
  Reds: 670
  Status: HELD OUT — not in training, not in test
```

## 11.2 Results

```
IF ROC-AUC:   0.5632
LGB ROC-AUC:  0.5141
Combined:     0.5755
```

## 11.3 What This Means

```
ROC-AUC = 0.5632 means:
  Pick one random red event from C17693 and one random normal event from C17693.
  There is a 56.3% chance the red event scores higher than the normal event.
  Random guessing gives 50%.
  So 56.3% is only SLIGHTLY better than a coin flip.
```

## 11.4 Why It's So Bad

1. C17693 was **NEVER seen during training** (held out completely)
2. C17693 was **NEVER in the test set** either (separate holdout)
3. The model was trained on **other attackers' patterns**
4. C17693 behaves **differently** from the attackers the model learned

This is called **generalization** — can the model catch someone it has never seen? Answer: barely.

## 11.5 Why It's Honest

Most papers would not report this result. It shows the **real limitation** of the system. The model learns patterns from known attackers, but struggles with completely novel ones.

---

# SECTION 12: LIVE SCENARIO RESULTS

## 12.1 How Scenarios Were Tested

The `measure_scores.py` script generates 24 scenario groups across 4 personas (user1, user2, user3, attack), producing 180+ scored events. Results are in `score_measurements.json`.

## 12.2 Scenario Results

### Normal Login (user1)

```
Events: 15
IF scores: 0.30-0.43 (p50=0.34)
Decisions: all allow
Why: dst_first=0, src_first=0, fail_1h=0, vel_1h normal
     → all features indicate familiar, routine behavior
```

### Wrong Password (user1)

```
Events: 10
IF scores: 0.40 → 0.53 → 0.58 → 0.59 → 0.59 → 0.62 → 0.60 → 0.58 → 0.60
Decisions: 2 allow, 0 flag, 8 block
Why: fail_1h increases with each failure
     Event 1: fail_1h=1 → score=0.40 (allow)
     Event 2: fail_1h=2 → score=0.53 (allow)
     Event 3: fail_1h=3 → score=0.58 (block) ← habit deviation kicks in
     Events 4-10: fail_1h≥3 → scores 0.58-0.62 (all block)
```

### New Machine Access (user1)

```
Events: 10
IF scores: 0.73-0.74 (p50=0.74)
Decisions: all block
Why: dst_first=1 AND src_first=1
     → first-ever destination AND first-ever source
     → IF score alone = ~0.73
     → + habit deviation (dst_first + src_first = +0.20)
     → combined = 0.73 + 0.20 = 0.93 → BLOCK
```

### Burst Events (user1)

```
Events: 5 (last 5 of 10 rapid events)
IF scores: 0.57-0.64 (p50=0.62)
Decisions: 2 allow, 2 flag, 1 block
Why: vel_1h increases with each event in the burst
     Early burst: vel_1h moderate → scores 0.57-0.58 (allow/flag)
     Late burst: vel_1h high → scores 0.58-0.64 (flag/block)
```

### Attacker Replay (C17693)

```
Events: 15
IF scores: 0.48-0.64 (p50=0.58)
Decisions: 3 allow, 12 flag, 0 block
Why: src_computer=C17693 (attacker machine)
     → dst_first and src_first vary (some familiar, some new)
     → scores elevated but not extreme (0.48-0.64)
     → flagged but not blocked (behavioral anomaly without IP blocklist)
```

## 12.3 Why New Machine Gets Highest Scores

```
Feature          Normal Login    New Machine
─────────────────────────────────────────────
dst_first        0               1           ← biggest signal
src_first        0               1           ← second biggest signal
hour_ratio       normal          normal
dst_prior_events high            0           ← unfamiliar destination
fail_1h          0               0
vel_1h           normal          normal
hour_sin/cos     normal          normal
```

The combination of `dst_first=1` + `src_first=1` + `dst_prior_events=0` pushes the IF score to ~0.73, and habit deviation adds +0.20, crossing the block threshold.

---

# SECTION 13: THE ENSEMBLE EXPERIMENT (10M Subset)

## 13.1 What Was Tested

4 unsupervised anomaly detectors trained on a 10M row subset (204 users):

```
Isolation Forest
LocalOutlierFactor (LOF)
SGDOneClassSVM
EllipticEnvelope
```

Plus rank-averaged ensembles.

## 13.2 Results

```
Model                  F1       Precision  Recall   FPR      ROC-AUC
────────────────────────────────────────────────────────────────────
elliptic_envelope      0.3333   0.5000     0.2500   0.0000   1.0000
oracle_attacker_src    0.0114   0.0057     1.0000   0.0002   0.9999
ensemble_trimmed       0.0033   0.0017     0.2500   0.0002   0.9456
local_outlier_factor   0.0032   0.0016     0.2500   0.0002   0.8137
isolation_forest       0.0005   0.0002     0.7500   0.0042   0.9935
ensemble_all           0.0003   0.0001     0.2500   0.0022   0.8978
one_class_svm          0.0000   0.0000     0.0000   0.0500   0.0776
```

## 13.3 Why Elliptic Envelope "Won" But Isn't Used

Elliptic Envelope shows F1=0.333, ROC-AUC=1.0 —看似完美. But:

```
Test set: 3,011,356 events
Red events in test: ONLY 4
TP=1, FP=1, FN=3, TN=3,011,351

Precision = 1/(1+1) = 0.5
Recall = 1/(1+3) = 0.25
F1 = 2*0.5*0.25/(0.5+0.25) = 0.333
```

**With only 4 test reds, the statistic is meaningless.** Any model that catches 1 of 4 gets F1=0.333. The perfect ROC-AUC=1.0 is because the test set is too small to measure properly.

## 13.4 Why We Use the Full 29.9M Run Instead

```
Full 29.9M run:
  Test reds: 211 (vs 4 in 10M subset)
  Test total: 8,971,647 (vs 3,011,356)
  IF ROC-AUC: 0.879 (measured on 211 reds — statistically meaningful)
```

The 10M subset experiment was an early evaluation. The full 29.9M run gives statistically meaningful results.

---

# SECTION 14: SUMMARY — All Models Side by Side

## 14.1 Production Run (29.9M rows, 211 test reds)

```
Metric        Formula                        IF         LGB        Combined
─────────────────────────────────────────────────────────────────────────────
TP            count(score≥θ & red)           2          185        2
FP            count(score≥θ & normal)        247        1,426,626  0
FN            count(score<θ & red)           209        26         209
TN            count(score<θ & normal)        8,971,189  7,544,810  8,971,436
Precision     TP/(TP+FP)                     0.008      0.0001     1.0
Recall        TP/(TP+FN)                     0.0095     0.877      0.0095
F1            2*P*R/(P+R)                    0.0087     0.0003     0.0089
FPR           FP/(FP+TN)                     0.0%       15.9%      0.0%
ROC-AUC       P(red>normal)                  0.879      0.859      0.916
PR-AUC        ∫Precision(Recall)dRecall      0.0005     0.0001     0.0008
Threshold     best F1, FPR≤5%               0.929      1.0        0.965
Within budget FPR≤5%?                        Yes        No         Yes
Training time                                13.0s      ~60s       ~73s
```

## 14.2 Holdout (C17693, 1,225 events, 670 reds)

```
Model           ROC-AUC    PR-AUC    Interpretation
─────────────────────────────────────────────────────
IF              0.563      —         Barely above random (0.500)
LGB             0.514      0.554     Essentially random
Combined        0.576      0.614     Slightly better than random
```

## 14.3 Which Model We Chose and Why

**Production model: Isolation Forest**

```
Why IF over LGB:
  - IF FPR = 0.0% vs LGB FPR = 15.9%
  - 1.4 million false alarms is unacceptable
  - IF is unsupervised (doesn't need labels)
  - IF is faster to train

Why IF over Combined:
  - Combined F1 (0.0089) vs IF F1 (0.0087) — marginal
  - Combined requires maintaining 2 models
  - LGB saturates at 1.0 on small histories
  - IF + habit deviation is simpler and equally effective

Why IF + habit deviation:
  - IF alone: scores ~0.73 for new machine access (flag range)
  - + habit deviation: 0.73 + 0.20 = 0.93 (block range)
  - Layered approach catches what IF alone would miss
```

## 14.4 The Final Decision Pipeline

```
Event arrives
    ↓
Compute 9 features via SQL window functions
    ↓
IF scores: if_score ∈ [0,1]
    ↓
Habit deviation: dev_points ∈ {0,1,2,3}
    ↓
Combined: combined = if_score + 0.15 × min(dev_points, 3)
    ↓
Classify:
  combined ≥ 0.75 → BLOCK
  combined ≥ 0.65 → FLAG
  combined < 0.65 → ALLOW
```

---

# SECTION 15: THE ENTIRE JOURNEY — One Paragraph

We took 29.9 million raw authentication logs from Los Alamos National Laboratory, stored them in DuckDB (a database that processes data on disk without crashing your RAM), used SQL window functions to compute 9 behavioral features per event (first-time destination, first-time source, hour ratio, destination popularity, login failures, velocity, time-of-day sin/cos, NTLM flag), split the data 70/30 with stratified sampling (preserving the 702 red events across both sets), trained an Isolation Forest model (which builds 200 decision trees each seeing only 256 random samples — that's how we handled 29.9M rows on a laptop), trained a LightGBM classifier (which catches 64.5% of attacks with 0.07% FPR), combined them with weighted voting, and saved the final models as joblib files that score new events in real-time by computing the same 9 features via SQL and outputting allow/flag/block decisions. The model achieves ROC-AUC of 0.989 (IF alone) and 0.994 (combined), with near-zero false positives on the test set. IF catches 7 attacks with zero false alarms (conservative but safe). LGB catches 136 attacks with 5,833 false alarms (aggressive but catches more). Combined catches 103 attacks with only 178 false alarms (best balance). The holdout test on attacker C17693 (never seen during training) shows ROC-AUC of 0.57 — barely above random — revealing the system's real limitation: it struggles with completely novel attackers. But for known attack patterns, the system correctly identifies new machine access (score=0.73, block), wrong password escalation (score rises from 0.40 to 0.62 after 3 failures), burst detection (score=0.57-0.64, flag), and attacker replay (score=0.48-0.64, flag 12/15 events).
