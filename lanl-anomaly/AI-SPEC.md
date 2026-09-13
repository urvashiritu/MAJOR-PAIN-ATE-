# AI-SPEC: LANL Insider Threat Detection System

## 1. System Overview

**System Type:** Hybrid (Anomaly Detection + Supervised Classification)
**Architecture:** Dual-model ensemble — Isolation Forest (unsupervised anomaly) + LightGBM (supervised gradient boosting), combined via weighted score fusion
**Dataset:** LANL Cyber-1 Corpus — 29,905,488 authentication events, 702 red team attacker users, 604 unique source users, ~58 days of de-identified enterprise network data
**Training Split:** GroupShuffleSplit(random_state=42, groups=src_user) — 462 train red / 240 test red events

---

## 1b. Domain Context

**Industry Vertical:** Cybersecurity / Government & National Laboratory Operations
**User Population:** Security Operations Center (SOC) analysts, threat hunters, insider threat program managers at enterprise-scale organizations (especially government, defense, energy, and critical infrastructure)
**Stakes Level:** Critical — undetected insider threats can result in catastrophic data exfiltration, intellectual property theft, sabotage of critical infrastructure, and national security compromise. The LANL dataset specifically models a real national laboratory environment.
**Output Consequence:** Every flagged anomaly triggers analyst investigation workflow — high false positive rates cause alert fatigue and missed true threats; false negatives mean active insider threats go undetected during the investigation window.

### What Domain Experts Evaluate Against

**Dimension: Detection Recall at Bounded False Positive Rate**
Good: System detects ≥85% of red team attacker users while maintaining FPR ≤5% — analysts see manageable alert volume with actionable signals
Bad: System achieves 99% recall but at 30% FPR — generates thousands of false alerts daily, analysts stop trusting the system within days
Stakes: Critical
Source: Insider threat detection practitioners consistently report that alert fatigue is the #1 reason UEBA deployments fail; Spycloud 2025 report: 56% of organizations experienced insider threat incidents, but 77% lack confidence in their detection capabilities due to false positive overload

**Dimension: Temporal Attack Coverage**
Good: System detects attack campaigns across the full timeline — early reconnaissance, lateral movement, and exfiltration phases are all represented in alerts
Bad: System only detects exfiltration events (high-volume data transfers) but misses the low-and-slow reconnaissance phase where insiders are mapping the network
Stakes: High
Source: LANL red team scenarios include multi-phase attacks; the 702 red events span privilege abuse, identity theft, and data leakage — missing early phases means no time for preventive intervention

**Dimension: User-Level Generalization**
Good: System performs consistently across different attacker users — no single attacker user dominates all detections while others go undetected
Bad: System catches attacker C17693 perfectly but misses U500 entirely — the model overfit to specific attack signatures rather than detecting behavioral anomalies
Stakes: High
Source: The project's GroupShuffleSplit by src_user is specifically designed to prevent this; the holdout evaluation on C17693 tests generalization to unseen attacker patterns

**Dimension: Explainability for Analyst Triage**
Good: When an alert fires, the system can show which features (velocity spike, unusual destination, rare-hour access, first-time machine connection) contributed most to the anomaly score
Bad: System produces a single numeric score with no feature attribution — analyst has no starting point for investigation and must manually correlate all logs
Stakes: Medium
Source: SHAP/LIME explanations are standard in production UEBA (OpenUBA, Exabeam, Splunk UBA all provide feature-level attribution); SOC analyst workflows require investigation starting points

**Dimension: Temporal Consistency & Stability**
Good: Model scores are stable — same user's risk score doesn't wildly oscillate hour-to-hour without corresponding behavioral changes
Bad: Score jumps from 0.1 to 0.9 between consecutive time windows due to rolling window boundaries, creating phantom anomalies
Stakes: Medium
Source: PMC research (2025) found week-granularity aggregation achieves optimal stability (P=0.9997, R=0.9997, F1=0.9997) while session-level granularity is "more sensitive to transient behaviors, leading to potential instability"

### Known Failure Modes in This Domain

1. **Class Imbalance Collapse:** 702 red events in 29.9M total (0.00235% positive rate) — naive models achieve 99.99% accuracy by predicting all-normal, completely missing the threat. The project uses scale_pos_weight=3 and FPR-constrained threshold tuning to combat this.

2. **Domain Shift (Synthetic → Real):** CERT synthetic datasets produce models that fail on LANL real-world data. Planton361's zero-shot transfer study shows that models trained on CERT r5.2 authentication logs suffer significant performance degradation when applied to LANL without adaptation — drift metrics show distributional shift in feature spaces.

3. **Concept Drift:** Insider behavior evolves — attackers adapt tactics after initial access. Static models trained on historical data degrade over time as new attack patterns emerge. Production UEBA systems require continuous retraining pipelines.

4. **Feature Leakage via Temporal Proxies:** Features like `dst_prior_events` or `vel_1h` can leak label information if not carefully constructed — the project's deterministic 9-column ORDER BY ensures features are computed causally (only using information available at or before each event's timestamp).

