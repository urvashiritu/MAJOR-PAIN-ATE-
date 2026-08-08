# Project Roadmap

## Project Definition

### Final project title

**Real-Time User Identity Anomaly Detection Using Behavioral Login Profiles**

### Final project statement

This project builds a login-security system that learns a user's normal login
behavior, detects unusual authentication events, explains the reasons for the
risk score, and displays the decision on a live security dashboard.

The project has two connected parts:

1. An offline data and machine-learning pipeline based on the RBA dataset.
2. A live website, risk API, user-profile service, and dashboard for the demo.

The project is specifically about **login identity anomalies**. It is not a
complete insider-threat, authorization-abuse, or post-login monitoring system.

## Validation Verdict

The project is technically feasible and the RBA dataset is sufficient for the
core objective. The dataset contains approximately 31.3 million login events,
timestamps, users, countries, devices, browsers, operating systems,
success/failure results, attack-IP indicators, and account-takeover indicators.

The following limits must remain explicit:

- There are only 141 confirmed account-takeover rows, so takeover detection must
  be reported as a difficult, rare-event evaluation rather than a guaranteed
  classifier.
- `Is Attack IP` is a useful suspicious-event label, but it is not identical to
  confirmed account takeover.
- The dataset has blank device values. Blank must be treated as an explicit
  `unknown` category or missing value, not silently treated as a real device.
- One user contributes roughly 45% of the events. Sampling must cap or isolate
  this dominant bot/service-account behavior.
- Browser and operating-system version strings can create false device changes.
  Normalize versions before calculating device history.
- The live VPN scenario is a controlled demonstration. A VPN may not reliably
  change geolocation, so the demo must also support a clearly labelled
  simulation mode.

## Target Architecture

```text
RBA CSV
  -> DuckDB/Polars data pipeline
  -> cleaned sample and historical user baselines
  -> engineered features
  -> anomaly models and evaluation
  -> saved model artifacts

Website login
  -> risk API
  -> live feature extraction
  -> user profile comparison
  -> rules + anomaly model
  -> allow, challenge, or block
  -> WebSocket event
  -> security dashboard
```

## Beginner Build Order

Do not start with the dashboard. Build and test each layer in this order:

1. Confirm the project scope and documentation.
2. Create a reproducible Python environment.
3. Audit the raw dataset on a small sample and with full-file aggregates.
4. Build a clean, user-aware training sample.
5. Build the feature pipeline.
6. Build a rule-based risk engine.
7. Train and evaluate anomaly models.
8. Build the user-profile and risk APIs.
9. Build the login website.
10. Build the live security dashboard.
11. Connect both laptops and rehearse the demonstration.
12. Replace all placeholder claims in the report with measured results.

## Phase 0: Documentation And Scope

### Work

- Keep `major.md` as the theoretical background and presentation material.
- Use `dataset_scan_report.md` as dataset evidence (facts, issues, cleaning, blind re-audit §7), while correcting
  any contradictory missing-value/device statements.
- Treat old unverified metrics as invalid until reproduced.
- Use this file as the implementation source of truth.
- Move useful Q&A into an implementation log instead of presenting it as final
  research evidence.

### Completion criteria

- Every document describes login anomaly detection, not a broader unsupported
  security platform.
- No unverified accuracy, precision, or recall appears as a result.
- Dataset facts are consistent across documents.

## Phase 1: Environment And Repository Setup

### Recommended beginner stack

- Python 3.11 or later
- DuckDB for large CSV queries
- Polars or PyArrow for chunked processing
- pandas for small processed files and charts
- scikit-learn for anomaly models
- joblib for saving models
- FastAPI for the risk API
- SQLite for the first profile/event database
- HTML, CSS, and JavaScript for the first website/dashboard
- Plotly or Chart.js for visualizations

### Target folders

```text
src/
  data/
  features/
  models/
  api/
  dashboard/
data/
  raw/
  processed/
models/
reports/
tests/
```

