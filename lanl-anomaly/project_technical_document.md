# AI-Based Identity Anomaly Detection System

## Comprehensive Technical Inspection and Academic Report Preparation

**Repository inspected:** `lanl-anomaly`  
**Prepared:** 31 October 2026  
**Evidence basis:** current source tree, saved model metadata, JSON reports, experiment notes, and direct read-only queries against the shipped score parquet.  
**Important:** The older reference file `MPrepochapter.pdf` was not found under `/home/girish`; the chapter structure in the request was used. The current checkout contains pre-existing modifications and missing raw files. Nothing in the project code or data was changed for this inspection.

## Executive overview

This is a LANL Cyber1 authentication anomaly detection prototype and analyst demo. The training work explores supervised LightGBM, unsupervised Isolation Forest, LSTM sequence reconstruction/surprisal, and feature stacking. The strongest documented held-out experiment is LightGBM with 21 inputs, including LSTM autoencoder reconstruction error (RUN 9). The web application is a Flask dashboard with employee demo sign-in, analyst pages, server-sent events (SSE), and a fixed replay of scored LANL events.

There are two distinct scoring paths. The **offline, full-dataset score artifact** records 29,905,488 events with the 21-feature RUN 9 model and threshold `0.1871951071`. The **current live scorer source** loads `models/lanl_lgb_13feat.joblib`, builds a 21-key feature dictionary but sends only the bundle’s 13 selected features to LightGBM, and uses threshold `0.1934750697`. The replay reads the offline score parquet, not the current live scoring function. Thus offline replay results are not evidence that live scoring obtains the same performance.

The score parquet was queried directly: 29,905,488 rows, 702 red labels, 604 distinct source users, 5,658 distinct destination users, 8,162 source computers, and 8,085 destination computers. At the stored blocking threshold it has 598 red events and 269 normal events at/above threshold, with 104 red events below threshold. The curated replay window contains 9,954 events, 20 labeled red events, all 20 at FLAG or BLOCK, and 12 normal events at BLOCK. These are dataset/replay results, not generalization accuracy.

The reported held-out RUN 9 result is 136/240 red events detected, 183 false positives, PR-AUC 0.3682, ROC-AUC 0.9999, F1 0.4866, and threshold 0.1872. These values are recorded in the run log and serialized bundle; without the training feature table and held-out per-row scores, they cannot be recomputed from the current checkout. The split is grouped by `src_user`, with 462 red events in train and 240 in test, and a train/validation subdivision is documented for threshold choice. No accuracy is claimed because extreme imbalance makes it misleading.

## Repository structure and entry points

| Path | Purpose / report relevance |
|---|---|
| `README.md`, `SETUP.md`, `LIVE_README.md`, `DEMO_TLDR.md` | Overview, setup, live architecture, demo script. Some claims describe older 21-feature wiring. |
| `Agents.md` | Local collaboration requirements. |
| `AI-SPEC.md`, `docs/AI-SPEC.md` | Domain evaluation context; contains citations/claims that require independent checking before academic use. |
| `STORY.md`, `UI-REVIEW.md` | Narrative of experiments and UX review; not primary metric artifacts. |
| `bootstrap.sh`, `requirements.txt`, `.gitattributes`, `.gitignore` | Environment setup, package requirements, LFS/ignore configuration. |
| `src/00_build_slice.py` | Dataset stream scan, user sampling, slice and DuckDB loading. |
| `src/01_build_features.py` | SQL feature construction and guarded rebuild/swap. |
| `src/02_feature_probe.py` | Univariate feature separability probe. |
| `src/03_retrain_both.py` | Legacy 20-feature LightGBM + Isolation Forest training. |
| `src/retrain13_both.py` | 13-feature LightGBM + normal-only Isolation Forest training, grouped user split and validation threshold. |
| `src/04_lstm_surprisal.py` | Tokenized sequence language-model surprisal experiment. |
| `src/05_lstm_autoencoder.py` | LSTM autoencoder training, reconstruction error computation and optional database write. |
| `src/06_extract_latent.py` | LSTM representation extraction and dimensionality reduction experiments. |
| `src/07_train_normal_if.py` | Normal-only IF experiment with sampled train/calibration/evaluation and report generation. |
| `eval_lstm.py` | Evaluates LSTM-derived scores and LightGBM stacking; saves the 21-feature bundle when requested. |
| `exp1.py`, `exp2.py`, `exp3.py`, `if_finetune.py`, `overlap_test.py` | Historical model comparisons, feature experiments and blending tests. |
| `verify.py`, `verify_v2.py`, `verify_exp2.py`, `verify_scores.py` | Dataset, feature and score checks; some require absent raw database/files. |
| `test_live.py`, `test-playwright.js` | Application smoke checks and browser test. |
| `live/app.py` | Flask application, routes, replay orchestration, explanations and dashboard payloads. |
| `live/scorer.py` | Current incremental inference path, model loading, feature assembly and user history. |
| `live/scoring.py` | Separate/older batch scoring pipeline for creating score files; not the current per-event scorer. |
| `live/db.py` | Feature schema/SQL and DuckDB/parquet access helpers. |
| `live/replay.py` | Loads the curated window from parquet and joins raw event metadata from `lanl.duckdb`. |
| `live/auth.py` | Demo accounts, generated TOTP secrets, password and TOTP verification. |
| `live/templates/` | Login, employee, company simulator, analyst dashboard and dataset pages plus shared partials. |
| `live/static/js/` | API client, dashboard/router, charts, UI components and search. |
| `live/static/css/` | Dashboard and company simulator styles. |
| `live/static/vendor/` | Locally bundled ECharts, Chart.js and fonts. |
| `live/verify.py`, `live/test_audit.py`, `live/test_blind_event.py` | Model/scoring verification, full browser audit, and blind-event test harness. |
| `docs/` | Feature research, model deep dive, setup pointers, architecture JSON and research summaries. |
| `reports/experiment_log.md` | Experiment chronology, including failed/leaky runs and accepted RUN 9. |
| `reports/both_report.json` | Earlier split/model report, explicitly notes red-user leakage. |
| `reports/normal_if_report.json`, `reports/normal_if_13_report.json` | Sampled normal-only IF reports. |
| `data/processed/lanl_scores.parquet` | Shipped full-event score output; used by replay and offline dashboard. |
| `data/processed/lanl_feat_9feat_29.9M.parquet`, `lanl_feat_13feat_29.9M.parquet` | Processed feature files. |
| `models/*.joblib` | LightGBM and Isolation Forest serialized models/bundles. |
| `models/*.pt` | LSTM and LSTM-AE checkpoints with weights and token vocabulary. |
| `data/raw/lanl/` | Expected raw/intermediate source files. Several are absent in this checkout. |