### Regulatory / Compliance Context

- **NIST SP 800-53 (AU-6, AC-6):** Audit review, analysis, and reporting requirements; least privilege enforcement — detection systems must support audit trails and demonstrate coverage of privileged user monitoring
- **NIST SP 800-82 (ICS Security):** Critical infrastructure specific requirements — insider threat detection for operational technology environments with additional safety constraints
- **CMMC Level 2-3:** Cybersecurity Maturity Model Certification requires insider threat programs for defense contractors — detection capabilities must be documented and demonstrable
- **EO 14028 (Improving Cybersecurity):** Federal agencies must implement insider threat detection capabilities — LANL, as a DOE national lab, operates under this mandate
- **GDPR (Art. 5, 6):** If deployed in EU contexts — behavioral monitoring of employees requires legitimate interest basis and data minimization; anomaly scoring must be proportionate to the security objective
- **No specific prohibition on ML-based insider threat detection** — but systems must maintain human-in-the-loop for any consequential decisions (employment actions, access revocation)

### Domain Expert Roles for Evaluation

| Role | Responsibility in Eval |
|------|----------------------|
| SOC Analyst (Tier 1-2) | Alert triage workflow testing — can they investigate flagged anomalies effectively? Is the alert volume manageable? |
| Insider Threat Program Manager | Scenario coverage validation — do detections map to known threat scenarios (privilege abuse, data leakage, identity theft)? |
| Threat Hunter | Adversarial testing — can they find detection gaps by simulating novel attack patterns not in training data? |
| Compliance Officer | Regulatory alignment — does the system maintain required audit trails and demonstrate coverage of privileged user monitoring? |
| Data Engineer | Pipeline reliability — does the feature computation pipeline produce consistent results across retraining cycles? |
| Security Architect | Integration validation — do detection outputs integrate with SIEM/SOAR workflows and incident response playbooks? |

### Research Sources

- **LANL Cyber-1 Dataset:** https://csr.lanl.gov/data/cyber1 — 58 days of de-identified authentication, process, DNS, HTTP, and flow data with red team ground truth
- **"A Reproducible Empirical Study on the LANL cyber1 Corpus"** (SSRN, 2025) — multi-source behavioral-anomaly benchmark for insider threat detection on LANL
- **"Insider threat detection for specific threat scenarios"** (ResearchGate, 2024) — achieved 98.70% accuracy on CERT, 97.90% on LANL, 98.30% on TWOS with F1-scores 97.35-98.25%
- **Planton361/cert2lanl-zero-shot-transfer** (GitHub) — zero-shot transfer study from CERT to LANL with drift and capacity-constrained model analysis
- **"Enhancing Insider Threat Detection Using User-Based Sequencing and Transformer Encoders"** (arXiv 2506.23446, 2025) — Transformer + iFOREST achieves F1=0.9638 on combined CERT datasets
- **"Research on insider threat detection based on personalized federated learning"** (PMC, 2025) — week-granularity federated learning achieves P/R/F1=0.9988-0.9997
- **OpenUBA** (GitHub, 518 stars) — production-grade open-source UEBA framework with Kubernetes-native architecture
- **lcd-dal/feature-extraction-for-CERT-insider-threat-test-datasets** (GitHub, 112 stars) — established CERT feature extraction with sample classification/anomaly detection code
- **"Is F1 Score Suboptimal for Cybersecurity Models?"** (arXiv 2407.14664, 2024) — argues for cost-sensitive metrics over F1 in imbalanced security domains

### Comparison: Reported Results on CERT/LANL Datasets

| Approach | Dataset | Accuracy | Precision | Recall | F1 | AUC | Notes |
|----------|---------|----------|-----------|--------|-----|-----|-------|
| Transformer + iFOREST | CERT r4.2 | 0.9900 | 0.9859 | 1.0000 | 0.9929 | 1.0000 | Best single-model result on CERT r4.2 |
| Transformer + iFOREST | CERT (all combined) | 0.9661 | 0.9351 | 0.9943 | 0.9638 | 0.9500 | Cross-version generalization |
| DS-IID | CERT r4.2 | 0.9710 | 0.9600 | 0.9500 | 0.9550 | — | Dual-stage detection |
| Federated Learning (week) | CERT r4.2 | — | 0.9997 | 0.9997 | 0.9997 | — | Privacy-preserving, week granularity |
| SVM + SMOTE | CERT r4.2 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | — | Supervised with balancing |
| CNN (image-based) | CERT r4.2 | 0.9900 | 0.9929 | 0.9932 | 0.9930 | — | 20-dim vectors as 32x32 images |
| LightGBM + IF (this project) | LANL cyber1 | — | TBD | TBD | TBD | — | Dual-model ensemble on real-world data |
| ITDSTS | CERT+LANL+TWOS | 98.70% | — | — | 97.35-98.25% | — | Multi-dataset, scenario-specific |
| RedChronos (LLM) | CERT r4.2 | 0.9790 | 0.9330 | 0.9870 | — | — | LLM-based prompt fusion with genetic algorithm |

