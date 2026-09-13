# Feature Engineering Research Summary

## Date: 2026-09-11

## Problem Statement

The rule-based system (pair_rank <= 5) catches 95.2% of attacks on the LANL dataset. However, 34 attacks are missed because they occur on **established pairs** where the attacker mimics normal behavior.

## Key Finding

**Pair novelty features won't catch the remaining 34 attacks.** We need features that capture **behavioral deviation**, not just pair novelty.

## Research Sources

1. **Hopper** (USENIX Security 2021) - 94.5% detection rate with <9 FP/day
   - Uses path-based detection with credential change and new machine access
   - **Directly relevant** to the 34 missed attacks

2. **LMDetect** (arXiv 2024) - Time-aware subgraph classification
   - Uses temporal patterns in authentication sequences

3. **RAD** (CIKM 2026) - Rule-augmented relational anomaly detection
   - Uses the same LANL dataset
   - Achieves state-of-the-art results

4. **Exabeam UEBA** - Production-tested features
   - Volume, velocity, timing, diversity, novelty

5. **Microsoft Sentinel UEBA** - Behavioral analytics
   - Impossible travel, after-hours detection, peer group comparison

## Recommended Features

### P0 (Highest Impact)

| Feature | Category | Why It Works |
|---------|----------|--------------|
| `iat_zscore` | Temporal | Attackers authenticate at different rates than legitimate users |
| `velocity_ratio` | Temporal | Attackers scan machines in bursts |
| `path_length` | Path | Lateral movement paths are longer |

### P1 (Medium Impact)

| Feature | Category | Why It Works |
|---------|----------|--------------|
| `credential_change` | Path | Attackers switch credentials mid-path |
| `unique_dst_1H` | Velocity | Attackers access many machines quickly |
| `is_work_hours` | Temporal | Attackers often work after hours |

### P2 (Lower Impact)

| Feature | Category | Why It Works |
|---------|----------|--------------|
| `machine_popularity` | Cross-user | Attackers target shared resources |
| `peer_deviation` | Cross-user | Attackers behave differently from peers |

## Implementation Plan

1. Add P0 features to `01_build_features.py`
2. Run `02_feature_probe.py` to validate
3. Focus on the 34 missed attacks - do new features separate them?
4. If P0 helps, add P1 features

## Expected Outcome

Adding these features should:
- Catch more of the 34 missed attacks
- Maintain or improve the current 95.2% detection rate
- Reduce false positives by focusing on behavioral deviation

## References

- Hopper: https://www.usenix.org/conference/usenixsecurity21/presentation/ho
- LMDetect: https://arxiv.org/abs/2411.10279
- RAD: https://arxiv.org/abs/2608.23468
- Exabeam: https://www.exabeam.com/capabilities/ueba
- Microsoft Sentinel: https://learn.microsoft.com/en-us/azure/sentinel/ueba-reference