### Rules

- Never modify the raw 8.5 GB CSV.
- Never load the entire CSV into pandas.
- Save intermediate data as Parquet where possible.
- Record configuration, sample sizes, random seeds, and timestamps.

### Completion criteria

- A fresh environment can install the required packages.
- A small test command runs without needing the full dataset.
- The raw data remains unchanged.

## Phase 2: Dataset Audit

### Work

Create a script that verifies:

- row count and date range
- unique users and countries
- successful and failed events
- attack-IP and account-takeover counts
- blank values by column
- device categories
- events per user
- dominant-user concentration
- browser and operating-system inconsistencies

Run cheap full-file aggregates with DuckDB. Use a small sample for detailed
development and visualization.

### Completion criteria

Produce:

```text
reports/dataset_summary.json
reports/dataset_quality.csv
data/processed/development_sample.parquet
```

All values in the reports must be reproducible from the raw file.

## Phase 3: Cleaning And Sampling

### Cleaning

- Parse timestamps in chronological order.
- Map blank device values to `unknown`.
- Normalize browser and operating-system names by removing version noise.
- Preserve raw values for auditability.
- Decide explicitly whether impossible browser/OS combinations are retained,
  corrected, or excluded, and record the decision.

### Sampling

Use user-aware sampling rather than selecting rows and then deleting users.
Include:

- all users with confirmed account-takeover events
- attack-heavy users
- random light-attack users
- representative normal users
- a capped sample of the dominant bot/service account

Target approximately 500,000 to 1,000,000 rows initially. Do not force an
artificial attack ratio without reporting the natural ratio too.

### Important split rule

Use a **chronological split as the primary evaluation**: profiles and models
may use only information available before each test event. Add a user-holdout
split as a secondary experiment for unseen users. A user-only split by itself
can make contextual history features unrealistic because every first event for
an unseen user has no prior baseline.

### Completion criteria

- All 141 confirmed takeover rows and their users are accounted for.
- The dominant user cannot dominate the training sample.
- No test event contributes future information to its own features.
- Sampling statistics are saved in a report.

## Phase 4: Feature Engineering

Implement one shared feature function for both offline and live events.

### Core features

- `hour`
- `is_night`
- `is_weekend`
- `country_change`
- `device_change`
- `failed_before_success`
- `rapid_login_rate`
- `login_frequency_today`

### Required semantics

- The first-ever event has no previous country/device baseline, so handle it
  with an explicit policy rather than automatically calling it suspicious.
- `failed_before_success` uses a real five-minute lookback window.
- `rapid_login_rate` uses a defined 60-second window.
- `device_change` uses normalized device/browser/OS fields.
- Every historical feature uses only events earlier than the current event.

### Completion criteria

- Unit tests cover first events, missing devices, repeated events, time windows,
  midnight/day changes, and chronological ordering.
- The same input event produces the same offline and live feature values.
- A feature report contains distributions and example events.

## Phase 5: Rule-Based Baseline

Before machine learning, implement an explainable baseline.

Example points:

```text
New country:          +30
New device:           +25
Unusual login hour:   +15
Recent failed login:  +20
Rapid login activity: +15
```

Map the total to low, medium, high, and critical risk. The exact points are
initial values and must be tuned using validation data rather than presented as
scientific constants.

### Completion criteria

- A normal event receives a low score.
- Each suspicious feature increases the score predictably.
- The result includes both a score and human-readable reasons.

## Phase 6: Models And Evaluation

Start with Isolation Forest because it is relatively fast and explainable.
Then compare it with the planned alternatives:

- Isolation Forest
- Local Outlier Factor on a smaller subset
- One-Class SVM on a smaller subset
- Elliptic Envelope only if the feature distribution and scale make it useful

These are anomaly-detection models, so do not describe them as ordinary
supervised classifiers trained directly on attack labels. Train primarily on
normal or less-contaminated behavior, then use attack-IP and account-takeover
labels for external evaluation.