### Main commands (as documented)

```bash
cd lanl-anomaly
./bootstrap.sh --verify
LANL_DEV=1 venv/bin/python -m live.app
```

Training/evaluation entry points include `venv/bin/python src/retrain13_both.py --verbose` (13-feature run), `venv/bin/python src/03_retrain_both.py --verbose` (20-feature legacy run), and `venv/bin/python eval_lstm.py --ae-score --save-model` (21-feature stacking path; inspect flags/help before use). Training is not required for the demo. Do not run these against this checkout without restoring the required raw DuckDB; training also writes model/report outputs.

## Chapter 1: Introduction

### 1.1 Background and motivation

Enterprise authentication records describe user-to-computer access over time. A stolen credential can generate legitimate-looking successful logins, so detection can benefit from comparing events with prior user activity, temporal rates, authentication method and machine relationships. The project applies this idea to LANL’s de-identified Cyber1 authentication stream and provides an analyst-facing demonstration.

### 1.2 Problem statement

Given an authentication event and behavior-derived attributes, assign a risk score and identify events associated with red-team activity while keeping false alerts manageable under a highly imbalanced label distribution. The public red-team file labels only a small subset of events; unlabeled events should not automatically be described as confirmed benign in academic claims.

### 1.3 Objectives

1. Construct an event-level dataset from LANL authentication data and red-team labels.
2. Engineer identity, host, temporal, pair novelty and sequence features.
3. Compare supervised LightGBM with unsupervised Isolation Forest and recurrent sequence models.
4. Evaluate on user-grouped data and inspect red-team replay behavior.
5. Demonstrate score, triage decision and user-relative context through a web interface.

### 1.4 Scope and limitations

#### 1.4.1 Scope

LANL Cyber1 authentication records, a filtered 604-user cohort, labelled red-team events, tabular and sequence-based scores, offline scoring/replay and a local Flask demo.

#### 1.4.2 Limitations

Only 702 red-team events are labelled in the selected event table; identities and hosts are pseudonymous; the data are historical and domain-specific; no external enterprise dataset validates transfer. Live and offline models do not currently match. The live application depends on the unavailable raw DuckDB for context and replay metadata. Demo accounts use hard-coded passwords, local generated TOTP secrets and a development bypass; this is not production authentication. The sample threshold and observed rates are not operational guarantees.

## Chapter 2: Literature review preparation

### 2.1 Overview

Relevant concepts are anomaly detection under class imbalance, user/entity behavioral profiling, authentication graphs, lateral movement, isolation-based outlier detection, gradient-boosted trees and sequence modeling. The project’s implementation is tabular/event based; graph literature is background and a future direction, not a claim that a graph model is implemented.

### 2.2 Literature survey

| Work | Contribution relevant to this project | Relationship / boundary |
|---|---|---|
| Turcotte, Kent & Hash, *Unified Host and Network Data Set* (2018) | Describes the LANL research dataset and data-release context. | Primary citation for the dataset; cite the official LANL source as well. |
| Kent, Liebrock & Neil, “Authentication graphs: Analyzing user behavior within an enterprise network” (2015) | User-specific and bipartite authentication graph analysis for profiling and intrusion detection. | Motivates behavioral context; this repository does not implement that graph method. |
| Ho et al., “Hopper: Modeling and Detecting Lateral Movement” (USENIX Security 2021) | Models login paths and combines attack specifications with anomaly scoring to detect lateral movement. | Relevant comparison for multi-event paths; this project mostly scores event rows independently. |
| Liu, Ting & Zhou, “Isolation Forest” (ICDM 2008) | Isolates observations using randomized trees; anomaly relates to shorter isolation paths. | Implemented as an experimental baseline, not the selected live model. |
| Ke et al., “LightGBM: A Highly Efficient Gradient Boosting Decision Tree” (NeurIPS 2017) | Efficient gradient-boosted decision trees. | Implemented supervised classifier; learns from red-team labels. |
| Du et al., “DeepLog: Anomaly Detection and Diagnosis from System Logs through Deep Learning” (CCS 2017) | Sequence prediction for log anomaly detection. | General sequence-model motivation; repository’s LSTM-AE uses categorical authentication tokens, not DeepLog’s exact method. |

### 2.3 Relevant theories and concepts

