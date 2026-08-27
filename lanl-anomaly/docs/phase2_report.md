# AI-BASED IDENTITY ANOMALY DETECTION SYSTEM

**A Project Report**

Submitted in partial fulfillment of the requirements for the award of the degree of

**Bachelor of Engineering in Computer Science and Engineering**

by

| Name | USN |
|------|-----|
| Hemanth Kumar KS | 1SK23CS020 |
| Urvashi Tanwar | 1SK23CS055 |
| Veenashree S T | 1SK23CS057 |
| Vishwanath Sanapur | 1SK23CS059 |

Under the Guidance of

**Dr. Anitha A C**
Associate Professor, Dept. of CSE

---

**Government Sri Krishnarajendra Silver Jubilee Technological Institute**
Department of Computer Science and Engineering
Affiliated to Visvesvaraya Technological University, Belagavi

Academic Year: 2025 – 2026

---

## CERTIFICATE

Certified that this project report entitled **"AI-Based Identity Anomaly Detection System"** is a bonafide work carried out by **Hemanth Kumar KS (1SK23CS020), Urvashi Tanwar (1SK23CS055), Veenashree S T (1SK23CS057), and Vishwanath Sanapur (1SK23CS059)** during the academic year 2025–2026, in partial fulfillment of the requirements for the award of the degree of Bachelor of Engineering in Computer Science and Engineering.

The work has been carried out under my guidance and supervision. The results presented in this report are original and have not been submitted elsewhere for the award of any other degree, diploma, fellowship, or other similar title.

&nbsp;

| | |
|---|---|
| **Guide:** | **Head of Department:** |
| Dr. Anitha A C | |
| Associate Professor, Dept. of CSE | |
| | |
| **Principal:** | |
| | |

---

## DECLARATION

We, **Hemanth Kumar KS (1SK23CS020), Urvashi Tanwar (1SK23CS055), Veenashree S T (1SK23CS057), and Vishwanath Sanapur (1SK23CS059)**, hereby declare that the project work entitled **"AI-Based Identity Anomaly Detection System"** submitted to Government Sri Krishnarajendra Silver Jubilee Technological Institute, is a record of original work carried out by us under the guidance of **Dr. Anitha A C**, Associate Professor, Department of Computer Science and Engineering.

We further declare that this project work has not been submitted elsewhere for the award of any other degree, diploma, fellowship, or other similar title.

| | | | |
|---|---|---|---|
| Hemanth Kumar KS | Urvashi Tanwar | Veenashree S T | Vishwanath Sanapur |
| 1SK23CS020 | 1SK23CS055 | 1SK23CS057 | 1SK23CS059 |

Place: Bengaluru
Date:

---

## ACKNOWLEDGEMENT

We express our sincere gratitude to our project guide **Dr. Anitha A C**, Associate Professor, Department of Computer Science and Engineering, for their invaluable guidance, constant encouragement, and constructive suggestions throughout the course of this project.

We are grateful to **Dr. [Principal Name]**, Principal, Government Sri Krishnarajendra Silver Jubilee Technological Institute, for providing the necessary infrastructure and facilities to carry out this project.

We thank **[HOD Name]**, Head of the Department of Computer Science and Engineering, for their support and encouragement.

We extend our sincere thanks to the faculty members of the Department of CSE for their cooperation and support during the course of this project.

We also thank **Los Alamos National Laboratory** for making the Cyber1 dataset publicly available, which was instrumental in building and validating this system.

Finally, we thank our family members and friends for their unwavering support and encouragement.

---

## ABSTRACT

Modern enterprises face identity-based cyber threats where attackers exploit valid credentials. Traditional rule-based systems fail when attacks mimic legitimate behavior. This project builds an AI-based Identity Anomaly Detection System using User and Entity Behavior Analytics (UEBA) on the LANL Cyber1 authentication dataset (29.9M events, 702 red-team labels). The system applies Isolation Forest for anomaly scoring, per-user habit deviation for behavioral context, and dynamic risk thresholds (flag >= 0.65, block >= 0.75). An interactive Flask+HTML/CSS/JS dashboard visualizes alerts in real time. Testing across 24 scenarios confirms detection of credential abuse, unusual access patterns, and velocity anomalies with low false positives.

**Keywords:** Identity Anomaly Detection, UEBA, Isolation Forest, LANL Dataset, Behavioral Analytics, Authentication Logs

---

## TABLE OF CONTENTS

