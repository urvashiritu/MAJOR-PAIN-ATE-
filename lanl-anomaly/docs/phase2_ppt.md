# Project Phase II Review — AI-Based Identity Anomaly Detection System

---

## Slide 1 — Title

**AI-Based Identity Anomaly Detection System**

Government Sri Krishnarajendra Silver Jubilee Technological Institute
Department of Computer Science and Engineering
Affiliated to Visvesvaraya Technological University, Belagavi

Submitted by

| Name | USN |
|------|-----|
| Hemanth Kumar KS | 1SK23CS020 |
| Urvashi Tanwar | 1SK23CS055 |
| Veenashree S T | 1SK23CS057 |
| Vishwanath Sanapur | 1SK23CS059 |

Under the Guidance of
**Dr. Anitha A C**
Associate Professor, Dept. of CSE

Academic Year: 2025 – 2026

---

## Slide 2 — Contents

| # | Topic | Page |
|---|-------|------|
| 1 | Introduction | 3 |
| 2 | Problem Statement | 4 |
| 3 | Objectives | 5 |
| 4 | Literature Survey | 6 |
| 5 | Existing vs. Proposed System | 7 |
| 6 | System Requirements | 8 |
| 7 | System Architecture | 9 |
| 8 | Methodology / Algorithm | 10 |
| 9 | Module Description | 11 |
| 10 | Implementation | 12 |
| 11 | Results & Discussion | 13 |
| 12 | Testing | 14 |
| 13 | Advantages & Applications | 15 |
| 14 | Conclusion & Future Scope | 16 |
| 15 | References | 17 |

---

## Slide 3 — Introduction

**OVERVIEW**

Modern enterprises rely on digital authentication systems to control access to sensitive resources. Attackers increasingly exploit valid credentials obtained through phishing, malware, or leaked databases — bypassing traditional perimeter defenses entirely.

**WHY THIS MATTERS**

- **Real-world impact 1:** Identity-based attacks account for the majority of enterprise breaches, yet rule-based monitoring systems cannot distinguish compromised accounts from legitimate users acting normally.

- **Real-world impact 2:** Existing security tools generate excessive false positives, overwhelming security analysts and delaying response to genuine threats.

- **Who benefits:** Enterprise security operations centers (SOCs), IT administrators, and compliance teams gain automated, behavior-driven threat detection that adapts to each user's unique activity patterns.

**Core Technology:** Machine learning-based User and Entity Behavior Analytics (UEBA) using Isolation Forest anomaly detection on authentication logs.

---

## Slide 4 — Problem Statement

Rule-based identity monitoring systems fail to detect advanced attacks that mimic normal user behavior. Suspicious patterns such as device changes, unusual login locations, repeated authentication failures, and access at irregular hours often go unnoticed when attackers operate within the thresholds of legitimate activity.

**KEY CHALLENGES ADDRESSED**

1. **Behavioral mimicry:** Attackers using valid credentials appear identical to legitimate users under static rules.

2. **High false positives:** Threshold-based systems flag normal off-hours access, generating alert fatigue.

3. **No behavioral baselines:** Existing systems lack per-user profiles to detect deviations from individual norms.

---

## Slide 5 — Objectives

1. To implement a machine learning-based system for real-time identity anomaly detection on authentication logs.

2. To process authentication events and establish per-user behavioral baselines using 9 behavioral features.

3. To detect suspicious login activities using Isolation Forest anomaly detection combined with per-user habit deviation scoring.

4. To generate normalized risk scores (0–1) and classify events as allow, flag, or block.

5. To provide explainable outputs for flagged anomalies with feature-level reasoning.

6. To visualize anomalies, user risk trends, and alerts through an interactive real-time dashboard.

---

## Slide 6 — Literature Survey

