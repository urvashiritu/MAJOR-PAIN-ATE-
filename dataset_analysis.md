# Dataset Analysis Report — AI-Based Identity Anomaly Detection

**Team:** Hemanth, Urvashi, Veenashree, Vishwanath
**Guide:** Dr. Anitha A C
**Date:** July 2026

---

## 1. Objective

Select a dataset for training and evaluating our ensemble ML models (Isolation Forest, One-Class SVM, LOF, Elliptic Envelope) to detect anomalous login behavior.

**Requirements:**
- Must have user login data with timestamps
- Must have features to compute 8 behavioral features (hour, is_weekend, is_night, device_change, country_change, failed_before_success, rapid_login_rate, login_frequency_today)
- Must have ground truth labels (which events are attacks)
- Must be manageable size for a student team (under 20 GB)

---

## 2. Dataset 1: RBA (Risk-Based Authentication) — Zenodo

**Source:** Telenor Norway SSO (synthesized from real login patterns)
**Paper:** Wiefling et al., ACM TOPS 2022
**Download:** https://zenodo.org/records/6782156

### File Structure

| File | Size | Format |
|------|------|--------|
| rba-dataset.zip | 1.1 GB | ZIP (contains single CSV) |
| rba-dataset.csv | 8.5 GB | CSV, 31.3 million rows (31,269,264), 16 columns |

### Columns

| Column | Type | Example |
|--------|------|---------|
| index | int | 0 |
| Login Timestamp | datetime | 2020-02-03 12:43:30.772 |
| User ID | string | -4324475583306591935 |
| Round-Trip Time [ms] | int | (empty for many rows) |
| IP Address | string | 10.0.65.171 |
| Country | string | NO, US, AU, etc. |
| Region | string | Vestland (often empty) |
| City | string | Urangsvag (often empty) |
| ASN | int | 29695 |
| User Agent String | string | Mozilla/5.0 ... |
| Browser Name and Version | string | Firefox 20.0.0.1618 |
| OS Name and Version | string | iOS 13.4 |
| Device Type | string | mobile, desktop, tablet |
| Login Successful | bool | True / False |
| Is Attack IP | bool | True / False |
| Is Account Takeover | bool | True / False |

### Sample Row (Normal)

```
Login Timestamp: 2020-02-03 12:43:30.772
User ID: -4324475583306591935
Country: NO
Device Type: mobile
Browser: Firefox 20.0.0.1618
OS: iOS 13.4
Login Successful: False
Is Attack IP: False
Is Account Takeover: False
```

### Sample Row (Attack)

```
Login Timestamp: 2020-02-03 12:43:59.396
User ID: -4618854071942621186
Country: US
Device Type: mobile
Login Successful: False
Is Attack IP: True
Is Account Takeover: False
```

### Verdict

| Factor | Status |
|--------|--------|
| Has user_id | Yes |
| Has timestamp | Yes |
| Has country | Yes |
| Has device type | Yes (from User Agent) |
| Has browser | Yes |
| Has OS | Yes |
| Has success/failure | Yes |
| Has attack labels | Yes (Is Attack IP, Is Account Takeover) |
| All 8 features computable | Yes |
| Ground truth available | Yes (141 confirmed account takeovers) |
| Size manageable | Yes 8.5 GB |
| Already downloaded | Yes |
| Academic citations | ACM TOPS paper + follow-ups |

---

## 3. Dataset 2: LANL CMSCSE — Los Alamos National Lab

**Source:** Real enterprise network at LANL
**Paper:** Kent, 2015, "Cybersecurity Data Sources for Dynamic Network Research"
**Download:** https://csr.lanl.gov/data/cyber1/

### File Structure

| File | Size (compressed) | Rows | Columns |
|------|-------------------|------|---------|
| auth.txt.gz | 7.2 GB | 1.05 billion | 9 |
| proc.txt.gz | 2.2 GB | 426 million | 4 |
| flows.txt.gz | 1.1 GB | 130 million | 9 |
| dns.txt.gz | 177 MB | 41 million | 3 |
| redteam.txt.gz | 4.8 KB | 749 | 4 |