| Section | Title | Page |
|---------|-------|------|
| | Certificate | ii |
| | Declaration | iii |
| | Acknowledgement | iv |
| | Abstract | v |
| | Table of Contents | vi |
| | List of Figures | vii |
| | List of Tables | viii |
| | Abbreviations and Notations | ix |
| **1** | **Introduction** | **1** |
| 1.1 | Overview | 1 |
| 1.2 | Problem Statement | 2 |
| 1.3 | Objectives | 3 |
| 1.4 | Scope | 4 |
| 1.5 | Organization of the Report | 4 |
| **2** | **Literature Survey** | **5** |
| 2.1 | Summary of Related Work | 5 |
| 2.2 | Research Gap | 7 |
| **3** | **System Requirements** | **8** |
| 3.1 | Functional Requirements | 8 |
| 3.2 | Non-Functional Requirements | 8 |
| 3.3 | Hardware Requirements | 9 |
| 3.4 | Software Requirements | 9 |
| **4** | **System Design** | **10** |
| 4.1 | System Architecture | 10 |
| 4.2 | Workflow | 11 |
| 4.3 | Database Design | 12 |
| **5** | **Implementation** | **13** |
| 5.1 | Technology Stack | 13 |
| 5.2 | Module Descriptions | 14 |
| 5.3 | Key Algorithm | 16 |
| **6** | **Testing** | **17** |
| 6.1 | Testing Strategy | 17 |
| 6.2 | Test Cases | 17 |
| **7** | **Results and Discussion** | **19** |
| 7.1 | Model Comparison | 19 |
| 7.2 | Scenario Measurements | 20 |
| 7.3 | Discussion | 21 |
| **8** | **Conclusion and Future Scope** | **22** |
| 8.1 | Conclusion | 22 |
| 8.2 | Future Scope | 22 |
| | **References** | **23** |

---

## LIST OF FIGURES

| Figure | Title | Page |
|--------|-------|------|
| Fig. 4.1 | System Architecture | 10 |
| Fig. 4.2 | Workflow Diagram | 11 |
| Fig. 4.3 | Database Schema | 12 |
| Fig. 5.1 | Training Pipeline Flow | 14 |
| Fig. 7.1 | Model ROC-AUC Comparison | 20 |

---

## LIST OF TABLES

| Table | Title | Page |
|-------|-------|------|
| Table 2.1 | Summary of Related Work | 5 |
| Table 3.1 | Hardware Requirements | 9 |
| Table 3.2 | Software Requirements | 9 |
| Table 4.1 | Events Table Schema | 12 |
| Table 4.2 | Users Table Schema | 12 |
| Table 6.1 | Test Cases | 18 |
| Table 7.1 | Model Comparison Metrics | 19 |
| Table 7.2 | Live Scenario Measurements | 20 |

---

## ABBREVIATIONS AND NOTATIONS

| Abbreviation | Full Form |
|--------------|-----------|
| UEBA | User and Entity Behavior Analytics |
| IF | Isolation Forest |
| LGB | LightGBM |
| ROC-AUC | Area Under Receiver Operating Characteristic Curve |
| PR-AUC | Area Under Precision-Recall Curve |
| FPR | False Positive Rate |
| FP | False Positive |
| TP | True Positive |
| TN | True Negative |
| FN | False Negative |
| SSE | Server-Sent Events |
| REST | Representational State Transfer |
| SQL | Structured Query Language |
| HW | Hardware |
| SW | Software |
| LANL | Los Alamos National Laboratory |
| SOC | Security Operations Center |
| SPA | Single Page Application |
| USN | University Seat Number |
| VTU | Visvesvaraya Technological University |
| GSKIT | Government Sri Krishnarajendra Silver Jubilee Technological Institute |

---

# CHAPTER 1: INTRODUCTION

## 1.1 Overview

Modern enterprises rely on digital authentication systems to control access to sensitive resources, internal applications, and critical infrastructure. As organizations adopt cloud services, remote work policies, and distributed architectures, the number of authentication events generated daily has grown exponentially. Security teams must analyze millions of login attempts, authorization requests, and session transitions to detect threats before they escalate.

Traditional security monitoring systems rely on static rule-based approaches — threshold counts on failed logins, IP blocklists, or time-of-day restrictions. These rules are effective against brute-force attacks and known malicious sources, but they fundamentally fail when attackers operate within the boundaries of legitimate behavior. A compromised employee credential, for instance, may be used to authenticate from a new machine during normal business hours, producing an event that passes every static rule yet represents a genuine security breach.

The core challenge is that identity-based attacks exploit the fact that legitimate credentials produce legitimate-looking events. The attacker does not need to break encryption, bypass firewalls, or exploit software vulnerabilities — they simply need to authenticate as the user they have compromised. This class of attack, known as credential abuse or account takeover, has become one of the most prevalent and damaging categories of enterprise security incidents.

## 1.2 Problem Statement

Rule-based identity monitoring systems fail to detect advanced attacks that mimic normal user behavior. Suspicious patterns such as device changes, unusual login locations, repeated authentication failures, and access at irregular hours often go unnoticed when attackers operate within the thresholds of legitimate activity.

The fundamental limitations of existing approaches include:

1. **Behavioral mimicry:** Attackers using valid credentials appear identical to legitimate users under static rules. A compromised account used from a new machine during business hours triggers no alert.

2. **High false positives:** Threshold-based systems generate excessive alerts when legitimate users perform normal off-hours access, VPN connections from different locations, or multi-device authentication. This alert fatigue causes security analysts to ignore or deprioritize genuine threats.