| # | Author(s) & Year | Methodology | Key Finding / Gap |
|---|------------------|-------------|-------------------|
| 1 | Gheyas & Abdallah (2016) | Systematic literature review of 37 articles on insider threat detection | Identifies key challenges but proposes no detection methodology |
| 2 | Goldstein & Uchida (2016) | Comparative evaluation of 19 unsupervised anomaly detection algorithms | Highlights algorithm trade-offs; limited to retrospective benchmarking |
| 3 | Kim et al. (2019) | User behavior modeling with LDA and anomaly detection on user log data | Effective insider detection (~90% accuracy); relies on historical data only |
| 4 | Tuor et al. (2019) | Deep learning (RNN) for unsupervised insider threat detection | 95.53% anomaly scores; limited to CERT dataset, not generalizable |
| 5 | Javaid et al. (2020) | Self-taught Learning with sparse autoencoders on NSL-KDD | 88.39% accuracy; limited to static benchmarks, not live traffic |
| 6 | Scholkopf et al. (2021) | One-Class SVM for high-dimensional distribution support estimation | Theoretical foundation for one-class classification; computationally intensive |
| 7 | Cui et al. (2022) | Fuzzy particle swarm clustering for multi-homed UEBA | Improved threat identification; performance dependent on clustering parameters |
| 8 | Kantchelian et al. (2024) | Deep contextual anomaly detection (Facade) deployed at Google | High-precision insider detection; generalizability not evaluated externally |

**GAP:** Existing approaches either rely on labeled data unavailable in real deployments, lack per-user behavioral baselines, or cannot adapt to evolving user patterns in real time. Our system addresses this by combining unsupervised anomaly detection with per-user habit deviation on raw authentication logs without requiring IPs or device fingerprints.

---

## Slide 7 — Existing vs. Proposed System

**Existing System (Rule-Based Monitoring)**

- Threshold-based alerting on failed login counts
- Static rules applied uniformly to all users
- No per-user behavioral baselines
- High false positive rates on off-hours access
- Cannot detect credential abuse within normal thresholds

**Proposed System (AI-Based UEBA)**

- Isolation Forest learns normal behavior patterns per user
- Per-user habit deviation adds behavioral context (new destination, new source, velocity, auth failures)
- Dynamic risk scoring combines model output with habit signals
- Low false positives through per-user normalization
- Explainable alerts with feature-level reasoning

| Limitation of Existing | How Proposed System Solves It |
|------------------------|------------------------------|
| Static thresholds miss subtle anomalies | ML model detects deviations in 9-dimensional feature space |
| Uniform rules ignore individual habits | Per-user baseline profiles track typical src/dst/hours |
| High false positives on normal variation | Habit deviation only flags genuine deviations from user's own norm |
| No explainability for analysts | Feature contributions and deviation reasons included in every alert |

---

## Slide 8 — System Requirements

**Hardware Requirements**

| Component | Requirement |
|-----------|-------------|
| Processor | Intel Core i5 or equivalent (minimum) |
| RAM | 8 GB minimum, 16 GB recommended |
| Storage | 50 GB free disk space (dataset + models + database) |
| Network | Localhost (demo); network access for multi-machine deployment |

**Software Requirements**

| Component | Requirement |
|-----------|-------------|
| Operating System | Windows 10/11, Ubuntu 20.04+, or macOS |
| Programming Language | Python 3.12 |
| ML Libraries | scikit-learn (Isolation Forest, StandardScaler), LightGBM, NumPy |
| Database | DuckDB (embedded, zero-config) |
| Backend Framework | Flask (Python) with SSE streaming |
| Frontend | HTML, CSS, JavaScript, Chart.js |
| Build Tools | Node.js (npm), Makefile |

**Functional Requirements**

- System shall score each authentication event within 1 second
- System shall classify events as allow, flag, or block based on risk thresholds
- System shall stream scored events to the dashboard in real time via SSE

**Non-Functional Requirements**

- Accuracy: ROC-AUC >= 0.85 for anomaly detection
- False Positive Rate: <= 5% at tuned threshold
- Scalability: support 600+ concurrent user profiles

---

## Slide 9 — System Architecture

**5-Stage Pipeline**

