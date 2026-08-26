# Detailed Project Documentation

Everything you need to know. No fluff. Skip around.

---

## The Problem

Organizations have authentication logs scattered across 10+ systems. Attackers blend in. Security analysts drown in alerts.

**We built a system that:**
- Ingests auth logs from 6 different sources
- Extracts behavioral features per event
- Classifies each event in real time
- Shows everything on a live dashboard

---

## The Dataset

### Sources

| # | Source | Format | Events | Key Fields |
|---|---|---|---|---|
| 1 | SSH | Syslog text | 100,569 | timestamp, user, IP, success/fail |
| 2 | AWS CloudTrail | JSON | 100,944 | eventTime, userIdentity, sourceIPAddress |
| 3 | Windows Security | XML (→JSON) | 100,260 | TimeCreated, TargetUserName, IpAddress |
| 4 | MySQL Audit | JSON | 100,262 | timestamp, user, connection_data.status |
| 5 | Web Auth | JSONL | 100,188 | timestamp, username, ip, success |
| 6 | Entra ID | JSON | 100,916 | createdDateTime, userPrincipalName, ipAddress |

**Total: 603,291 events**

### Attack IPs

**5 original (obvious brute-force):**

| IP | Failures/Day | Sources Used | Behavior |
|---|---|---|---|
| `185.220.101.17` | 400+ | SSH, WEB, AWS | Aggressive password spray |
| `45.155.205.233` | 400+ | SSH, MYSQL | Targeted DB brute force |
| `91.240.118.172` | 400+ | SSH, ENTRA, WINDOWS | Multi-source credential stuffing |
| `103.75.201.44` | 400+ | WEB, ENTRA | Web app brute force |
| `194.26.135.119` | 400+ | SSH, AWS | Cloud credential theft |

**5 stealthy (harder to detect):**

| IP | Strategy | Why It's Hard |
|---|---|---|
| `10.20.99.101` | Slow brute (2-3 attempts/hour) | Stays under hourly thresholds |
| `10.20.99.102` | Credential stuffing (valid usernames) | High success rate masks failures |
| `10.20.99.103` | Lateral movement (1-2 new users/hour) | Low volume, legitimate-looking |
| `10.20.99.104` | Low-and-slow (1 attempt/day/user) | Basically invisible |
| `10.20.99.105` | Distributed spray (many IPs, few attempts each) | No single IP has high count |

---

## The Pipeline

### Step 1: Parse Raw Logs → `data/auth.duckdb`

**Script:** `src/01_parse_all.py`

Each source has its own parser. All normalize to one schema:

```
auth_events (
    ts          TIMESTAMP,
    src_user    VARCHAR,
    src_ip      VARCHAR,
    success     BOOLEAN,
    source      VARCHAR,    -- 'SSH', 'AWS', etc.
    auth_type   VARCHAR     -- 'password', 'Kerberos', etc.
)
```

**Key fixes applied during parsing:**
- MySQL: `connection_data.status` field (not `success`) determines login result
- Windows: XML namespace stripping + `cast(timestamp AS TIMESTAMP)`
- AWS: Python-based JSON parsing (giant objects exceeded DuckDB limits)
- Column name bug: `CAST(success AS BOOLEAN)` → just `success` (column was already boolean)

### Step 2: Build Features → `outputs/features_lanl.parquet`

**Script:** `src/02_build_features.py`

All features are **per-event** and **windowed** (no future leakage):

```sql
-- fail_1h: count of failures from this IP in the last hour
SELECT count(*) FROM auth_norm f
WHERE f.src_ip = a.src_ip AND NOT f.success
  AND f.ts > a.ts - INTERVAL '1 hour' AND f.ts <= a.ts

-- user_fail_rate: historical failure rate for this user BEFORE this event
SELECT CASE WHEN count(*) > 0
  THEN count(*) FILTER (WHERE NOT success)::FLOAT / count(*)
  ELSE 0.5 END
FROM auth_norm WHERE src_user = a.src_user AND ts < a.ts
```

**Why windowed?** If you compute features over the entire dataset, you leak future information. The model must only see the past when scoring.

### Step 3: Train Models → `models/multi_*.joblib`

**Script:** `src/03_train_models.py`

**Evaluation methodology (honest):**

| Strategy | Purpose |
|---|---|
| Holdout IP (`10.20.99.103`) | Tests generalization to unseen attacker |
| Time-based split | Train Jul 1-20, Test Jul 21-31 (no temporal leakage) |
| PR-AUC as primary metric | More meaningful than ROC-AUC at 8% attack rate |
| Baseline comparison | fail_1h > 8 threshold vs full model |

**Isolation Forest:**
- 200 estimators, 8% contamination
- Detects anomalies without needing labeled data
- Normalizes raw anomaly scores to [0, 1]