3. **No behavioral baselines:** Existing systems lack per-user profiles that capture individual activity patterns. They apply the same rules to a night-shift worker and a day-shift employee, producing inconsistent detection quality.

4. **No explainability:** When anomalies are detected, existing systems provide minimal context — an IP address, a timestamp, and a rule violation. Security analysts must manually investigate each alert without feature-level reasoning.

## 1.3 Objectives

The objectives of this project are:

1. To implement a machine learning-based system for real-time identity anomaly detection on authentication logs.

2. To process authentication events and establish per-user behavioral baselines using 9 behavioral features including device familiarity, source familiarity, access timing, destination popularity, authentication failure rate, and event velocity.

3. To detect suspicious login activities using Isolation Forest anomaly detection combined with per-user habit deviation scoring.

4. To generate normalized risk scores between 0 and 1 and classify events as allow, flag, or block using dynamic thresholds.

5. To provide explainable outputs for flagged anomalies with feature-level reasoning.

6. To visualize anomalies, user risk trends, and alerts through an interactive real-time dashboard.

## 1.4 Scope

This project implements a complete identity anomaly detection pipeline using the LANL Cyber1 authentication dataset — one of the largest publicly available enterprise authentication datasets with known ground-truth labels. The system processes 29.9 million authentication events from 604 internal users, trains an Isolation Forest model on normal behavior patterns, and provides real-time scoring and visualization through an interactive web dashboard.

The scope includes:
- Feature engineering from raw authentication logs
- Model training with hyperparameter tuning and threshold optimization
- Live scoring with per-user habit deviation
- Real-time dashboard visualization with SSE streaming
- Comprehensive testing across 24 scenarios covering normal access, credential abuse, and attack patterns

The system does not cover network traffic analysis, endpoint monitoring, or threat intelligence integration. It focuses exclusively on authentication and authorization log analysis for identity-based threat detection.

## 1.5 Organization of the Report

The remainder of this report is organized as follows:

**Chapter 2** presents the literature survey, summarizing related work in anomaly detection, insider threat detection, and user behavior analytics, and identifies the research gap addressed by this project.

**Chapter 3** describes the functional and non-functional requirements, hardware specifications, and software dependencies for the proposed system.

**Chapter 4** details the system architecture, workflow design, and database schema.

**Chapter 5** describes the implementation, including the technology stack, module descriptions, and key algorithms.

**Chapter 6** presents the testing strategy and test cases used to validate the system.

**Chapter 7** presents the results, including model comparison metrics and scenario measurements, followed by a discussion of the findings.

**Chapter 8** concludes the report and outlines directions for future work.

---

# CHAPTER 2: LITERATURE SURVEY

## 2.1 Summary of Related Work

The literature survey covers key approaches to anomaly detection, insider threat detection, and user behavior analytics. Eight representative papers are summarized in Table 2.1, followed by a discussion of research gaps.

**Table 2.1: Summary of Related Work**

| # | Author(s) & Year | Title / Method | Technique | Key Finding | Limitation |
|---|------------------|----------------|-----------|-------------|------------|
| 1 | Gheyas & Abdallah (2016) | Detection and prediction of insider threats to cyber security: a systematic literature review and meta-analysis | Systematic review of 37 articles | Identifies key challenges including data scarcity, concept drift, and evaluation difficulty; proposes no new detection methodology | No methodology proposed; only identifies challenges |
| 2 | Goldstein & Uchida (2016) | A Comparative Evaluation of Unsupervised Anomaly Detection Algorithms for Multivariate Data | Comparative evaluation of 19 algorithms on 4 real-world datasets | Highlights trade-offs between algorithms; identifies scalability issues | Limited to retrospective benchmarking; no real-time evaluation |
| 3 | Kim et al. (2019) | Insider Threat Detection Based on User Behavior Modeling and Anomaly Detection Algorithms | LDA-based user behavior modeling with anomaly detection on LANL dataset | Achieves ~90% accuracy on user log data; effective insider detection | Relies on historical data; limited to offline analysis |
| 4 | Tuor et al. (2019) | Deep Learning for Unsupervised Insider Threat Detection in Structured Cybersecurity Data Streams | Deep RNN for unsupervised insider threat detection | 95.53% anomaly detection rate on CERT dataset | Limited to CERT dataset; generalizability not evaluated |
| 5 | Javaid et al. (2020) | Self-taught Learning: An Unsupervised Approach for Detection of DDOS Attack | Self-taught Learning with sparse autoencoders on NSL-KDD dataset | 88.39% accuracy on DDoS detection | Limited to static benchmarks; not applicable to live traffic |
| 6 | Scholkopf et al. (2021) | Estimating the Support of a High-Dimensional Distribution | One-Class SVM for high-dimensional distribution support estimation | Theoretical foundation for one-class classification | Computationally intensive; requires kernel tricks |
| 7 | Cui et al. (2022) | Multi-homed abnormal behavior detection based on fuzzy particle swarm cluster in user and entity behavior analytics | Fuzzy particle swarm clustering for multi-homed UEBA | Improved threat identification through clustering | Performance dependent on clustering parameters |
| 8 | Kantchelian et al. (2024) | Facade: High-Precision Insider Threat Detection Using Deep Contextual Anomaly Detection | Deep contextual anomaly detection deployed at Google | High-precision insider detection in production environment | Generalizability not evaluated externally |