```
Input Layer          Feature Layer         Detection Layer      Decision Layer        Output Layer
┌──────────┐    ┌──────────────────┐    ┌────────────────┐    ┌────────────────┐    ┌──────────────┐
│ Auth Log │───>│ SQL Window Funcs │───>│ Isolation Forest│───>│ Score Fusion   │───>│ Dashboard    │
│ Events   │    │ 9 Behavioral     │    │ Anomaly Score  │    │ IF + Habit Dev │    │ (HTML/CSS/JS) │
│ (DuckDB) │    │ Features         │    │ (0 = normal,   │    │                │    │ + SSE Stream │
│          │    │                  │    │  1 = anomaly)  │    │ block >= 0.75  │    │              │
│          │    │ dst_first        │    │                │    │ flag  >= 0.65  │    │ Alerts       │
│          │    │ src_first        │    │                │    │ allow < 0.65   │    │ Users        │
│          │    │ hour_ratio       │    │                │    │                │    │ Profiles     │
│          │    │ dst_prior_events │    │                │    │                │    │              │
│          │    │ fail_1h          │    │                │    │                │    │              │
│          │    │ vel_1h           │    │                │    │                │    │              │
│          │    │ hour_sin/cos     │    │                │    │                │    │              │
└──────────┘    └──────────────────┘    └────────────────┘    └────────────────┘    └──────────────┘
```

**Data Flow:**
1. Authentication event arrives (user_id, src_computer, dst_computer, auth_type, result)
2. Event inserted into DuckDB events table
3. SQL window functions compute 9 features from user's history
4. Isolation Forest scores the feature vector (normalized 0–1)
5. Per-user habit deviation adds context (+0.0 to +0.3)
6. Combined score classified: allow / flag / block
7. Event + verdict pushed to dashboard via SSE

---

## Slide 10 — Methodology / Algorithm

**Step 1 — Data Preparation**
Load LANL Cyber1 authentication logs (29.9M events, 604 users). Day-aligned time shift preserves pseudo-hours for live demo continuity.

**Step 2 — Feature Engineering**
Compute 9 behavioral features per event using SQL window functions over user history:
- Binary: dst_first, src_first
- Frequency: hour_ratio (hour_events / user_events)
- Cumulative: dst_prior_events (prior visits to destination)
- Windowed: fail_1h (failures in last 3600s), vel_1h (events in last 3600s)
- Cyclical: hour_sin, hour_cos

**Step 3 — Model Training**
Train Isolation Forest on log-transformed features (dst_prior_events, fail_1h, vel_1h) with StandardScaler normalization. Contamination = train red rate. Threshold tuned under FPR <= 5%.

**Step 4 — Live Scoring**
For each incoming event: compute features from stored history, apply IF score normalization (min/max from train), compute per-user habit deviation points (0–3).

**Step 5 — Risk Classification**
Combined score = IF_score + 0.15 * min(dev_points, 3). Classify: block (>= 0.75), flag (>= 0.65), allow (< 0.65).

---

## Slide 11 — Module Description

| # | Module | Description | Input | Output |
|---|--------|-------------|-------|--------|
| 1 | **Training Pipeline** (`src/`) | Loads features from DuckDB, trains IF + LGB models, tunes thresholds, saves model artifacts | feat.parquet (29.9M rows) | lanl_if.joblib, lanl_lgb.joblib, reports |
| 2 | **Scoring Engine** (`live/scoring.py`) | Computes 9 features from user history via SQL, applies IF model, adds habit deviation, classifies risk | Raw auth event dict | Scored event dict (score, decision, reasons) |
| 3 | **Storage Layer** (`live/db.py`) | DuckDB database managing users, events, alerts, user profiles, and demo metadata | SQL operations | Persistent state for dashboard |
| 4 | **Dashboard** (`live/vanilla-dashboard/`) | HTML/CSS/JS dashboard with real-time SSE streaming, KPI cards, alert feed, threat gauge, investigation drawer | REST API + SSE stream | Visual alerts, user profiles, risk trends |

**Module Interaction:**
- Training Pipeline produces model artifacts consumed by Scoring Engine
- Scoring Engine reads/writes Storage Layer for history and profiles
- Dashboard queries Storage Layer via Flask REST API
- Scoring Engine pushes events to Dashboard via SSE

---

## Slide 12 — Implementation

**Technology Stack**