**LightGBM:**
- Binary classification (attack vs normal)
- `scale_pos_weight` handles class imbalance (8.2% attacks)
- 500 boosting rounds, early stopping on validation

**Ensemble:**
```python
combined = 0.5 * if_score + 0.5 * lgb_score
```
Threshold selected to maximize F1 on validation set.

### Step 4: Score Events → Risk Level

```
combined_score >= 0.75  →  CRITICAL
combined_score >= 0.50  →  HIGH
combined_score >= thresh → MEDIUM
combined_score <  thresh → LOW
```

---

## The Live System

### Architecture

```
Laptop B (attacker)
    │
    │ SSH attempts → rsyslog forwards to UDP 1514
    ▼
Laptop A (server)
    │
    ├─ Flask app.py (port 5001)
    │   ├─ SSH syslog listener (UDP 1514)
    │   │   └─ parse_ssh_line() → event dict
    │   │   └─ compute_live_features() → 9 features
    │   │   └─ score_event() → risk level
    │   │   └─ append to _live_events buffer
    │   │
    │   ├─ REST API
    │   │   ├─ GET /api/stats → KPIs + distributions
    │   │   ├─ GET /api/score-batch → training sample
    │   │   ├─ POST /api/score → score single event
    │   │   └─ POST /api/ssh-listener → start/stop
    │   │
    │   └─ Dashboard (templates/dashboard.html)
    │       ├─ Auto-refresh every 10s
    │       ├─ KPI cards (total, attacks, ROC-AUC, F1)
    │       ├─ Doughnut charts (source distribution, success/failure)
    │       └─ Live events table with risk badges
    │
    └─ data/auth.duckdb (read-only)
```

### SSH Syslog Listener

Listens on UDP port 1514. Parses syslog-formatted SSH lines:

```
Aug 26 22:00:01 laptop sshd[1234]: Failed password for root from 185.220.101.17 port 22
```

Regex:
```python
r"^(\w+ \d+ \d+:\d+:\d+) \S+ sshd\[\d+\]: "
r"(Accepted|Failed) \S+ (?:for )?(?:invalid user )?(\S+)? "
r"from (\S+) port \d+"
```

### Cold-Start Behavior

When a new IP appears for the first time:

| Feature | Value | Why |
|---|---|---|
| `fail_1h` | 0 | No failures yet |
| `vel_1h` | 1 | First event |
| `fail_24h` | 0 | No 24h history |
| `vel_24h` | 1 | First event |
| `user_fail_rate` | 0.5 | Default (50/50 guess) |
| `src_ip_fail_rate` | 0.0 | No failures observed |

The model needs ~10-15 failed attempts before escalating risk. This is realistic — real systems need behavioral context too.

---

## Honest Limitations

### What Works Great
- Detecting aggressive brute-force (original 5 IPs): ROC-AUC 0.9999
- Multi-source correlation (same attacker across SSH + AWS + Windows)
- Real-time scoring with sub-second latency
- Dashboard auto-refreshes every 10 seconds

### What Doesn't
- **Cold-start:** New IPs need ~10-15 events before classification kicks in
- **Stealthy attacks:** Low-volume attackers (1-3 attempts/hour) evade the model
- **Feature leakage risk:** `src_ip_fail_rate` uses historical aggregates that are IP-specific — the model partially memorizes IP identity
- **Holdout evaluation:** Held-out IP `10.20.99.103` had only attack events (no normals), making holdout metrics trivially perfect

### Known Technical Debt
- `compute_live_features()` in `app.py` re-computes features from a 200-event buffer (not from DuckDB) — less accurate than training features
- `api/score-batch` uses dummy features for training sample display (doesn't actually score)
- Temporal features (`hour_ratio`, `hour_sin`, `hour_cos`) have ~0.50 AUC — essentially random

---

## How to Reproduce Everything

### From Scratch

```bash
# 1. Parse raw logs into DuckDB
python3 src/01_parse_all.py

# 2. Build features
python3 src/02_build_features.py

# 3. Train models
python3 src/03_train_models.py

# 4. Run dashboard
python3 app.py
```

### Simulate Attacks via Syslog

```bash
# Send 10 rapid failures from known attacker
for i in $(seq 1 10); do
  echo "Aug 26 22:00:$i laptop sshd[$RANDOM]: Failed password for root from 185.220.101.17 port $((RANDOM%60000+1024))" | nc -u localhost 1514
  sleep 0.5
done
```

### Multi-Laptop Demo

```bash
# On Laptop B, configure rsyslog forwarding:
sudo bash -c 'echo "*.* @@<LAPTOP_A_IP>:1514" >> /etc/rsyslog.conf'
sudo systemctl restart rsyslog

# Then SSH to Laptop A:
ssh fakeuser@<LAPTOP_A_IP>
```