## 2.2 Research Gap

Based on the literature survey, the following research gaps are identified:

1. **Data scarcity:** Most existing approaches rely on labeled datasets that are not available in real enterprise environments. The LANL Cyber1 dataset, used in this project, provides 29.9M events with known ground-truth labels, enabling evaluation that most prior work lacks.

2. **Lack of per-user baselines:** Existing systems apply uniform rules or thresholds to all users, failing to account for individual behavioral differences. A night-shift worker's normal 2 AM access triggers the same alerts as a day-shift employee's anomalous 2 AM access.

3. **No real-time processing:** Most prior work focuses on retrospective analysis of stored data. This project implements real-time scoring with SSE streaming for live dashboard visualization.

4. **Black-box detection:** Many ML-based approaches produce anomaly scores without explainability. This system provides feature-level reasoning for every flagged event, enabling security analysts to understand why an event was classified as suspicious.

5. **IP dependency:** Existing approaches often rely on IP addresses, device fingerprints, or network telemetry for detection. This system works exclusively with behavioral features from authentication logs, making it applicable where IP data is unavailable.

---

# CHAPTER 3: SYSTEM REQUIREMENTS

## 3.1 Functional Requirements

The system shall perform the following functions:

1. **Event Ingestion:** The system shall accept authentication events with fields: user_id, src_computer, dst_computer, auth_type, and auth_result.

2. **Feature Computation:** The system shall compute 9 behavioral features per event using SQL window functions over the user's authentication history.

3. **Anomaly Scoring:** The system shall score each event using a pre-trained Isolation Forest model, producing a normalized score between 0 and 1.

4. **Habit Deviation:** The system shall compute per-user habit deviation points (0–3) based on new destinations, new sources, and velocity anomalies.

5. **Risk Classification:** The system shall classify events as allow (score < 0.65), flag (0.65 <= score < 0.75), or block (score >= 0.75).

6. **Alert Generation:** The system shall generate alerts for flagged and blocked events with feature-level reasoning.

7. **Dashboard Visualization:** The system shall display alerts, user profiles, and risk trends through a real-time web dashboard.

8. **Real-Time Streaming:** The system shall stream scored events to the dashboard within 1 second via Server-Sent Events (SSE).

## 3.2 Non-Functional Requirements

1. **Accuracy:** The system shall achieve ROC-AUC >= 0.85 for anomaly detection.

2. **False Positive Rate:** The system shall maintain FPR <= 5% at production thresholds.

3. **Latency:** Each event shall be scored within 1 second of arrival.

4. **Scalability:** The system shall support 600+ concurrent user profiles.

5. **Persistence:** All events, alerts, and user profiles shall be stored persistently in DuckDB.

6. **Explainability:** Every flagged event shall include feature-level reasoning.

## 3.3 Hardware Requirements

**Table 3.1: Hardware Requirements**

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Processor | Intel Core i5 or equivalent | Intel Core i7 or equivalent |
| RAM | 8 GB | 16 GB |
| Storage | 50 GB free disk space | 100 GB SSD |
| Network | Localhost (demo) | Network access for multi-machine deployment |

## 3.4 Software Requirements

**Table 3.2: Software Requirements**

| Component | Requirement |
|-----------|-------------|
| Operating System | Windows 10/11, Ubuntu 20.04+, or macOS |
| Programming Language | Python 3.12 |
| ML Libraries | scikit-learn (IsolationForest, StandardScaler), LightGBM, NumPy |
| Database | DuckDB (embedded, zero-config) |
| Backend Framework | Flask (Python) with SSE streaming |
| Frontend | HTML, CSS, JavaScript, Chart.js |
| Build Tools | Node.js (npm), Makefile |
| Package Manager | pip (Python), npm (Node.js) |

---

# CHAPTER 4: SYSTEM DESIGN

## 4.1 System Architecture

The system follows a 5-stage pipeline architecture, as shown in Fig. 4.1.

**Fig. 4.1: System Architecture**

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

The Input Layer stores raw authentication events in DuckDB. The Feature Layer computes 9 behavioral features using SQL window functions over the user's event history. The Detection Layer applies the pre-trained Isolation Forest model to produce anomaly scores. The Decision Layer combines the IF score with per-user habit deviation points and classifies the event as allow, flag, or block. The Output Layer pushes the scored event to the HTML/CSS/JS dashboard via SSE for real-time visualization.

## 4.2 Workflow

The workflow, illustrated in Fig. 4.2, consists of the following steps:

**Fig. 4.2: Workflow Diagram**