- **Supervised binary classification:** LightGBM estimates a class-1 score from labelled red-team examples and features. `predict_proba(...)[0,1]` is the served score in the current live path.
- **Unsupervised anomaly detection:** Isolation Forest fits on feature vectors, optionally only normal rows; its `decision_function` orientation is transformed in experiment code so higher values can mean more anomalous.
- **Sequence reconstruction:** six categorical attributes per event become vocabulary tokens; an LSTM encoder/decoder reconstructs an input window. Cross-entropy on the current event’s six tokens is used as reconstruction error.
- **User behavior profiling:** per-user historical arrays support percentiles for velocity and reconstruction error. These percentiles are explanation context; they are not the LightGBM model’s decision rule.
- **Rare-event metrics:** precision, recall, F1, PR-AUC, ROC-AUC and FPR answer different questions. Accuracy is omitted because a majority-class predictor would look strong with 702 positives in ~30M events.
- **Thresholding:** a model score threshold converts ranking into a decision. The stored offline output uses block threshold 0.187195 and flag threshold approximately 0.7 × block threshold. Current live scorer uses 0.193475 for BLOCK and its 0.7 fraction for FLAG.

### 2.4 Research gaps indicated by this work

The experiment history documents weak transfer to a held-out attacker machine, several early user/event split leakage issues, and a training-serving feature mismatch. The next research gap is to test whether past-only user and graph/path features improve unseen-user or unseen-attacker detection under fixed alert budgets. Proposed literature-derived features such as path length, credential changes, peer deviation and destination diversity are not all implemented in the deployed scorer.

### 2.5 Existing system

The existing prototype is a user-grouped LightGBM score with engineered event features, plus an exploratory normal-only Isolation Forest and LSTM autoencoder. Its analyst interface combines offline replayed scores with independent live demo events.

### 2.6 Proposed system

The proposed academic framing should describe the system as an experimental identity anomaly detection pipeline with risk-based ALLOW/FLAG/BLOCK display, not as a production access-control platform. The desired future integrated system would train and serve from the same feature implementation, persist versioned thresholds, expose reproducible test results, and use user-history or path models only after independent evaluation.

### 2.7 Summary

Literature supports authentication behavior modeling and graph/path context. The current empirical contribution is engineering and evaluation of several models on the selected LANL cohort; its performance claims must retain their split and scope labels.

## Chapter 3: Methodology

### 3.1 Research methodology

#### 3.1.1 Dataset acquisition

The source is LANL’s *Comprehensive, Multi-Source Cyber-Security Events* / Cyber1 58-day release, specifically `auth.txt` and `redteam.txt`. The project script states the original auth stream has 1,051,430,459 events; the dataset includes other event types, but this project uses authentication. `auth.txt` is streamed from the archive rather than fully extracted. The raw archive and raw database are not present in the inspected checkout, so original size and full-stream counts are documented/code-referenced rather than independently re-scanned here.

#### 3.1.2 Dataset selection and preprocessing

`src/00_build_slice.py` reads the red-team rows as `(time,user,src_computer,dst_computer)`, scans authentication CSV stream, collects source/destination users/computers and exact matching red-team tuples, samples 500 normal source users from `^U\d+@DOM1$` with Python seed 42, and retains all source-user events for red-team users plus selected normal users. The intended cohort is 104 red-team users + 500 normal users = 604 users; resulting row count in the saved score artifact is 29,905,488.

The nine raw columns are: `time`, `src_user`, `dst_user`, `src_computer`, `dst_computer`, `auth_type`, `logon_type`, `orientation` (LANL field is `auth_orientation`), and `result`. There is no demonstrated global deduplication or general missing-value imputation in the slice code. Malformed rows with fewer than nine comma-separated fields are skipped. Red-team annotation is exact-match on time, source user, source computer and destination computer; feature building makes a distinct red-team table before membership matching. `result='Fail'` is used for failure counts. Other missing/null treatment is not comprehensively specified; do not claim full cleaning or null imputation.

#### 3.1.3 Feature engineering

The initial `src/01_build_features.py` table adds `hour=(time % 86400)/3600`, `is_red`, `dst_first`, `src_first`, `hour_events`, `user_events`, `dst_prior_events`, `fail_1h`, `vel_1h`, and `is_ntlm`. The later model/serving feature generations extend this table in SQL or evaluation CTEs. Categorical model inputs are not one-hot encoded for LightGBM; most tabular features are numeric or binary. The LSTM sequence path uses field-specific categorical vocabulary IDs.

#### 3.1.4 Model development

The primary reported experiment is supervised LightGBM with 21 features, combining 20 tabular signals with LSTM-AE reconstruction error. Older/alternative runs use 9, 13, 20, 23 or 37 features. The current live scorer selects 13 fields from the generated dictionary. Isolation Forest is also fit on standardized numeric features; some experiments log-transform `dst_prior_events`, `fail_1h`, `vel_1h`. The LSTM-AE is trained on benign event sequences and yields reconstruction cross-entropy.

#### 3.1.5 Training and evaluation

For RUN 9, `eval_lstm.py` uses `GroupShuffleSplit(test_size=0.3, random_state=42)` with `src_user` as groups, yielding 462 red training and 240 red test rows. The run log identifies train total 24,505,602, validation 14,198,558 rows / 196 red, and held-out test 5,399,886 rows / 240 red in the related overlap split. The RUN 9 comparison reports 136 TP and 183 FP. Threshold selection methodology varies across experiments: RUN 9 evaluation uses a precision-recall threshold sweep maximizing F1 on held-out scores, while the later 13-feature training script describes a nested user-group validation split. Never state that RUN 9’s test threshold was selected without test leakage unless the precise saved run evidence proves it; the code excerpt and log should be presented transparently.

The separate 13-feature script uses outer `GroupShuffleSplit` seed 42 and an inner validation split seed 99; it tunes thresholds on validation. A user-group split protects against the same source user appearing in both partitions, but does not prove transfer to a completely new organization, new identities under different populations, or new attacker tactics. The score parquet contains in-sample and test scores from a full-data scoring pass; its 598/702 count is not held-out performance.