Measure:

- precision
- recall
- F1-score
- false-positive rate
- threshold curves
- confusion matrices where meaningful
- detection of confirmed takeover events
- detection of successful attack-IP events
- scoring latency

Compare models with the same split, features, and event set. Select the final
model based on detection quality, false positives, speed, and explanation
quality, not accuracy alone.

### Completion criteria

```text
models/final_model.joblib
reports/model_comparison.csv
reports/threshold_analysis.csv
reports/confusion_matrix.png
```

Every reported metric can be reproduced by a command in the repository.

## Phase 7: User Profile And Risk API

Create a profile for each demo user containing:

- known devices
- usual countries
- usual login hours
- typical daily login count
- recent failed-login history
- profile confidence or number of observations

Create API operations for:

```text
POST /login
POST /events
GET  /risk/{event_id}
GET  /users/{user_id}/profile
GET  /alerts
WS   /dashboard
```

The login flow must:

1. receive a login event
2. calculate live features
3. load the user's profile
4. run the rules and model
5. combine the scores
6. return allow, challenge, or block
7. publish the event to the dashboard
8. update the profile only after an accepted normal event

Use fake accounts and never store real passwords.

## Phase 8: Website And Dashboard

### Website

Build a small company-style portal with:

- login page
- normal home page
- verification page
- blocked-login page
- optional demo controls clearly labelled for the examiner

### Dashboard

Show:

- live event stream
- current risk score
- allow/challenge/block decision
- user, country, device, and timestamp
- reasons for the score
- user profile summary
- recent alerts
- allowed/challenged/blocked totals

The dashboard must update when a login occurs on the second laptop.

## Phase 9: Live Demonstration

Use Laptop 1 for the dashboard and Laptop 2 for the company website.

### Demo sequence

1. Known device and normal location: low risk and allow.
2. New country using VPN or demo simulation: increased risk.
3. New device/browser: additional risk.
4. Multiple failed attempts: alert appears.
5. Successful login after failures: challenge or block.
6. Return to the normal profile: risk decreases.

The dashboard should explain the decision as it happens. The key demonstration
is not merely that the system shows red or green; it is that the score changes
because specific behavioral evidence changed.

## Phase 10: Testing

Test the system at four levels:

- data tests: parsing, missing values, ordering, and sampling
- feature tests: history and time-window semantics
- model tests: reproducibility, thresholds, and false positives
- application tests: login response, alerts, WebSocket updates, and recovery

Test the demo before presentation without relying on a public network or an
unpredictable VPN provider.

## Phase 11: Report And Presentation

Use this report structure:

1. Introduction
2. Problem statement and objectives
3. Related work
4. Dataset and data quality
5. Preprocessing and sampling
6. Feature engineering
7. User-profile and risk architecture
8. Anomaly models
9. Evaluation methodology
10. Results
11. Website and dashboard implementation
12. Live demonstration
13. Limitations
14. Future work
15. Conclusion

Replace every placeholder metric with a measured result. Explain that the
system detects deviations from a learned login baseline; it does not prove an
attacker's identity and cannot detect every compromised session.

## Definition Of Done

The project is ready for demonstration when:

- the raw dataset can be processed reproducibly
- features are causally correct and shared by offline/live paths
- at least one model beats the rule baseline on the agreed evaluation
- false positives and rare takeover results are reported honestly
- a login from Laptop 2 appears live on the dashboard
- normal and suspicious scenarios produce different decisions
- every alert includes an explanation
- documentation matches the implemented system

## Immediate Next Tasks

1. Correct contradictions in the dataset documentation about blank devices and
   device categories.
2. Create the repository structure and Python environment.
3. Implement the dataset audit script.
4. Implement the development sample and save its statistics.
5. Implement and test the eight shared features.

Do not begin the full live dashboard until these five tasks are complete.