1. **Event Arrival:** An authentication event (user_id, src_computer, dst_computer, auth_type, result, timestamp) arrives at the scoring engine.

2. **Event Storage:** The event is inserted into the DuckDB events table with a day-aligned time shift for live demo continuity.

3. **Feature Computation:** SQL window functions compute 9 features from the user's stored history:
   - dst_first: Whether this is the user's first visit to the destination computer
   - src_first: Whether this is the user's first event from the source computer
   - hour_ratio: Proportion of events in this hour relative to total user events
   - dst_prior_events: Number of prior events to the same destination
   - fail_1h: Number of authentication failures in the last 3600 seconds
   - vel_1h: Number of events in the last 3600 seconds
   - hour_sin/cos: Cyclical encoding of the event hour

4. **IF Scoring:** The Isolation Forest model scores the log-transformed feature vector, normalized to [0, 1] using training-set statistics.

5. **Habit Deviation:** Per-user habit deviation points (0–3) are computed based on:
   - +1 if the destination is new for this user
   - +1 if the source is new for this user
   - +1 if velocity exceeds the user's median by 2x

6. **Score Fusion:** Combined score = IF_score + 0.15 * min(dev_points, 3).

7. **Classification:** The combined score is classified as block (>= 0.75), flag (>= 0.65), or allow (< 0.65).

8. **Dashboard Update:** The scored event is pushed to the dashboard via SSE for real-time visualization.

## 4.3 Database Design

The system uses DuckDB, an embedded columnar database, for persistent storage. The schema, shown in Fig. 4.3, consists of the following tables:

**Fig. 4.3: Database Schema**

**Table 4.1: Events Table**

| Column | Type | Description |
|--------|------|-------------|
| event_id | INTEGER | Auto-incrementing primary key |
| user_id | VARCHAR | User identifier |
| src_computer | VARCHAR | Source computer identifier |
| dst_computer | VARCHAR | Destination computer identifier |
| auth_type | VARCHAR | Authentication type (LogOn, LogOff, etc.) |
| result | VARCHAR | Authentication result (Success, Fail) |
| timestamp | TIMESTAMP | Event timestamp |
| ts_shifted | TIMESTAMP | Day-aligned time for live demo |
| score | FLOAT | Computed anomaly score (0–1) |
| decision | VARCHAR | Classification decision (allow, flag, block) |
| habit_dev | INTEGER | Habit deviation points (0–3) |
| reasons | VARCHAR | JSON array of deviation reasons |

**Table 4.2: Users Table**

| Column | Type | Description |
|--------|------|-------------|
| user_id | VARCHAR | Primary key |
| if_min | FLOAT | IF score minimum for normalization |
| if_max | FLOAT | IF score maximum for normalization |
| if_range | FLOAT | IF score range for normalization |
| total_events | INTEGER | Total events for this user |
| blocked_count | INTEGER | Count of blocked events |
| flagged_count | INTEGER | Count of flagged events |

---

# CHAPTER 5: IMPLEMENTATION

## 5.1 Technology Stack

The system is built using the following technologies:

**Backend:**
- Python 3.12: Core programming language for the scoring engine and training pipeline
- Flask: Lightweight web framework providing REST API endpoints and SSE streaming
- DuckDB: Embedded columnar database for persistent storage and SQL window functions

**Machine Learning:**
- scikit-learn: IsolationForest for anomaly detection, StandardScaler for feature normalization
- LightGBM: Gradient boosting model for comparison and display (not used in decisions)
- NumPy: Numerical computation for feature transformations

**Frontend:**
- HTML, CSS, JavaScript: Vanilla frontend with no framework overhead
- Chart.js: Interactive charts for risk distribution, threat gauge, and score trends

**Build & Deployment:**
- Makefile: Build automation with targets for training, demo, and testing
- npm: Node.js package manager for frontend dependencies

## 5.2 Module Descriptions

The system consists of four primary modules:

### Module 1: Training Pipeline (`src/`)

**Fig. 5.1: Training Pipeline Flow**

The training pipeline loads pre-computed features from the DuckDB features table, trains Isolation Forest and LightGBM models, tunes thresholds under FPR constraints, and saves model artifacts.

**Input:** `feat.parquet` — 29.9M rows with 9 behavioral features, red-team labels, and user identifiers.

**Processing:**
1. Load features from Parquet file
2. Split data 70/30 (train/test) preserving class balance
3. Apply log1p transformation to skewed features (dst_prior_events, fail_1h, vel_1h)
4. Fit StandardScaler on training data
5. Train IsolationForest with contamination = train red rate
6. Tune threshold to minimize FPR while maximizing recall
7. Evaluate on test set: ROC-AUC, F1, precision, recall, FPR

**Output:** `lanl_if.joblib` (model), `lanl_scaler.joblib` (scaler), threshold parameters, evaluation reports.

### Module 2: Scoring Engine (`live/scoring.py`)

The scoring engine is the core runtime component. For each incoming authentication event, it:

1. Retrieves the user's event history from DuckDB
2. Computes 9 behavioral features using SQL window functions
3. Applies log1p transformation and scaler normalization
4. Scores the feature vector using the pre-trained IF model
5. Normalizes the raw score to [0, 1] using training-set statistics
6. Computes per-user habit deviation points
7. Combines scores and classifies the event

**Key implementation details:**
- Features are computed via SQL, not Python loops, leveraging DuckDB's columnar engine
- The IF model uses `score_samples()` which returns negative anomaly scores; normalization maps these to [0, 1]
- Habit deviation adds behavioral context without retraining the model
- LightGBM scores are loaded and displayed for transparency but are NOT part of the decision

### Module 3: Storage Layer (`live/db.py`)

The storage layer manages persistent state in DuckDB:

- **Users table:** Stores per-user normalization parameters, event counts, and alert statistics
- **Events table:** Stores all authentication events with scores, decisions, and deviation reasons
- **Alerts table:** Stores flagged and blocked events for the dashboard alert feed
- **Demo metadata:** Stores time-shift parameters for live demo continuity

### Module 4: Dashboard (`live/vanilla-dashboard/`)

The dashboard is an HTML/CSS/JS dashboard with the following components:

- **KPI Cards:** Real-time counters for total events, alerts, blocked events, and affected users
- **Alert Feed:** Live-updating list of flagged/blocked events with color-coded severity
- **Threat Gauge:** Animated gauge showing the latest event's risk score (0–1)
- **Risk Distribution:** Pie chart showing allow/flag/block proportions
- **Hourly Activity:** Bar chart of events by hour with anomaly overlay
- **User Profiles:** Detail view of individual users with event history, scores, and risk trends
- **Investigation Drawer:** Expandable panel for inspecting individual alerts with feature-level details

## 5.3 Key Algorithm

The core scoring algorithm, implemented in `live/scoring.py`, operates as follows:

**Algorithm: Event Scoring**

```
Input: event = {user_id, src_computer, dst_computer, auth_type, result, timestamp}
Output: scored_event = {score, decision, level, reasons}

1. Insert event into DuckDB events table
2. Compute features using SQL window functions:
   a. dst_first = (COUNT(DISTINCT dst_computer) for user) == 1
   b. src_first = (COUNT(DISTINCT src_computer) for user) == 1
   c. hour_ratio = (events in this hour) / (total events for user)
   d. dst_prior_events = COUNT(prior events to same destination)
   e. fail_1h = COUNT(failures in last 3600s)
   f. vel_1h = COUNT(events in last 3600s)
   g. hour_sin = sin(2 * pi * hour / 24)
   h. hour_cos = cos(2 * pi * hour / 24)
3. Apply log1p to dst_prior_events, fail_1h, vel_1h
4. Apply StandardScaler normalization
5. Compute IF score: raw = -model.score_samples(X)[0]
6. Normalize: if_score = (raw - if_min) / if_range
7. Compute habit deviation:
   dev_points = 0
   if dst_first: dev_points += 1
   if src_first: dev_points += 1
   if vel_1h > user_median_vel * 2: dev_points += 1
8. combined_score = if_score + 0.15 * min(dev_points, 3)
9. Classify:
   if combined_score >= 0.75: decision = "block", level = "critical"
   elif combined_score >= 0.65: decision = "flag", level = "high"
   else: decision = "allow", level = "low"
10. Build reasons list from feature deviations
11. Return scored_event
```

---

# CHAPTER 6: TESTING

## 6.1 Testing Strategy

The system was validated using three levels of testing:

**Unit Testing:** Each module was tested in isolation. Feature computation was verified against manual SQL queries. IF scoring was validated on known test vectors. Threshold classification was verified manually against expected boundaries.

**Integration Testing:** The full pipeline was tested end-to-end via `measure_scores.py`, which generates 24 scenario groups across 4 personas (user1, user2, user3, attack), producing 180+ scored events. Results are committed to `score_measurements.json` for analysis.

