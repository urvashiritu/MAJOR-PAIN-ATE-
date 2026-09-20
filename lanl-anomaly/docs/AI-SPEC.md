# AI-SPEC: LANL Anomaly Detection System

## 1b. Domain Context

**Industry Vertical:** Cybersecurity / Insider Threat Detection  
**User Population:** SOC analysts, threat hunters, and security operations teams monitoring enterprise authentication logs for compromised credentials  
**Stakes Level:** High  
**Output Consequence:** Failed detection of a compromised account enables lateral movement, data exfiltration, or sabotage; excessive false positives create alert fatigue and cause analysts to ignore real threats

### What Domain Experts Evaluate Against

**Dimension: Temporal behavioral consistency**  
Good: Detection system flags authentication events that deviate from a user's established pattern — unusual time-of-day, unusual source host, unusual destination  
Bad: System flags all activity from a user without distinguishing anomalous sequences from normal routine access  
**Stakes:** Critical  
**Source:** Insider threat detection literature — red team exercises at LANL demonstrate that compromised credentials produce subtle behavioral shifts, not obvious anomalies

**Dimension: Cross-dimensional anomaly coherence**  
Good: Anomaly score reflects patterns across multiple tensor dimensions (user × source × destination × time) simultaneously, catching coordinated deviations  
Bad: Anomaly score treats each authentication event independently, missing multi-hop attack patterns where the anomaly spans several dimensions  
**Stakes:** High  
**Source:** Tensor factorization approach (HLSF paper, Eren et al.) — the key insight is that threat signals are distributed across relational structure, not isolated to single events

**Dimension: Precision-recall under extreme class imbalance**  
Good: System maintains meaningful precision at top-ranked alerts — the first 10–20 flagged events contain real threats, not noise  
Bad: System achieves high recall by flagging everything, burying true anomalies in a flood of benign alerts  
**Stakes:** High  
**Source:** LANL red team dataset contains ~76–119 anomalies out of 31K–125K events (0.06–0.6% prevalence) — ROC-AUC alone is misleading; PR-AUC and early-retrieval precision are the operative metrics

**Dimension: Structural anomaly interpretability**  
Good: System provides latent factor decomposition that maps anomalies to specific user–source–destination relationships, enabling analysts to understand *why* an event is flagged  
Bad: System outputs a single anomaly score with no explanation of which behavioral dimensions contribute to the flag  
**Stakes:** Medium  
**Source:** SOC operational practice — analysts who cannot interpret alert rationale distrust the system and eventually disable it

**Dimension: Robustness to tensor rank selection**  
Good: System performs consistently across a reasonable range of tensor ranks (e.g., rank 4–20), with graceful degradation  
Bad: Performance collapses when rank is slightly mis-specified, requiring expert tuning for each dataset  
**Stakes:** Medium  
**Source:** CP-APR literature — rank is a hyperparameter that practitioners must set; automatic rank determination (as in T-ELF) is preferred but not always available

### Known Failure Modes in This Domain

1. **Temporal granularity mismatch**: Building tensors at the wrong time granularity (e.g., per-event vs. per-day) produces either too sparse or too dense representations, degrading factorization quality. The HLSF paper shows that hour-of-day inclusion significantly improves detection.

2. **Rare-event drowning in PR-AUC**: Even strong models achieve very low PR-AUC (0.003–0.057 on LANL) because the anomaly fraction is vanishingly small. ROC-AUC scores above 0.9 can mask near-useless precision at operational thresholds.

3. **Zero-shot transfer failure across datasets**: Models trained on CERT synthetic data often fail on real LANL authentication logs due to distribution shift — the cert2lanl-zero-shot-transfer repo documents this explicitly.

4. **Tensor sparsity collapse**: The LANL tensors are extremely sparse (0.0001–0.15% nonzero), making standard ALS factorization unstable. Poisson-based methods (CP-APR) handle this better than squared-error methods, but still require careful initialization.

### Regulatory / Compliance Context

- **DOE/NNSA cyber security requirements**: LANL operates under DOE Order 205.1B (Cyber Security Program) — anomaly detection must support continuous monitoring and incident response timelines
- **NIST SP 800-53**: Detection systems must meet AU-6 (Audit Record Review, Analysis, and Reporting) controls — auditability of detection decisions is required
- **No HIPAA/GDPR directly applicable**: This is network authentication data, not PII in the healthcare or EU-citizen sense, but insider threat data is subject to LANL internal privacy policies and DOE privacy program requirements

### Domain Expert Roles for Evaluation

| Role | Responsibility in Eval |
|------|----------------------|
| SOC Analyst / Threat Hunter | Rubric calibration — validate whether flagged anomalies correspond to genuinely suspicious authentication patterns |
| Insider Threat Program Manager | Edge case review — assess whether detection thresholds produce actionable alerts vs. noise flood |
| LANL Cyber Systems Researcher | Reference dataset labeling — verify ground truth labels against red team exercise logs |
| Security Operations Lead | Production sampling — evaluate system behavior on live authentication streams vs. historical test set |

### Key Implementation Resources

| Resource | URL | Status | Notes |
|----------|-----|--------|-------|
| HLSF paper | https://arxiv.org/abs/2607.18479 | Published Jul 2026 | Authors: Perez, Eren, Kaiser (LANL). No public code repo found. |
| pyCP_APR | https://github.com/lanl/pyCP_APR | Active, 20★ | CP-APR tensor decomposition with PyTorch GPU backend. BSD-3. Well-documented. |
| T-ELF | https://github.com/lanl/T-ELF | Active, 26★ | Tensor Extraction of Latent Features. NMFk, RESCALk, auto rank determination. BSD-3. |
| LANL Unified Host & Network Dataset | https://csr.lanl.gov/data/2017/ | Public | The dataset used in HLSF and pyCP_APR papers |
| SmartTensors AI | https://smart-tensors.lanl.gov | LANL project | R&D 100 award-winning project encompassing pyCP_APR and T-ELF |

### HLSF Paper — LANL Results (Reported)

| Tensor Config | CP-APR ROC-AUC | RealNVP ROC-AUC | HLSF ROC-AUC | HLSF PR-AUC |
|---------------|----------------|-----------------|--------------|-------------|
| User×Source (US) | 0.8746 | 0.8111 | **0.8939** | 0.0409 |
| User×Dest (UD) | **0.7727** | 0.6787 | 0.6895 | 0.0030 |
| User×Source×Dest (USD) | 0.9295 | 0.9211 | **0.9709** | **0.0573** |

Key finding: HLSF fusion improves ROC-AUC by 4–5% over individual methods on higher-order tensors. PR-AUC remains low (0.003–0.057) due to extreme class imbalance — this is the operational reality, not a model failure.

### Research Sources

- Perez, Eren, Kaiser. "Hybrid Latent-Structural Fusion (HLSF) for Cyber Anomaly Detection." arXiv:2607.18479, Jul 2026.
- Eren et al. "General-Purpose Unsupervised Cyber Anomaly Detection via Non-Negative Tensor Factorization." Digital Threats, ACM, 2022.
- Eren et al. "Multi-Dimensional Anomalous Entity Detection via Poisson Tensor Factorization." IEEE ISI, 2020.
- LANL SmartTensors project: https://smart-tensors.lanl.gov
- Turcotte, Kent, Hash. "Unified Host and Network Data Set." Data Science for Cyber-Security, 2018.