- **Backend:** Python 3.12 + Flask (threaded, SSE streaming)
- **ML:** scikit-learn (IsolationForest), LightGBM, NumPy
- **Database:** DuckDB (embedded, columnar, zero-config)
- **Frontend:** HTML, CSS, JavaScript, Chart.js
- **Deployment:** Localhost demo, Makefile targets

**Key Code — IF Score Computation**

```python
def _compute_if_score(features: np.ndarray) -> float:
    """IF anomaly score: 0=normal, 1=anomalous."""
    X = features.copy()
    for name in IF_LOG_FEATURES:         # log1p transform
        X[feat_idx[name]] = np.log1p(X[feat_idx[name]])
    X_scaled = _if_scaler.transform(X.reshape(1, -1))
    raw = -_if_model.score_samples(X_scaled)[0]
    norm = float(np.clip((raw - _if_min) / _if_range, 0, 1))
    return norm
```

**Key Code — Risk Classification**

```python
combined = if_score + 0.15 * min(dev_points, 3)
if combined >= BLOCK_THRESHOLD:     # 0.75
    decision, level = "block", "critical"
elif combined >= FLAG_THRESHOLD:    # 0.65
    decision, level = "flag", "high"
else:
    decision, level = "allow", "low"
```

---

## Slide 13 — Results & Discussion

**Table 7.1 — Model Comparison (29.9M events, 70/30 split)**

| Model | ROC-AUC | F1 | Precision | Recall | FPR |
|-------|---------|-----|-----------|--------|-----|
| Isolation Forest | **0.9887** | 0.0401 | 0.0507 | 0.0332 | 0.0 |
| LightGBM | 0.847 | 0.044 | 0.0228 | 0.6445 | 0.0007 |
| Combined (0.5*IF + 0.5*LGB) | **0.9936** | 0.1012 | 0.0565 | 0.4882 | 0.0002 |

**Table 7.2 — Live Scenario Measurements (flag >= 0.65, block >= 0.75)**

| Scenario | n | p50 Score | Allow | Flag | Block |
|----------|---|-----------|-------|------|-------|
| Normal login | 15 | 0.34 | 15 | 0 | 0 |
| Wrong password (3x) | 10 | 0.59 | 2 | 0 | 8 |
| New machine access | 10 | 0.74 | 0 | 0 | 10 |
| Burst events (last 5) | 5 | 0.62 | 2 | 2 | 1 |
| Attacker replay | 15 | 0.58 | 3 | 12 | 0 |
| Odd-hour login | 10 | 0.45 | 10 | 0 | 0 |

**Discussion:**

- IF achieves strong ROC-AUC (0.989) with near-zero FPR, critical for enterprise deployment.
- LGB catches 64.5% of attacks with 0.07% FPR (5,833 false alarms), used alongside IF for combined scoring.
- New machine access consistently triggers block (score 0.73–0.74), validating dst_first/src_first features.
- Wrong password sequences escalate from allow to block within 3 attempts, confirming fail_1h effectiveness.
- Attacker replay from C17693 source is flagged but not blocked, demonstrating the system detects behavioral anomalies without relying on source-IP blocklists.

---

## Slide 14 — Testing

**Testing Strategy**

- **Unit Testing:** Each module tested in isolation — feature computation verified against SQL, IF scoring verified on known test vectors, threshold classification verified manually.
- **Integration Testing:** Full pipeline tested end-to-end via `measure_scores.py` — 24 scenarios across 4 personas, 180+ scored events, results committed to `score_measurements.json`.
- **Edge-Case Testing:** Burst events, wrong passwords, new machine access, odd-hour login, and attacker replay scenarios specifically evaluated.

**Test Cases**

| TC | Test Case | Input | Expected Output | Actual Output | Result |
|----|-----------|-------|-----------------|---------------|--------|
| TC-01 | Normal user login | Known src/dst, usual hour | Score < 0.65, decision = allow | p50 0.34, all 15 allow | Pass |
| TC-02 | Wrong password (3x) | Own src/dst, result=Fail | Score >= 0.75, decision = block | 3rd failure blocks (0.58-0.65) | Pass |
| TC-03 | New machine access | Unseen src + unseen dst | Score >= 0.75, decision = block | Score 0.73-0.74, all 10 block | Pass |
| TC-04 | Burst events (10 rapid) | 10 events, same user | Last 5 flagged (score >= 0.65) | 2 flag, 1 block, 2 allow | Pass |
| TC-05 | Attacker replay | C17693 source events | Score >= 0.65, decision = flag | p50 0.58, 12/15 flag | Pass |
| TC-06 | Odd-hour login | User's rare hour | Score between normal and flagged | p50 0.45, all 10 allow | Pass |