#### 3.1.6 System integration

Flask imports the current `live.scorer`, initializes model and context lazily, serves pages/API, and emits SSE messages. The replay path loads existing score rows and uses the offline model output; it does not recompute each replay event with `score_event`. Employee login and `/api/company/event` use `score_event`; the company simulator also computes a separate demo-profile comparison and overrides displayed decision to ALLOW or FLAG based on field equality.

#### 3.1.7 Tools and technologies

Python; DuckDB; NumPy; pandas; scikit-learn; LightGBM; PyTorch; joblib; Flask; pyotp; PyArrow; JavaScript; HTML/Jinja; CSS; ECharts and Chart.js. `requirements.txt` has minimum versions rather than a lockfile. `bootstrap.sh` supports CPU/GPU PyTorch installation, Git LFS artifacts and dataset checks. The docs recommend Linux/WSL, Python 3.12+, 16 GB RAM and 12 GB free disk for setup; the actual bundled venv is Python 3.14 and importing saved sklearn artifacts produced version warnings (models serialized with sklearn 1.9.0 and loaded under 1.9.1).

### 3.2 Design and implementation

#### 3.2.1 System architecture

```text
LANL auth.txt + redteam.txt
       │ streaming selection / exact label match
       ▼
auth_slice → DuckDB feat table → SQL/window feature generation
       │                         ├─ tabular LightGBM / Isolation Forest
       │                         └─ categorical sequences → LSTM-AE score
       ▼
offline evaluation + serialized model bundles + score parquet
       │                                      │
       │ current live scoring path            └─ replay window (pre-scored)
       ▼                                                  │
Flask pages/APIs ← employee/company demo events             ├─ REST dashboard data
       │                                                  └─ SSE replay feed
       ▼
Browser dashboard, charts, investigation drawer, user baselines
```

#### 3.2.2 Dataset and preprocessing pipeline

The two-pass stream procedure first inventories source users/hosts and red-team matches, then retains selected users. DuckDB loads the compressed slice and red-team table. `01_build_features.py` builds a scratch `feat_rebuild`, compares a set of key/feature columns against existing `feat`, and refuses a mismatch unless `--force`; it then replaces and exports only after the gate. This is a guarded rebuild design, but the verifier compares a limited selected feature list, not every field.

#### 3.2.3 Feature extraction and behavioral profiling

The repository has several feature schemas. The saved `lanl_lgb_21feat.joblib` lists the following in model order:

| # | Feature | Interpretation in code/docs |
|---:|---|---|
| 1 | `dst_first` | First observed user→destination association indicator. |
| 2 | `src_first` | First observed user→source-computer association indicator. |
| 3 | `hour_ratio` | Count of user events in matching hour divided by user event total in the training SQL path. |
| 4 | `dst_prior_events` | Prior events for user/destination or related SQL generation; exact training semantics vary by pipeline version. |
| 5 | `fail_1h` | Recent failed logins. |
| 6 | `vel_1h` | Recent authentication event count. |
| 7 | `hour_sin` | Cyclic encoding of hour. |
| 8 | `hour_cos` | Cyclic encoding of hour. |
| 9 | `is_ntlm` | NTLM indicator. |
| 10 | `pair_first` | First user/source/destination triple indicator. |
| 11 | `src_dst_pair_first` | First source/destination computer pair indicator. |
| 12 | `fail_rate` | Failure count normalized by velocity plus one. |
| 13 | `dst_first_x_ntlm` | Interaction of destination novelty and NTLM. |
| 14 | `log_pair_rank` | Log transformed pair occurrence rank. |
| 15 | `pair_freq_ratio` | Historical pair frequency relative to user total. |
| 16 | `is_rare_hour` | Whether the event time falls in a low-frequency user hour. |
| 17 | `pairs_last_100` | The batch `FEATURE_SQL` shown in `live/db.py` hardcodes this as `0.0`; current scorer computes a distinct-destination count over the last 100 events. This is a serving/training mismatch. |
| 18 | `iat_zscore` | Inter-arrival time normalized by recent user inter-arrival mean/std. |
| 19 | `velocity_ratio` | 1-hour count divided by 24-hour count plus one. |
| 20 | `machine_popularity` | Number of distinct users associated with destination machine. |
| 21 | `lstm_ae_recon_error` | Mean cross-entropy reconstruction loss over six categorical event fields. |

The *current live scorer bundle* has 13 inputs: the first 13 listed above. It still computes 21 values into the event dictionary, but uses only model bundle feature names in the matrix. Do not describe 21 as the number consumed by current live LightGBM. The dashboard investigation endpoint receives replay events whose `features` are empty, so it can state labels/decisions but cannot display actual per-row replay feature contributions. Live employee events have computed feature details.

User-relative baselines are sorted arrays of historical `vel_1h` and `lstm_ae_recon_error` for selected demo users. `baseline_snapshot` calculates percentiles and exposes median/p99. The explanation function suppresses anomaly-tail claims below 20 prior history events and refers to user percentiles; this is explanation context and not a per-user calibrated classifier. Unseen users have no precomputed context and default to sparse state; no evidence establishes robust generalized cold-start scoring.

#### 3.2.4 Model architecture and anomaly scoring

**LightGBM (RUN 9):** gradient-boosted decision trees, binary target `is_red`, 21 numeric inputs. Saved bundle metadata confirms `n_estimators=500`, `num_leaves=63`, `learning_rate=0.03`, `scale_pos_weight=3`, `min_child_samples=100`, `reg_alpha=0.5`, `reg_lambda=5.0`, `random_state=42`. Output is a positive-class probability. Optimizer/loss are internal to LightGBM’s binary classifier; a neural optimizer is not applicable.

