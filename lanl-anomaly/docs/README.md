# LANL Anomaly Detection - Feature Engineering Research

## Date: 2026-09-11

## Executive Summary

Comprehensive research on features that catch rule-system bypasses in authentication anomaly detection. The goal is to catch the 34 missed attacks on established pairs where attackers mimic normal behavior.

## The Problem

- **Current system**: Rule-based system (pair_rank <= 5) catches 95.2% of attacks
- **Missed attacks**: 34 attacks on established pairs where attacker mimics normal behavior
- **Root cause**: Pair novelty features won't catch these - need behavioral deviation features

## Research Sources

| Source | Key Insight | Detection Rate | Relevance |
|--------|-------------|----------------|-----------|
| **Hopper** (USENIX 2021) | Path-based detection with credential change | 94.5% TPR, <9 FP/day | **Directly relevant** to 34 missed attacks |
| **LMDetect** (arXiv 2024) | Time-aware subgraph classification | State-of-the-art | Temporal patterns in sequences |
| **RAD** (CIKM 2026) | Rule injection into graph neural networks | Best on LANL | Same dataset, state-of-the-art |
| **Exabeam UEBA** | Production-tested behavioral features | Enterprise-grade | Volume, velocity, timing, diversity |
| **Microsoft Sentinel** | Impossible travel, peer comparison | Industry standard | Behavioral analytics |

## Recommended Features

### P0 - Highest Impact (Implement First)

| Feature | Category | How It Works | Expected AUC |
|---------|----------|--------------|--------------|
| `iat_zscore` | Temporal | Time since last auth / user's historical baseline | 0.85-0.95 |
| `velocity_ratio` | Temporal | Auth count in 1H / Auth count in 24H | 0.80-0.90 |
| `path_length` | Path | Consecutive auths without session break | 0.75-0.85 |

**Why these work:**
- Attackers authenticate at different rates than legitimate users
- Attackers scan machines in bursts
- Lateral movement paths are longer than normal authentication sequences

### P1 - Medium Impact

| Feature | Category | How It Works | Expected AUC |
|---------|----------|--------------|--------------|
| `credential_change` | Path | User changes credentials mid-path | 0.70-0.80 |
| `unique_dst_1H` | Velocity | Unique destinations in 1 hour | 0.70-0.80 |
| `is_work_hours` | Temporal | Binary flag for 8AM-6PM | 0.65-0.75 |

**Why these work:**
- Attackers switch credentials (Hopper's key insight)
- Attackers access many machines quickly
- Attackers often work after hours

### P2 - Lower Impact

| Feature | Category | How It Works | Expected AUC |
|---------|----------|--------------|--------------|
| `machine_popularity` | Cross-user | Number of users accessing this machine | 0.60-0.70 |
| `peer_deviation` | Cross-user | Compare to users with similar access patterns | 0.60-0.70 |

**Why these work:**
- Attackers target shared resources
- Attackers behave differently from peers

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

| File | Description |
|------|-------------|
| `docs/FEATURE_ENGINEERING_RESEARCH.md` | Comprehensive research document (500+ lines) |
| `docs/RESEARCH_SUMMARY.md` | Executive summary |
| `docs/FEATURE_ENGINEERING_SUMMARY.md` | Implementation guide |
| `reports/experiment_log.md` | Updated with research findings |

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