### auth.txt.gz Columns

| Column | Type | Example |
|--------|------|---------|
| time | int (epoch) | 1 |
| source_user@domain | string | ANONYMOUS LOGON@C586 |
| destination_user@domain | string | ANONYMOUS LOGON@C586 |
| source_computer | string | C1250 |
| destination_computer | string | C586 |
| authentication_type | string | NTLM, Negotiate, Kerberos, ? |
| logon_type | string | Network, Service, Batch, Interactive |
| authentication_orientation | string | LogOn, LogOff |
| success/failure | string | Success, Fail |

### Sample Row

```
time: 1
source_user: ANONYMOUS LOGON@C586
dest_user: ANONYMOUS LOGON@C586
source_computer: C1250
dest_computer: C586
auth_type: NTLM
logon_type: Network
orientation: LogOn
success: Success
```

### Verdict

| Factor | Status |
|--------|--------|
| Has user_id | Yes |
| Has timestamp | Yes (epoch format) |
| Has country | No (all internal LANL) |
| Has device type | No (computer name only like C1250) |
| Has browser/OS | No |
| Has success/failure | Yes |
| Has attack labels | Yes (redteam.txt.gz) |
| All 8 features computable | No (missing country, device, browser, OS) |
| Size manageable | No (89 GB uncompressed) |
| Already downloaded | Only 2.6 MB sampled subset |
| Academic citations | Real enterprise data |

**Cannot compute: country_change, device_change, browser, OS features.**

---

## 4. Dataset 3: CERT Insider Threat r4.2 — Carnegie Mellon University

**Source:** CMU CERT Division (DARPA funded), synthetic
**Paper:** Glasser & Lindauer, IEEE SPW 2013
**Download:** https://kilthub.cmu.edu/articles/dataset/Insider_Threat_Test_Dataset/12841247

### File Structure (Full Download ~16 GB)

| File | Size | Columns | Content |
|------|------|---------|---------|
| logon.csv | ~500 MB | id, date, user, pc, activity | LogOn/LogOff events |
| device.csv | ~28 MB | id, date, user, pc, activity | USB Connect/Disconnect |
| file.csv | ~184 MB | id, date, user, pc, filename, activity | File operations |
| email.csv | 1.3 GB | id, date, user, pc, to, cc, bcc, from, size, attachments, content | Email records |
| http.csv | 13.5 GB | id, date, user, pc, url, content_type | Web browsing |
| psychometric.csv | 44 KB | user, O, C, E, A, N | Personality scores |
| LDAP | ~10 MB | user, role, department, team, manager | Employee info |
| answers/ | ~5 MB | — | Ground truth keys |

### logon.csv Columns (our primary file)

| Column | Type | Example |
|--------|------|---------|
| id | string | {R3I7-S4TX96FG-8219JWFF} |
| date | datetime | 01/02/2010 07:11:45 |
| user | string | LAP0338 |
| pc | string | PC-5758 |
| activity | string | LogOn, LogOff |

### Sample logon.csv Row

```
id: {R3I7-S4TX96FG-8219JWFF}
date: 01/02/2010 07:11:45
user: LAP0338
pc: PC-5758
activity: LogOn
```

### Verdict

| Factor | Status |
|--------|--------|
| Has user_id | Yes |
| Has timestamp | Yes |
| Has country | No |
| Has device type | No (pc name only) |
| Has browser/OS | No |
| Has success/failure | No (only LogOn/LogOff) |
| Has attack labels | Yes (answer key files) |
| All 8 features computable | No (missing country, device, browser, OS, success/failure) |
| Size manageable | Yes 16 GB |
| Already downloaded | No (only email.csv, 1.3 GB) |
| Academic citations | 275+ papers |

**Cannot compute: country_change, device_change, browser, OS, failed_before_success.**

---

## 5. Comparison Summary Table