**Key Insight:** Results >99% F1 on CERT r4.2 are common in literature, but these often don't transfer to LANL real-world data. The most meaningful benchmark is performance on LANL specifically, where the cert2lanl transfer study shows significant domain shift degradation.

---

## 2. Feature Engineering

### 20-Feature Configuration (Config E — Best from exp2.py)

| # | Feature | Type | Description | Domain Rationale |
|---|---------|------|-------------|------------------|
| 1 | dst_first | Binary | First-ever connection to this destination machine | Novel destination = reconnaissance indicator |
| 2 | src_first | Binary | First-ever event from this source computer | New source machine = potential lateral movement |
| 3 | hour_ratio | Continuous | Events this hour / total user events | Temporal concentration anomaly |
| 4 | dst_prior_events | Count | Prior events to this destination (cumulative) | Established vs novel destination relationship |
| 5 | fail_1h | Count | Failed authentications in last hour | Brute force / credential stuffing indicator |
| 6 | vel_1h | Count | Authentication velocity in last hour | Volume spike = potential credential harvesting |
| 7 | hour_sin | Cyclical | sin(hour/24 * 2π) | After-hours access detection |
| 8 | hour_cos | Cyclical | cos(hour/24 * 2π) | After-hours access detection |
| 9 | is_ntlm | Binary | NTLM authentication type | Credential relay risk indicator |
| 10 | pair_first | Binary | First user→machine pair event | Novel access path |
| 11 | src_dst_pair_first | Binary | First src_computer→dst_computer pair | New network path |
| 12 | fail_rate | Continuous | fail_1h / (vel_1h + 1) | Attack intensity ratio |
| 13 | dst_first_x_ntlm | Interaction | dst_first × is_ntlm | Novel destination + credential relay |
| 14 | log_pair_rank | Continuous | log1p(row_number within user→machine pair) | Pair familiarity progression |
| 15 | pair_freq_ratio | Continuous | pair_events / user_total_events | Relationship concentration |
| 16 | is_rare_hour | Binary | Hour in bottom 20% of user's distribution | Unusual timing for this specific user |
| 17 | pairs_last_100 | Count | Distinct destinations in last 100 events | Lateral movement breadth |
| 18 | iat_zscore | Continuous | (time_since_last - mean) / std over 100-window | Inter-arrival time anomaly |
| 19 | velocity_ratio | Continuous | auth_count_1h / (auth_count_24h + 1) | Short-term vs long-term velocity |
| 20 | machine_popularity | Count | Distinct users accessing this machine | Shared infrastructure vs personal machine |

---

## 3. Model Architecture

### Dual-Model Ensemble

**LightGBM (Supervised)**
- Objective: Binary classification with FPR-constrained threshold tuning
- Key params: num_leaves=63, lr=0.03, n_estimators=500, scale_pos_weight=3
- Threshold: Optimized for F1 within 5% FPR budget via precision-recall curve
- Strength: Learns attacker behavioral patterns from labeled red team data

**Isolation Forest (Unsupervised)**
- Objective: Anomaly detection — score deviations from normal behavioral distribution
- Key params: n_estimators=200, contamination=702/29.9M, max_samples=256
- Preprocessing: log1p transform on count features, StandardScaler normalization
- Strength: Catches novel attack patterns not seen in training labels

**Combined Score**
- Formula: 0.5 × LGB_score + 0.5 × IF_score
- Rationale: Supervised model catches known patterns; unsupervised model catches novel anomalies

---

## 4. Evaluation Strategy

### Primary Metrics
- **PR-AUC (Precision-Recall Area Under Curve):** Primary metric for imbalanced classification — captures performance across all threshold settings
- **ROC-AUC:** Secondary metric — less informative for extreme imbalance but widely reported for benchmarking
- **F1 at FPR ≤ 5%:** Operational metric — the threshold-tuned F1 score within the false positive budget
- **Precision, Recall, FPR at operating threshold:** Direct operational metrics

### Evaluation Protocol
- **GroupShuffleSplit by src_user:** Prevents data leakage — same user's events never appear in both train and test
- **Holdout attacker evaluation:** C17693 held out as unseen attacker for generalization testing
- **Deterministic ordering:** 9-column ORDER BY ensures reproducible feature computation and train/test splits

---

## 5. Production Considerations

### Latency Requirements
- Real-time scoring: <100ms per event for live alerting
- Batch scoring: Full dataset retraining must complete within maintenance windows

### Reliability
- Model artifacts serialized via joblib with metadata (features, thresholds, metrics)
- Deterministic computation ensures reproducible results across retraining cycles
- Feature pipeline uses DuckDB with explicit thread/memory limits for consistency

### Scalability
- Current: 29.9M events fits in memory (requires ~6GB RAM)
- Production: Must handle enterprise-scale logs (billions of events) via streaming feature computation