**LSTM-AE:** six token categories per event (`src_user`, `src_computer`, `dst_computer`, `auth_type`, `logon_type`, `orientation`); context window 50; embedding/hidden dimension 128; two-layer LSTM encoder and two-layer LSTM decoder, with output projection to vocabulary size 16,874. Train batch 128, inference batch 512, default two epochs, Adam at 0.001, cross-entropy reconstruction loss. Saved checkpoint contains only state dictionary, vocab, offsets, vocabulary size; those training hyperparameters are sourced from training script, not checkpoint metadata. The forward method initializes the decoder from encoder states but feeds embedded input sequence to the decoder (teacher forcing), so it reconstructs the same sequence. Per-event score is average cross-entropy across the event’s six tokens.

**Isolation Forest:** unsupervised randomized isolation trees. The later normal-only 9/13-feature model uses `n_estimators=200`, `max_samples=256`, `random_state=42`, `contamination=1e-7`, StandardScaler, and log transforms on `dst_prior_events`, `fail_1h`, `vel_1h`; calibration target FPR is 1e-4. Its saved report evaluates a 200,000-row normal training sample, 50,000-row normal calibration sample, and 702 red-team rows. This sampled evaluation is not comparable to full-population PR-AUC.

#### 3.2.5 Training and evaluation workflow

RUN 9’s relevant 21-feature bundle is present. The `eval_lstm.py` script loads score arrays and features, performs user-group split seed 42, trains LightGBM, computes test metrics and optionally saves the model. Train features include `lstm_ae_recon_error` produced by `src/05_lstm_autoencoder.py`. Experiment notes report RTX 3050, approximately 80 minutes for the AE training and around 13–21 minutes for evaluation runs, but these are historical log statements, not reproduced in this inspection. No complete training/validation/test artifact set accompanies all model bundles.

### 3.3 Summary

The reproducible research path is LANL stream → selected user cohort → DuckDB event features → sequence score and tabular model → split-specific evaluation → saved artifacts. The web demo is an integration of two paths (pre-scored replay and current 13-input live scorer); document this explicitly.

## Chapter 4: Project testing

### 4.1 Introduction

Tests include browser-driven smoke/audit scripts, model/feature verification scripts and a blind-event experiment. They are not a conventional isolated unit-test suite; several require a running Flask app, Playwright/Chromium and the missing raw database.

### 4.2 Tools

Python AST parser was used to syntax-parse project Python sources. DuckDB in the project virtual environment was used for read-only parquet verification. `test_live.py` imports Playwright and exercises Flask HTTP/browser endpoints. `live/test_audit.py` creates screenshot files and writes an audit report if it reaches completion; it was not run because the app cannot be initialized from the absent raw database and Playwright is absent.

### 4.3 Dataset and algorithm details

The setup verification script checks raw database size/opens `feat`, red-team count, model files and score parquet. Current checkout lacks `data/raw/lanl/lanl.duckdb`, `redteam.txt`, and several raw files, so bootstrap verification cannot pass. The score parquet itself is present and readable.

### 4.4 Software testing

#### 4.4.1 Types

Static syntax parse; parquet artifact verification; HTTP/API smoke checks; browser render and interaction audit; model checkpoint/loading/feature/scoring verification; blind-event evaluation harness. The test files themselves were inspected, but only checks actually run in this inspection are marked executed.

#### 4.4.2 Test cases and results

| Test ID | Test description | Expected result | Actual result | Status | Evidence |
|---|---|---|---|---|---|
| V-01 | Parse project Python files with `ast.parse` | All parse | 31 files parsed, no syntax errors | PASS | Command recorded in `verification_and_evidence.md`. |
| V-02 | Read score parquet and inspect row/label counts | 29,905,488 rows, 702 red labels | Exact match | PASS | Direct DuckDB query, documented there. |
| V-03 | Verify curated replay label/decision/FP counts from score artifact | 9,954 rows; 20 red; 20 flagged; 12 normal flagged | 9,954; 20; all 20 FLAG/BLOCK; 12 normal BLOCK | PASS | Direct DuckDB query; replay code defines interval. |
| V-04 | Run `venv/bin/python test_live.py` | API/browser tests execute | Fails immediately importing `playwright`; no endpoint test ran | BLOCKED | Captured `ModuleNotFoundError`. |
| V-05 | Full Playwright audit | Pages/interactions complete | Not run: Playwright absent, server/raw DB unavailable | NOT RUN | `live/test_audit.py` preconditions. |
| V-06 | Model load metadata inspection | Bundles/checkpoints inspect | Loaded; sklearn 1.9.0→1.9.1 compatibility warnings emitted | PASS WITH WARNING | Read-only `joblib.load`/`torch.load`. |
| V-07 | Bootstrap / live server smoke | Dataset, models, API start | Not run: raw DuckDB and `redteam.txt` absent; smoke suite also lacks Playwright | NOT RUN | Current file inventory and `bootstrap.sh`. |
| V-08 | Full training / full data regeneration | Reproducible training | Not run, expensive and source DB absent | NOT RUN | Commands documented; no mutation performed. |

### 4.5 Summary

The available offline output is verifiable and source files syntax-parse. Application behavior was not exercised. Tests in the report must not be described as passed based on source inspection alone.

## Chapter 5: Results and discussion

### 5.1 Overview

Results below distinguish stored score artifact, curated replay, held-out model experiment and sampled IF experiment. They have different populations and should not be combined into one accuracy claim.

### 5.2 Dataset analysis