| Requirement | RBA | LANL | CERT logon.csv |
|-------------|-----|------|----------------|
| user_id | Yes | Yes | Yes |
| timestamp | Yes | Yes (epoch) | Yes |
| country | **Yes** | No | No |
| device type | **Yes** | No (computer name) | No (pc name) |
| browser | **Yes** | No | No |
| OS | **Yes** | No | No |
| success/failure | **Yes** | Yes | No (LogOn/LogOff) |
| attack labels | Yes (141 ATOs) | Yes (749 redteam) | Yes (70 malicious users) |
| All 8 features | Yes | No (missing 3+) | No (missing 4+) |
| Download size | 8.5 GB | 89 GB (full) | 16 GB (full) |
| Already downloaded | Yes | Partial sample | Wrong file |
| Ready to use now | Yes | No | No |

---

## 6. Selection: RBA Dataset

### Why RBA

1. **All 8 features computable** — Has country, device type, browser, OS, timestamp, success/failure. The other two datasets are missing 3-4 columns we need.

2. **Already downloaded and cached** — 1.2 GB zip extracted to 8.5 GB CSV. DuckDB cache (533 MB) already built. Zero setup time.

3. **31.3 million events** — More than enough data for training our 4 ML models.

4. **Ground truth labels** — Is Attack IP and Is Account Takeover columns let us evaluate precision, recall, F1.

5. **Right fit for our project** — The project is "Identity Anomaly Detection." RBA is an authentication dataset with login-level anomalies. CERT is for insider threat (file exfiltration, email leaks). LANL lacks geo/device features entirely.

### What RBA Lacks vs CERT

- Only 141 confirmed account takeovers (vs 70 malicious users with multi-day scenarios in CERT)
- Synthesized data (statistically reconstructed from real patterns), not real logs
- Fewer academic citations (ACM TOPS 2022 vs 275+ papers for CERT)

### Mitigation

- The synthetic persona generator (built in Week 1) creates additional attack scenarios
- For the report, we cite the RBA paper and acknowledge the limitation of synthetic data
- The ensemble model evaluates on both RBA ground truth and synthetic attack events

---

## 7. Fields Used in Our Pipeline

From the 16 RBA columns, we use these for our 8 features:

| RBA Column | Maps To | Feature(s) |
|-----------|---------|------------|
| Login Timestamp | timestamp | hour, is_weekend, is_night, rapid_login_rate, login_frequency_today |
| User ID | user_id | User identity |
| Country | country | country_change |
| Device Type | device | device_change |
| OS Name and Version | os | Supplementary |
| Browser Name and Version | browser | Supplementary |
| Login Successful | is_success | failed_before_success |
| Is Attack IP | ground truth | Evaluation |
| Is Account Takeover | ground truth | Evaluation |

---

## 8. Conclusion

We selected the RBA dataset for the following reasons:

- It is the only dataset among the three that contains all columns needed for our 8 behavioral features
- It is already downloaded and ready for use (8.5 GB extracted CSV + 533 MB DuckDB cache)
- It has 31.3 million login events with ground truth labels for evaluation
- It is specifically designed for login-level anomaly detection, matching our project objective
- CERT r4.2 (more academic prestige) lacks country, device, browser, OS, and success/failure columns in its auth logs
- LANL (real enterprise data) is 89 GB and lacks country and device information entirely

---

## 9. Update (Aug 1, 2026)

**Decision stands: RBA is the only training dataset.**

A multi-source extension was prototyped afterwards — 7 AI-generated synthetic log formats (SSH, VPN, Windows AD, M365, AWS, database audit, web login) normalized by a `parser.py` into a common schema — then **removed**. The synthetic data was internally inconsistent (impossible device/browser/OS combos), only 1 of 7 sources had ground-truth labels, and models scored AUC ≈ 0.45 (worse than random) on those labels. It could not serve as training or evaluation data.

The parser concept (normalizing heterogeneous auth logs into one schema) remains a candidate **future demo enhancement**, matching how SIEM products consume logs — but the ML trains on the real RBA dataset only.