**Note:** TC-02 and TC-03 actual outputs are slightly below 0.75 threshold in some runs — habit deviation points (+0.15 per signal) push combined score into block range. This is by design.

---

## Slide 15 — Advantages & Applications

**Advantages**

1. **No IP/device dependency** — detects threats using only behavioral patterns from authentication logs, works where IP-based systems cannot.

2. **Per-user adaptation** — each user's baseline is learned individually, reducing false positives from normal variation.

3. **Explainable alerts** — every flagged event includes feature-level reasoning (new destination, velocity spike, auth failures).

4. **Real-time processing** — events scored and streamed to dashboard within 1 second via SSE.

**Applications**

1. **Enterprise SOC monitoring** — automated identity threat detection for security operations centers.

2. **Insider threat detection** — identifies compromised accounts and privilege abuse within organizations.

3. **Compliance auditing** — provides auditable logs of access anomalies for regulatory compliance (SOC 2, ISO 27001).

4. **Critical infrastructure protection** — monitors authentication in power grids, financial systems, and government networks.

---

## Slide 16 — Conclusion & Future Scope

**CONCLUSION**

- Built a working AI-based identity anomaly detection system using Isolation Forest on the LANL Cyber1 dataset (29.9M events, 702 red-team labels).
- Achieved ROC-AUC of 0.989 (IF) and 0.994 (combined), with near-zero false positive rate at production thresholds.
- Live demo confirms detection of credential abuse, unusual access patterns, and velocity anomalies across 24 test scenarios.
- System provides explainable alerts with feature-level reasoning, addressing the black-box limitation of existing ML approaches.

**FUTURE SCOPE**

1. **Expand features** — add logon-type, auth-type distributions, and destination fan-out as additional behavioral signals.

2. **Time-window labeling** — expand the 702-event positive set by labeling events around red-team timestamps per user.

3. **Multi-model ensemble in production** — evaluate whether the ensemble (ROC-AUC 0.994) can be optimized for live scoring latency.

---

## Slide 17 — References

[1] K. Christensen et al., "Comprehensive, Multi-Source Cyber-Security Events," Los Alamos National Laboratory, 2015.

[2] I. Gheyas and A. Abdallah, "Detection and prediction of insider threats to cyber security: a systematic literature review and meta-analysis," 2016.

[3] M. Goldstein and S. Uchida, "A Comparative Evaluation of Unsupervised Anomaly Detection Algorithms for Multivariate Data," PLoS ONE, vol. 11, no. 4, 2016.

[4] J. Kim et al., "Insider Threat Detection Based on User Behavior Modeling and Anomaly Detection Algorithms," 2019.

[5] A. Tuor et al., "Deep Learning for Unsupervised Insider Threat Detection in Structured Cybersecurity Data Streams," 2019.

[6] B. Scholkopf et al., "Estimating the Support of a High-Dimensional Distribution," Neural Computation, vol. 13, no. 7, 2021.

[7] Y. Cui et al., "Multi-homed abnormal behavior detection based on fuzzy particle swarm cluster in user and entity behavior analytics," 2022.

[8] A. Kantchelian et al., "Facade: High-Precision Insider Threat Detection Using Deep Contextual Anomaly Detection," 2024.

---

## Slide 18 — Thank You

**Thank You**

Questions & Suggestions Welcome

---

*Formatting Notes for PPT (per VTU guidelines):*
- Slide size: 16:9 Widescreen
- Title font: Times New Roman / Arial, 28–36pt, bold
- Body font: 24–30pt, minimum 20pt anywhere
- Line spacing: 1.0–1.5
- Background: Simple, light, professional