| Statistic | Value | Evidence quality |
|---|---:|---|
| Auth rows in shipped scores | 29,905,488 | Independently counted in parquet. |
| Red labels in score artifact | 702 | Independently counted in parquet. |
| Distinct source users | 604 | Independently counted in parquet. |
| Distinct destination users | 5,658 | Independently counted in parquet. |
| Distinct source computers | 8,162 | Independently counted in parquet. |
| Distinct destination computers | 8,085 | Independently counted in parquet. |
| Source authentication stream | 1,051,430,459 rows | Script/doc figure; raw archive unavailable for recount. |
| LANL redteam file rows | 749 | Source comments/docs; selected cohort has 702 matched event labels. |
| Selected users | 104 red-team + 500 normal = 604 | Sampling logic and output distinct count. |

### 5.3 Model performance metrics

#### RUN 9: 21-feature LightGBM, held-out user-group test (reported)

| Metric | Value | Interpretation |
|---|---:|---|
| ROC-AUC | 0.999920 (rounded 0.9999) | Ranking red events above normal events over all thresholds; highly sensitive to large negative class and near-saturated here. |
| PR-AUC / average precision | 0.368241 (rounded 0.3682) | Precision-recall ranking summary; more informative under severe class imbalance. Random baseline is positive prevalence (~240 / 5,399,886 = 0.0000445). |
| TP / red recall | 136 / 240 = 56.67% | Red events at the saved selected threshold. |
| FP | 183 | Normal events at/above threshold. |
| FN | 104 | Red events below threshold. |
| TN | 5,399,463 | Derived from stated test total 5,399,886, 240 reds, 183 FP. |
| Precision | 136 / (136+183) = 42.63% | Fraction of alerts that are red labels. |
| F1 | 0.4866 | Harmonic mean of precision and recall. |
| FPR | 183 / 5,399,646 = 0.00339% | False alerts divided by normal test events. |
| Threshold | 0.1871951071 | Stored in 21-feature bundle and score parquet. |

Confusion matrix (event decision at the recorded block threshold):

| | Predicted red | Predicted normal |
|---|---:|---:|
| Red label | TP 136 | FN 104 |
| Normal/unlabeled | FP 183 | TN 5,399,463 |

The test label “normal” here means “not labelled red-team,” not proven benign. The report’s `183 / 5,399,886` phrasing is a denominator mismatch: 5,399,886 is total test rows; 5,399,646 is the implied non-red count. The confusion values yield the stated F1 when rounded.

#### Shipped full score parquet (not held out)

At score `>=0.1871951071`: TP=598, FP=269, FN=104, TN=29,904,517. This corresponds to red-label recall 85.19%, precision 68.98%, F1 approximately 0.761, and FPR approximately 0.00090%. **This is a full-dataset score artifact and includes training rows; it is not a held-out test result.** The score parquet also has 11 red and 103 non-red events in FLAG (score between 0.7 threshold and block threshold) and 93 red events in ALLOW. If operational positive means either FLAG or BLOCK, the stored decision columns yield 609 red flagged and 372 non-red flagged. The docs’ “598 caught” uses the BLOCK threshold only.

#### Curated replay (time range 765000–767000)

| Item | Count |
|---|---:|
| Replay events | 9,954 |
| Confirmed red labels | 20 |
| Red at FLAG/BLOCK | 20 (19 BLOCK + 1 FLAG) |
| Normal at BLOCK | 12 |
| Normal at FLAG | 0 |
| Missed red events | 0 |

This window was selected because it contains a known lateral-movement burst associated with source machine C17693. It is curated and overlaps the full scored dataset; the 20/20 result is not an unbiased test estimate or “100% accuracy.”

#### Other available results

| Experiment / artifact | Metrics and scope |
|---|---|
| `reports/both_report.json` | Early split is explicitly described as leaking 97% red users across train/test. IF PR-AUC .0063, ROC-AUC .9887, F1 .0401, TP 7, FP 131; LGB PR-AUC .0153, ROC-AUC .8470, F1 .0440, TP 136, FP 5,833; combined F1 .1012. Holdout C17693 ROC-AUC ~.576. Do not present as unbiased generalization. |
| Normal-only IF, 9 feature report | 200,000 normal train, 50,000 normal calibration, 702 red eval, target/observed calibration FPR 1e-4, red recall .04416. Sample PR-AUC .6026 and ROC-AUC .9908 are on a sampled mixture and explicitly not population estimates. |
| Normal-only IF, 13 feature report | Same sample sizes/target FPR; red recall .07265; sample PR-AUC .62994, ROC-AUC .99224; sampled mixture, not population estimate. |
| RUN 9 LSTM-AE standalone | ROC-AUC .9425, F1 .0095, TP 118, FP 24,482 (reported); ranking signal does not yield useful alert threshold. |
| RUN 10 LGB-37 | F1 .4772; TP 157, FP 261; PR-AUC .3752 in log; metrics vary in repeated non-deterministic SQL runs. |
| RUN 11 LGB-23 | F1 .4735, PR-AUC .3625, TP 143, FP 221. |
| RUN 12 final (IF score as feature) | F1 .4819, TP 140, FP 201; log states deterministic single-thread configuration. |

Accuracy: not reported for the selected RUN 9, and deliberately not emphasized. Score distributions: the score parquet’s direct inspected range is ~1.38e-8 to 0.99349; distribution quantiles/plots were not generated in this inspection. The demo example score `3.35e-8` appears in `DEMO_TLDR.md` only and could not be tied to a retained event/log; do not present it as independently reproduced.

### 5.4 Confusion matrix and evaluation caveats

