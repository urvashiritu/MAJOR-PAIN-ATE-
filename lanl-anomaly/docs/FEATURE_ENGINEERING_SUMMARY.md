# LANL Anomaly Detection - Feature Engineering Research

## Executive Summary

Research on features that catch rule-system bypasses in authentication anomaly detection. The goal is to catch the 34 missed attacks on established pairs where attackers mimic normal behavior.

## Key Findings

### 1. The Problem
- Rule-based system (pair_rank <= 5) catches 95.2% of attacks
- 34 attacks are missed on **established pairs**
- Attacker mimics normal behavior on known user-machine pairs
- **Pair novelty features won't help** - need behavioral deviation features

### 2. Research-Backed Solutions

| Source | Key Insight | Detection Rate |
|--------|-------------|----------------|
| **Hopper** (USENIX 2021) | Path-based detection with credential change | 94.5% TPR, <9 FP/day |
| **LMDetect** (arXiv 2024) | Time-aware subgraph classification | State-of-the-art |
| **RAD** (CIKM 2026) | Rule injection into graph neural networks | Best on LANL |
| **Exabeam UEBA** | Production-tested behavioral features | Enterprise-grade |
| **Microsoft Sentinel** | Impossible travel, peer comparison | Industry standard |

### 3. Recommended Features (Priority Order)

#### P0 - Highest Impact (Implement First)
1. **`iat_zscore`** - Inter-arrival time z-score
   - How: Time since last auth / user's historical baseline
   - Why: Attackers authenticate at different rates
   - Expected AUC: 0.85-0.95

2. **`velocity_ratio`** - Authentication velocity
   - How: Auth count in 1H / Auth count in 24H
   - Why: Attackers scan machines in bursts
   - Expected AUC: 0.80-0.90

3. **`path_length`** - Lateral movement path length
   - How: Consecutive auths without session break
   - Why: Lateral movement paths are longer
   - Expected AUC: 0.75-0.85

#### P1 - Medium Impact
4. **`credential_change`** - Hopper's key feature
   - How: User changes credentials mid-path
   - Why: Attackers switch credentials
   - Expected AUC: 0.70-0.80

5. **`unique_dst_1H`** - Unique destinations in 1 hour
   - How: Count of unique destination computers in 1-hour window
   - Why: Attackers access many machines quickly
   - Expected AUC: 0.70-0.80

6. **`is_work_hours`** - After-hours detection
   - How: Binary flag for 8AM-6PM
   - Why: Attackers often work after hours
   - Expected AUC: 0.65-0.75

#### P2 - Lower Impact
7. **`machine_popularity`** - Shared resource access
   - How: Number of users accessing this machine
   - Why: Attackers target shared resources
   - Expected AUC: 0.60-0.70

8. **`peer_deviation`** - Behavioral deviation from peers
   - How: Compare to users with similar access patterns
   - Why: Attackers behave differently from peers
   - Expected AUC: 0.60-0.70

## Implementation Plan

### Phase 1: Add P0 Features to DuckDB
```sql
-- Add to FEATURE_SQL in 01_build_features.py

-- Inter-arrival time
EXTRACT(EPOCH FROM (
    b.time - LAG(b.time) OVER (PARTITION BY b.src_user ORDER BY b.time)
)) AS time_since_last,

-- Rolling mean for z-score
AVG(EXTRACT(EPOCH FROM (
    b.time - LAG(b.time) OVER (PARTITION BY b.src_user ORDER BY b.time)
))) OVER (PARTITION BY b.src_user ORDER BY b.time 
    ROWS BETWEEN 100 PRECEDING AND 1 PRECEDING) AS iat_mean,

-- Rolling std for z-score
STDDEV(EXTRACT(EPOCH FROM (
    b.time - LAG(b.time) OVER (PARTITION BY b.src_user ORDER BY b.time)
))) OVER (PARTITION BY b.src_user ORDER BY b.time 
    ROWS BETWEEN 100 PRECEDING AND 1 PRECEDING) AS iat_std,

-- Velocity features
count(*) OVER (PARTITION BY b.src_user ORDER BY b.time 
    RANGE BETWEEN 3600 PRECEDING AND CURRENT ROW) AS auth_count_1H,
count(*) OVER (PARTITION BY b.src_user ORDER BY b.time 
    RANGE BETWEEN 86400 PRECEDING AND CURRENT ROW) AS auth_count_24H,

-- Path features
SUM(CASE WHEN EXTRACT(EPOCH FROM (
    b.time - LAG(b.time) OVER (PARTITION BY b.src_user ORDER BY b.time)
)) > 3600 THEN 1 ELSE 0 END) OVER (PARTITION BY b.src_user 
    ORDER BY b.time) AS path_id,
```

### Phase 2: Validate with Feature Probe
1. Update `02_feature_probe.py` to include new features
2. Run on the 34 missed attacks
3. Check if new features separate them from normal behavior

### Phase 3: Retrain Models
1. Add new features to `03_retrain_both.py`
2. Compare performance with and without new features
3. Focus on the 34 missed attacks

## Expected Outcomes

- **Catch more of the 34 missed attacks** - behavioral features should separate them
- **Maintain 95.2% detection rate** - don't break what's working
- **Reduce false positives** - focus on behavioral deviation, not just pair novelty

## Files Created

1. `docs/FEATURE_ENGINEERING_RESEARCH.md` - Comprehensive research document
2. `docs/RESEARCH_SUMMARY.md` - Executive summary
3. `docs/FEATURE_ENGINEERING_SUMMARY.md` - This file

## Next Steps

1. **Immediate**: Add P0 features to `01_build_features.py`
2. **Short-term**: Validate with `02_feature_probe.py`
3. **Medium-term**: Retrain models and compare performance
4. **Long-term**: Add P1 and P2 features as needed

## References

- Hopper: https://www.usenix.org/conference/usenixsecurity21/presentation/ho
- LMDetect: https://arxiv.org/abs/2411.10279
- RAD: https://arxiv.org/abs/2608.23468
- Exabeam: https://www.exabeam.com/capabilities/ueba
- Microsoft Sentinel: https://learn.microsoft.com/en-us/azure/sentinel/ueba-reference
- LANL Dataset: https://csr.lanl.gov/data/cyber1