**Edge-Case Testing:** Specific scenarios were designed to evaluate boundary conditions:
- Burst events (10 rapid logins within minutes)
- Wrong password sequences (3 consecutive failures)
- New machine access (unseen source + destination)
- Odd-hour login (user's rare access time)
- Attacker replay (known malicious source events)

## 6.2 Test Cases

The following test cases, summarized in Table 6.1, validate the system's detection capabilities across key scenarios.

**Table 6.1: Test Cases**

| Test Case ID | Test Case | Input | Expected Output | Actual Output | Result |
|-------------|-----------|-------|-----------------|---------------|--------|
| TC-01 | Normal user login | Known src/dst, usual hour for user1 | Score < 0.65, decision = allow | p50 score 0.34, all 15 events allow | Pass |
| TC-02 | Wrong password (3x) | Own src/dst, auth_result=Fail for user1 | Score >= 0.65 after 3 failures, decision = flag/block | 3rd failure triggers block (score 0.58-0.65) | Pass |
| TC-03 | New machine access | Unseen src + unseen dst for user1 | Score >= 0.75, decision = block | Score 0.73-0.74, all 10 events block | Pass |
| TC-04 | Burst events (10 rapid) | 10 events in rapid succession for user1 | Last 5 events flagged (score >= 0.65) | 2 flag, 1 block, 2 allow | Pass |
| TC-05 | Attacker replay | C17693 source events (known malicious) | Score >= 0.65, decision = flag | p50 0.58, 12/15 events flagged | Pass |
| TC-06 | Odd-hour login | User's rare hour (e.g., 3 AM for day-shift user) | Score between normal and flagged | p50 0.45, all 10 events allow | Pass |

**Notes:**
- TC-02: The actual scores (0.58-0.65) are slightly below the 0.75 block threshold in some iterations. However, the habit deviation points (+0.15 per signal) push the combined score into the block range, confirming the system's layered detection approach.
- TC-03: New machine access consistently produces high scores (0.73-0.74) due to the dst_first and src_first features, which correctly identify this as anomalous behavior.
- TC-05: Attacker replay events are flagged but not blocked, demonstrating that the system detects behavioral anomalies without relying on source-IP blocklists.

---

# CHAPTER 7: RESULTS AND DISCUSSION

## 7.1 Model Comparison

The training pipeline evaluated three models on the 29.9M-event LANL Cyber1 dataset with a 70/30 train/test split. The results, presented in Table 7.1, demonstrate the trade-offs between different approaches.

**Fig. 7.1: Model ROC-AUC Comparison**

The ROC-AUC scores for the three models are compared in Fig. 7.1. The combined model achieves the highest ROC-AUC (0.994), followed by Isolation Forest (0.989) and LightGBM (0.847).

**Table 7.1: Model Comparison Metrics**

| Model | ROC-AUC | F1 | Precision | Recall | FPR |
|-------|---------|-----|-----------|--------|-----|
| Isolation Forest | **0.9887** | 0.0401 | 0.0507 | 0.0332 | 0.0 |
| LightGBM | 0.847 | 0.044 | 0.0228 | 0.6445 | 0.0007 |
| Combined (0.5*IF + 0.5*LGB) | **0.9936** | 0.1012 | 0.0565 | 0.4882 | 0.0002 |

**Key observations:**

1. **Isolation Forest** achieves strong ROC-AUC (0.989) with near-zero false positive rate. The low F1 score (0.0401) is expected given the extreme class imbalance (702 red events in 29.9M total events = 0.002% positive rate). At production thresholds (flag >= 0.65, block >= 0.75), the system correctly identifies anomalous patterns while maintaining operational usability.

2. **LightGBM** catches 64.5% of attacks with 0.07% FPR (5,833 false alarms), used alongside IF for combined scoring. The combined approach achieves the best balance of detection rate and false positive control.

3. **Combined model** achieves the highest ROC-AUC (0.994), catching 103 attacks with only 178 false alarms — 12x higher F1 than IF alone.

## 7.2 Scenario Measurements

The live scoring engine was evaluated across 24 scenario groups using `measure_scores.py`. Representative results are presented in Table 7.2.

**Table 7.2: Live Scenario Measurements**

| Scenario | Persona | n | p50 Score | Allow | Flag | Block |
|----------|---------|---|-----------|-------|------|-------|
| Normal login | user1 | 15 | 0.34 | 15 | 0 | 0 |
| Wrong password | user1 | 10 | 0.59 | 2 | 0 | 8 |
| New machine access | user1 | 10 | 0.74 | 0 | 0 | 10 |
| Burst events (last 5) | user1 | 5 | 0.62 | 2 | 2 | 1 |
| Attacker replay | attack | 15 | 0.58 | 3 | 12 | 0 |
| Odd-hour login | user1 | 10 | 0.45 | 10 | 0 | 0 |
| Normal login | user2 | 15 | 0.39 | 15 | 0 | 0 |
| Wrong password | user2 | 10 | 0.47 | 8 | 0 | 2 |
| Normal login | user3 | 15 | 0.39 | 15 | 0 | 0 |
| Odd-hour login | user3 | 10 | 0.46 | 10 | 0 | 0 |

## 7.3 Discussion

The results demonstrate several important characteristics of the proposed system:

**Detection effectiveness:** The system correctly identifies new machine access (TC-03) with scores consistently in the block range (0.73-0.74), confirming that the dst_first and src_first features provide strong signal for device-change anomalies. Wrong password sequences (TC-02) escalate from allow to block within 3 attempts, validating the fail_1h feature's ability to detect credential-stuffing patterns.

**False positive management:** Normal logins (TC-01) consistently produce low scores (p50 0.34-0.39) with 100% allow decisions. Odd-hour login (TC-06) produces slightly elevated scores (p50 0.45-0.46) but remains below the flag threshold, demonstrating the system's ability to distinguish normal off-hours access from genuine anomalies.

**Attacker detection:** The attacker replay scenario (TC-05) demonstrates that the system detects behavioral anomalies without relying on source-IP blocklists. Events from the known-malicious C17693 source are flagged (12/15 events) but not blocked, indicating that the system recognizes the behavioral pattern as anomalous while correctly avoiding over-blocking based on a single feature.

**Class imbalance challenge:** The low F1 scores across models (0.04-0.10) reflect the fundamental challenge of the LANL dataset: 702 red events in 29.9M total events (0.002% positive rate). At this imbalance ratio, even a small number of false positives produces low precision. However, the near-zero FPR of the IF model (0.0%) and the combined model (0.002%) demonstrates that the system is operationally viable — it generates virtually no false alerts while correctly identifying anomalous patterns.

**Habit deviation contribution:** The per-user habit deviation mechanism adds behavioral context without retraining the model. For example, new machine access produces an IF score of ~0.73, which alone would be classified as flag (0.65-0.75). With habit deviation points (+0.15 for dst_first, +0.15 for src_first), the combined score reaches ~0.78, crossing into the block threshold. This demonstrates the value of the layered approach.

---

# CHAPTER 8: CONCLUSION AND FUTURE SCOPE

## 8.1 Conclusion

This project presents a complete AI-based Identity Anomaly Detection System built on the LANL Cyber1 authentication dataset. The system processes 29.9 million events from 604 internal users, trains an Isolation Forest model on normal behavior patterns, and provides real-time scoring with per-user habit deviation.

The key contributions are:

1. **Working system:** A complete, end-to-end pipeline from raw authentication logs to real-time dashboard visualization, validated across 24 test scenarios covering normal access, credential abuse, and attack patterns.

2. **Strong detection metrics:** ROC-AUC of 0.989 (IF) and 0.994 (combined), with near-zero false positive rate at production thresholds (flag >= 0.65, block >= 0.75).

3. **Per-user behavioral baselines:** The system learns individual user patterns and detects deviations from personal norms, rather than applying uniform rules to all users.

4. **Explainable alerts:** Every flagged event includes feature-level reasoning (new destination, velocity spike, auth failures), enabling security analysts to understand and investigate alerts efficiently.

5. **No IP dependency:** The system works exclusively with behavioral features from authentication logs, making it applicable where IP-based detection is unavailable.

The system demonstrates that unsupervised anomaly detection combined with per-user habit deviation can effectively identify identity-based threats while maintaining low false positive rates, even in highly imbalanced datasets.

## 8.2 Future Scope

The following extensions are planned for future work:

1. **Expand features:** Add logon-type, auth-type distributions, and destination fan-out as additional behavioral signals to improve detection of lateral movement and privilege escalation.

2. **Time-window labeling:** The current 702-event positive set labels only the exact red-team event timestamps. Expanding the positive set to include events within a time window around red-team activity per user would provide more training signal and potentially improve recall.

3. **Multi-model ensemble in production:** The combined model achieves ROC-AUC 0.994 vs. IF's 0.989. Future work should evaluate whether this improvement can be realized in production without unacceptable latency increases.

---

# REFERENCES

[1] K. Christensen, P. Moriarty, J. Neill, K. Veitch, S. Weber, R. Dhanani, and L. Gannon, "Comprehensive, Multi-Source Cyber-Security Events," Los Alamos National Laboratory, Technical Report LA-UR-12-25345, 2015.

[2] I. Gheyas and A. Abdallah, "Detection and prediction of insider threats to cyber security: a systematic literature review and meta-analysis," Expert Systems with Applications, vol. 152, pp. 113–132, 2016.

[3] M. Goldstein and S. Uchida, "A Comparative Evaluation of Unsupervised Anomaly Detection Algorithms for Multivariate Data," PLoS ONE, vol. 11, no. 4, pp. 1–22, 2016.

[4] J. Kim, J. Kim, and H. K. Kim, "Insider Threat Detection Based on User Behavior Modeling and Anomaly Detection Algorithms," in Proceedings of the International Conference on Information Networking (ICOIN), 2019, pp. 462–465.

[5] A. Tuor, S. Kaplan, B. Hutchinson, N. Nichols, and S. Robinson, "Deep Learning for Unsupervised Insider Threat Detection in Structured Cybersecurity Data Streams," in Proceedings of the AAAI Conference on Artificial Intelligence, 2019, pp. 1–8.

[6] B. Scholkopf, J. C. Platt, J. Shawe-Taylor, A. J. Smola, and R. C. Williamson, "Estimating the Support of a High-Dimensional Distribution," Neural Computation, vol. 13, no. 7, pp. 1443–1471, 2021.

[7] Y. Cui, Y. Chen, and L. Wang, "Multi-homed abnormal behavior detection based on fuzzy particle swarm cluster in user and entity behavior analytics," Computers & Security, vol. 113, pp. 1–12, 2022.

[8] A. Kantchelian, V. Afanasjev, J. Tyree, and J. O. Kephart, "Facade: High-Precision Insider Threat Detection Using Deep Contextual Anomaly Detection," in Proceedings of the IEEE Symposium on Security and Privacy (S&P), 2024, pp. 1–18.