Precision = TP/(TP+FP); recall/detection rate = TP/(TP+FN); F1 = 2PR/(P+R); FPR = FP/(FP+TN). ROC-AUC integrates TPR against FPR; PR-AUC summarizes precision versus recall. TN is inferred for the held-out confusion matrix from row totals and must be labeled derived. AUC values are from stored bundle/log, not recomputed here because held-out score arrays are not available as a separate artifact.

### 5.5 Red-team and replay evaluation

`redteam.txt` records 749 malicious authentication actions; the project exact-matches tuple fields to selected auth rows and finds 702 event labels in `feat`. `live/replay.py` uses inclusive `time BETWEEN 765000 AND 767000`, loads stored predictions/labels from `lanl_scores.parquet`, joins auth type/logon type/result from `lanl.duckdb`, then maps score decision to lowercase for the app. The score parquet audit independently confirms 9,954 rows, 20 red labels, 20 flagged and 12 normal BLOCK. The live replay route emits those prerecorded events at configured speed; it does not recalculate them through the live scorer.

### 5.6 Live monitoring results

The current source computes on-demand features and calls LightGBM per event. No running Flask server was available, Playwright is not installed, and raw DuckDB is absent. Therefore current live score, latency, API response behavior, SSE flow and threshold performance were not runtime-verified. Any single demo number in README/demo notes is historical unless independently reproduced.

### 5.7 Explainability and behavioral baselines

The live explanation uses event features plus user-specific velocity and LSTM-error percentiles. It emits a cold-start explanation when historical user count <20, hides reasons from SSE for events with the `normal_profile` basis, and describes the model score rather than explaining feature attribution. Replay investigation uses empty event features, so replay “feature contribution” view cannot be treated as actual per-event LightGBM attribution. Feature importance API is global gain importance, not per-event explanation.

### 5.8 Performance and reliability

Historical experiment logs report about 57 seconds to score 29.9M rows in one full-dataset run and around 19 ms live event scoring in an older description. These timings are not remeasured. Current `score_event` opens a DuckDB connection and runs a filtered SQL aggregation per event, then runs CPU PyTorch inference; expected production throughput and concurrency remain unverified. The app keeps live state in process memory and does not persist demo events across restart.

### 5.9 Comparative analysis

RUN 9 improved F1 modestly over 20-feature LightGBM (0.4817→0.4866) and reduced FP (217→183) while catching fewer positives (145→136), according to the log. LSTM-AE reconstruction as a feature was more useful than standalone thresholding. IF-as-feature, latent PCA and smoothed-AE variants did not improve the selected F1 in recorded experiments. Early model comparisons are contaminated by split leakage and should be separated from later user-grouped runs.

### 5.10 Discussion

The central positive result is strong score ranking and measurable red-team recall on a user-held-out test set, coupled with a low absolute FPR. The operational precision is still roughly 43% at the selected threshold in the rare-class held-out population; the analyst workflow must handle false alerts. The curated replay is useful for demoing chronology and UI, but its selected attack-heavy window cannot support a population-level detection claim. A major engineering risk is feature/model drift between batch training and current live inference, compounded by contradictory API metadata and smoke assertions.

## Chapter 6: Conclusion

### 6.1 Conclusion

The repository implements an end-to-end experimental LANL identity anomaly pipeline: source-user cohort selection, SQL feature generation, supervised and unsupervised model experiments, sequence reconstruction, saved score artifacts, Flask APIs, event replay, demo authentication and analyst UI. The best documented held-out result is RUN 9’s 21-feature LightGBM: PR-AUC .3682, F1 .4866, 136/240 red detections and 183 false positives at threshold .1872. The result is properly understood as a split-specific research evaluation, not production efficacy.

### 6.2 Limitations

Labels are sparse and incomplete; only 702 selected events have red labels. The sample excludes most users. Some earlier results use leaked splits. A score parquet generated over all rows is in-sample in part. Batch and serving feature definitions differ (`pairs_last_100` is an obvious example), and live model has 13 rather than 21 inputs. The 13-feature bundle’s stored ROC-AUC .999257 does not come with equivalent full metrics in its current metadata. Current environment misses raw source DB and Playwright. Baselines cover four demo users; general identity cold-start has not been evaluated. Hard-coded demo credentials and LANL_DEV bypass preclude production deployment. Version-pinned dependencies, comprehensive unit tests and retained evaluation arrays are absent.

### 6.3 Future work

1. Unify one versioned feature function for training, batch scoring and serving; assert feature names, order, data ranges and expected decision semantics.
2. Re-run evaluation with strictly user-grouped splits and a second holdout by attacker/host/time; publish scores and split manifests.
3. Choose threshold using validation data only and report recall at explicit false-alert budgets and precision at top-K.
4. Evaluate past-only temporal features and graph/path signals (destination diversity, auth path length, credential switching, peer deviation) without future leakage.
5. Add testable model bundle metadata, dependency lockfile and synthetic fixtures; execute app/API/browser tests in CI.
6. Replace demo passwords and bypass with environment secrets, secure session/cookie settings, rate limiting, CSRF controls and a clearly isolated development configuration before any deployment.
7. Measure cold-start, sustained event throughput, memory, concurrent clients and restart behavior.
8. Add missing labeled datasets and privacy/governance review before claiming real-world transfer.

## Architecture and workflow details for report diagrams

### End-to-end processing

```text
Acquire LANL archive → stream count/match → sample 500 non-red users
→ retain red-user events + selected normal-user events
→ DuckDB raw table + red-team labels
→ engineer tabular/window features
→ train LSTM-AE on benign sequences; score event reconstruction error
→ append AE score to tabular matrix
→ user-group train/test split; fit LightGBM; select score threshold
→ export model bundle and per-row parquet scores
→ Flask loads live model/context; browser receives APIs/SSE
→ analyst replays stored scored window and inspects outcomes
```

### Authentication workflow

```text
Login form → authenticate(username,password,TOTP)
→ constant-time password compare → TOTP verify with ±1 time step
→ session role employee / analyst → role-gated pages/APIs
```

Generated TOTP secrets are stored in `live/.totp_secrets.json` on first use. `LANL_DEV` surfaces demo passwords/codes and grants analyst role to analyst-gated requests; it must remain a local-only demo flag.

### Figure and screenshot inventory

| Suggested figure | Caption / contents | Current asset | State |
|---|---|---|---|
| Figure 1 | End-to-end system architecture | `live/static/lanl-ueba-architecture.html`, matching JSON in `docs/` and `live/static/` | Existing diagram; inspect diagram semantics against implementation before use. |
| Figure 2 | LANL slice generation and labeling workflow | None | Create as report diagram. |
| Figure 3 | Feature families and 9→13→20→21 model schema evolution | None | Create; show current 13-feature live scorer separately. |
| Figure 4 | LSTM-AE tokenization, 50-token context, encoder/decoder, cross-entropy score | None | Create based on `src/05_lstm_autoencoder.py`. |
| Figure 5 | Grouped training/validation/test process and threshold selection | None | Create from evaluation script; explicitly flag RUN 9 threshold methodology. |
| Figure 6 | Runtime live sign-in scoring sequence | None | Create; distinguish live 13-input scoring from parquet replay. |
| Figure 7 | Per-user baseline percentile explanation and cold-start branch | None | Create from `app.py` / `scorer.py`. |
| Figure 8 | TOTP authentication and role gate | None | Create from current auth routes. |
| Figure 9 | Curated replay event timeline and confusion summary | None | Create only from score parquet; label it curated 9,954-event window. |
| Figure 10 | Held-out confusion matrix / PR curve | No retained figure or held-out arrays found | Placeholder; use tabulated logged metrics until arrays/plot are produced. |
| Figure 11 | Browser screenshots (login, analyst dashboard, dataset page, employee outcome) | No project screenshot assets found | Placeholder; current test scripts generate images only when dependencies/server work. |

## REFERENCES

1. Melissa J. M. Turcotte, Alexander D. Kent, and Curtis Hash. “Unified Host and Network Data Set.” In *Data Science for Cyber-Security*, 2018, pp. 1–22. DOI: [10.1142/9781786345646_001](https://doi.org/10.1142/9781786345646_001). Official LANL dataset page: [Cyber Security Research data release](https://lanl.ma.ic.ac.uk/data/2017/).
2. Alexander D. Kent, Lorie M. Liebrock, and Joshua C. Neil. “Authentication graphs: Analyzing user behavior within an enterprise network.” *Computers & Security* 48 (2015), 150–166. DOI: [10.1016/j.cose.2014.09.001](https://doi.org/10.1016/j.cose.2014.09.001).
3. Grant Ho et al. “Hopper: Modeling and Detecting Lateral Movement.” *30th USENIX Security Symposium* (2021), 3093–3110. [USENIX paper](https://www.usenix.org/conference/usenixsecurity21/presentation/ho).
4. Fei Tony Liu, Kai Ming Ting, and Zhi-Hua Zhou. “Isolation Forest.” *2008 Eighth IEEE International Conference on Data Mining*, 413–422. DOI: [10.1109/ICDM.2008.17](https://doi.org/10.1109/ICDM.2008.17).
5. Guolin Ke et al. “LightGBM: A Highly Efficient Gradient Boosting Decision Tree.” *Advances in Neural Information Processing Systems 30* (2017). [Proceedings](https://papers.nips.cc/paper/2017/hash/6449f44a102fde848669bdd9eb6b76fa-Abstract.html).
6. Min Du et al. “DeepLog: Anomaly Detection and Diagnosis from System Logs through Deep Learning.” *ACM CCS* (2017). DOI: [10.1145/3133956.3134015](https://doi.org/10.1145/3133956.3134015). Use only as sequence anomaly detection context; implementation is not DeepLog.
7. LANL. *Comprehensive, Multi-Source Cyber-Security Events* dataset description / Cyber1 release. [LANL dataset page](https://csr.lanl.gov/data/cyber1/). Cite release LA-UR-15-23810 where required by the official release metadata.
8. Flask documentation. [Flask documentation](https://flask.palletsprojects.com/).
9. DuckDB documentation. [DuckDB documentation](https://duckdb.org/docs/).
10. PyTorch documentation. [PyTorch documentation](https://pytorch.org/docs/stable/index.html).
11. LightGBM documentation. [LightGBM documentation](https://lightgbm.readthedocs.io/).
12. scikit-learn documentation. [IsolationForest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html), [GroupShuffleSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupShuffleSplit.html), and [evaluation metrics](https://scikit-learn.org/stable/modules/model_evaluation.html).

## Appendix A: Reproducibility commands

Dataset rebuild from the original archive (expensive; not run here):

```bash
unzip -p ~/Downloads/archive.zip auth.txt/auth.txt | venv/bin/python src/00_build_slice.py count
unzip -p ~/Downloads/archive.zip auth.txt/auth.txt | venv/bin/python src/00_build_slice.py slice
venv/bin/python src/00_build_slice.py load
venv/bin/python src/01_build_features.py
venv/bin/python src/02_feature_probe.py
```

The docs’ stated bootstrap prerequisite is a locally supplied `lanl.duckdb.zst` / `lanl.duckdb`; current checkout lacks both. Full data/training commands should only be run after restoring source data and choosing non-overwriting output paths.
