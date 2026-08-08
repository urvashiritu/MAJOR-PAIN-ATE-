# Dataset Scan Report — RBA Dataset

**File:** `data/raw/rba-dataset.csv` (8.5 GB, Zenodo 6782156)
**Scan date:** Aug 2, 2026
**Method:** DuckDB 1.5.5, in-memory, read-only. Every query scanned **all 31,269,264 rows** (full-file reads, ~5 s per pass). No files were modified during the scan.

---

## 1. Column validation — what is correct

| Column | Check | Result |
|---|---|---|
| index | numeric, sequential, unique | ✓ perfect sequence 0 → 31,269,263, no gaps, no reuse |
| Login Timestamp | parseable, valid range | ✓ 100% parse (`%Y-%m-%d %H:%M:%S[.%f]`), 2020-02-03 12:43:30 → 2021-02-28 23:59:58 |
| User ID | numeric | ✓ all int64 (−9.22e18 … +9.22e18); 2,151,939 negative users + 2,152,918 positive users (both signs are legitimate) |
| Round-Trip Time [ms] | numeric where present | ✓ 8 … 223,457 ms — but see §3.4 (95.9% empty) |
| IP Address | IPv4 format, octet range | ✓ all match `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}`, no octet > 255 |
| Country | ISO-3166 alpha-2 | ✓ 229 codes, all valid except `XK` (Kosovo, de-facto standard, 53 rows) |
| Region / City | — | ⚠️ two missing-value conventions, see §3.5 |
| ASN | 32-bit range | ✓ 12 … 507,727, no overflow |
| User Agent String | present | ✓ all rows non-empty (9,715 suspiciously short, <15 chars) |
| Browser / OS / Device | present | ✓ no NULLs, no `-` placeholders — but cross-field contradictions, see §3.1–3.3 |
| Login Successful / Is Attack IP / Is Account Takeover | boolean | ✓ only `True`/`False`, no NULLs |
| Whole rows | exact duplicates | ✓ none (0 duplicate groups on key fields) |

**The 16 columns and their header names are correct.** No missing columns, no type garbage, no malformed rows were dropped by the parser.

---

## 2. Verified facts (full-scan, reproducible)

| Fact | Value |
|---|---|
| Total events | 31,269,264 |
| Unique users | 4,304,857 |
| Date range | 2020-02-03 → 2021-02-28 (~13 months) |
| Successful logins | 12,541,442 (40.1%) |
| Failed logins | 18,727,822 (59.9%) |
| Is Attack IP = True | 3,096,977 (~9.9%) |
| — of which successful | 804,491 |
| Account takeovers (ATO) | 141 rows, 138 users |
| — ATO also attack-flagged | 77 of 141 (54.6%) |
| Unique IPs | 3,512,330 |
| Unique countries | 229 |
| Device types | mobile, desktop, tablet, bot, unknown |
| Unique browsers (raw strings) | 4,549 |
| Generator-bot rows (UA carries `github.com/das-group/rba-dataset`) | 3,704,894 (11.8%) |
| Impossible browser/OS versions vs login date | 1,651,546 (5.3%) |
| ASNs spanning 2+ countries | 680 (15,497,255 rows, 49.6%) |

---

## 3. Inconsistencies found (full-scan counts)

### 3.1 Browser ↔ OS contradictions — 1,223,315 rows (3.9%) — HIGH

| Pattern | Rows |
|---|---|
| browser says Android, OS says iOS | 1,207,424 |
| browser says mobile platform (Android/iPhone/iPad), OS says Windows | 15,644 |
| browser says Windows, OS says mobile (Android/iOS/Mac) | 247 |

Example (`data/raw/rba-dataset.csv:3`): browser `Android 2.3.3.2672` + OS `iOS 7.1`.

**Impact:** `device_change` / `os_change` features will invent fake device switches and confuse the models. The User Agent string is the source of truth for fixing these.

### 3.2 device=mobile but browser string has no mobile marker — 3,162,207 rows (10.1%) — MEDIUM

Device Type says `mobile`, but the Browser column has no `Mobile`/`Android`/`iPhone`/`iPad` token (e.g. browser `Firefox 20.0.0.1618`, OS `iOS 13.4`, device `mobile`). This is the dataset's own UA-parser losing the mobile marker, not a user-level error.

### 3.3 Private (RFC1918) IPs geolocated to other countries — 5,266,810 rows — HIGH

- `10.x` private IPs: **7,291,335 rows (23.3%)** — internal IPs from Telenor's SSO vantage point; plausible only for NO
- of those, **5,266,810 are tagged with countries other than NO** (US, RU, …) — impossible geolocation
- **506,460 private-IP rows are flagged `Is Attack IP = True`** — label noise (a private/internal address can't be an external attack IP)
- 1,920,195 successful logins from private IPs
- 39 of the 141 ATO rows come from private IPs
- **IP reuse across users:** 49,009 IPs serve 10–99 users, 9,221 serve 100–999, 1,071 serve 1,000+ (top: `10.0.77.226` with 12,235 users) — private NAT pools, so IP-derived identity signals for these rows are weak

### 3.4 Round-Trip Time missing / extreme — 29,993,329 rows — MEDIUM

- **95.9% of rows have empty RTT** (only 1,275,935 rows have a value: 875,234 success / 400,701 failed). Not a parse error — the column is mostly empty by design.
- 79 rows have RTT > 60,000 ms (max 223,457 ms ≈ 3.7 min) — implausible outliers.

**Impact:** RTT cannot be a primary feature; keep it as an auxiliary signal with an explicit "missing" flag.

### 3.5 Two missing-value conventions — 14,063,591 rows — LOW

Region/City use `-` as a placeholder **and** NULL in the same columns:

| Pattern | Rows |
|---|---|
| region `-` AND city `-` | 13,895,698 |
| region `-` but city set | 117,683 |
| region NULL | 47,409 |
| city NULL | 8,590 |

### 3.6 Device type `unknown` / `bot` — 2,895,205 rows (9.3%) — LOW

- `unknown`: 867,371 rows (11,230 successful — silent gap in device coverage)
- `bot`: 2,027,834 rows (only 64 successful; 4,959 of them have non-bot User Agent strings)

### 3.7 ATO label quirks — 65 rows — LOW

- 1 of 141 ATO rows is a **failed** login (takeover on a failed attempt)
- 64 of 141 ATO rows are NOT flagged `Is Attack IP` — the attack-IP label alone misses 45% of confirmed takeovers (already documented; re-verified)

### 3.8 Impossible browser/OS versions vs login date — 1,651,546 rows (5.3%) — MEDIUM-HIGH

Versions appear **before their real-world release date** (or after the dataset ends) — a synthesis artifact, not user error:

| Impossible pattern | Rows |
|---|---|
| Chrome 85 before 2020-08-25 (release) | 7,337 |
| Chrome 89 (released Mar 2021, after dataset end) | 159 |
| Chrome 90+ (released Apr 2021+, after dataset end) | 239,712 |
| Android 11 before 2020-09-08 (release) | 38 |
| Android 12+ (released Oct 2021, after dataset end) | 885,290 |
| iOS 14 before 2020-09-16 (release) | 516,751 |
| iOS 15+ (released Sep 2021, after dataset end) | 2,259 |

> **Reproducibility note:** every count above uses the **`browser_raw` / `os_raw` column** as the source of the version string (e.g. `Chrome 85` matches `^Chrome 85`), **not** the `user_agent` column. Matching the UA instead yields very different numbers (e.g. `Chrome 85` in the UA → 1.18M), so always run these against the raw columns. Each row is one query against `data/raw/rba-dataset.csv`.

**Impact:** proves the dataset is synthesized (Wiefling et al. 2022) and that raw version strings cannot be trusted for temporal features. Use version-stripped families instead.

### 3.9 Generator-bot traffic — 3,704,894 rows (11.8%) — MEDIUM-HIGH

3.70M User Agent strings carry the generator's own URL `github.com/das-group/rba-dataset`:

| Bot UA | Rows |
|---|---|
| `ZipppBot/0.11 (... das-group ...)` | 1,662,964 |
| `Mozilla/5.0 (compatible; startmebot/1.0 ...)` | 321,325 |
| `ZoomBot (Linkbot 1.0 ...)` | 19,570 |
| `Mozilla/5.0 (compatible; MetaJobBot ...)` | 7,437 |
| Normal-looking UAs also stamped with the URL (e.g. Lumia `... das-group/rba-dataset ...`) | ~1,693,598 |

- 2,020,868 of them have `device = bot`; 349,510 carry attack-IP flags (11.3% of all), 500,565 are "successful" logins
- The single bot user `-4324475583306591935` — 14,025,899 rows (**44.86% of ALL events**), 4 successes, 1,650,627 attack flags = **53% of all attack flags** (concentration problem, same class; handled at sampling — see §7.1)

**Impact:** ~12% of the dataset is the generator's own machinery; treat as a distinct traffic class (flag it, cap it at sampling — never silently train on it as "normal human behavior").

### 3.10 ASN ↔ country mismatch — 15,497,255 rows (49.6%) — MEDIUM

680 ASNs are tagged with 2+ countries; e.g. ASN 29695 (Telenor Norway) spans 6 countries with 8,130,723 rows; ASN 500039 spans 28 countries. Real CDNs/clouds do serve multiple countries, but ~half the dataset is too much — the synthetic geolocation step generated country independently of ASN. (IP→country itself is consistent — see §1 — so use the row's country, not the ASN's.)

### 3.11 VLC media-player UAs — 708,927 rows (2.3%) — LOW

`VLC/3.0.0-git LibVLC/3.0.0-git` — a desktop video player attempting 708,927 logins, **all failed**, 46,023 attack-flagged. A media player cannot do SSO — synthetic noise rows.

### 3.12 Exotic leftover browser families — 713,403 rows (2.3%), 44 families — LOW

Version stripping leaves parser-artifact families: `VLC 3.0.0-git`, `134 Browser`, `1Password`, `Unknown Mac OS X 11_6_3 Browser`, `Bot Mac OS X 11_6_3 Browser`, `Tablet Windows Phone 8_1 Browser`. Caused by `_`-separated versions (`11_6_3`) not being stripped — fixed by the cleaning regex (§5, rule 2).

---

**Root cause of 3.8–3.11:** the RBA dataset is **synthesized** (statistically reconstructed from real login patterns). Versions don't respect the timeline, the generator stamped its own URL into UAs, and geolocation was generated independently of ASN.

---

## 4. Severity summary

| # | Issue | Rows | Severity | Fix |
|---|---|---|---|---|
| 3.1 | Browser↔OS contradiction | 1,223,315 | HIGH | Re-derive OS from UA string |
| 3.3 | Private IP → foreign country / attack flag | 5,266,810 / 506,460 | HIGH | Flag `is_private_ip`, mark geo unreliable |
| 3.2 | mobile device, desktop browser marker | 3,162,207 | MEDIUM | Re-derive device from UA string |
| 3.4 | RTT missing / outliers | 29,993,329 / 79 | MEDIUM | Explicit missing + outlier flags |
| 3.8 | Impossible versions vs date | 1,651,546 | MEDIUM-HIGH | Strip versions; report-only (keep) |
| 3.9 | Generator-bot traffic (das-group UA) | 3,704,894 | MEDIUM-HIGH | Flag `is_generator_bot`; cap at sampling |
| 3.10 | ASN ↔ country mismatch | 15,497,255 | MEDIUM | Keep ASN; trust row country |
| 3.5 | `-` vs NULL | 14,063,591 | LOW | Unify to NULL |
| 3.6 | unknown/bot device | 2,895,205 | LOW | Keep as category |
| 3.11 | VLC media-player UAs | 708,927 | LOW | Flag `is_vlc` |
| 3.12 | Exotic digit browser families | 713,403 | LOW | Regex fix |
| 3.7 | ATO quirks | 65 | LOW | Keep, document |

---

## 5. Cleaning solution (how to preprocess)

**Design principle (from the project roadmap):** preserve raw values for auditability; cleaning **adds normalized columns + flags**, it never silently drops rows.

### Step 1 — Schema

Write the cleaned file with DuckDB directly from the CSV (no 8.5 GB load into RAM):

```
row_id, ts, user_id, rtt, ip, country, region, city, asn, user_agent,
browser_raw, os_raw, device_raw, login_success, is_attack_ip, is_ato,
browser_family, os_family, device_type,
is_private_ip, geo_unreliable, rtt_missing, rtt_outlier,
ua_os_conflict, version_stripped,
is_generator_bot, is_vlc
```

### Step 2 — Fix rules (implemented in `src/00_clean_dataset.py`)

1. **`os_family`** — derived from the User Agent string (source of truth), not the OS column:
   `KaiOS → KaiOS` (os_raw is authoritative — these devices spoof a Chrome/CriOS UA); `Windows Phone → Windows Phone` (checked BEFORE iOS — WP UAs carry a `like iPhone OS` spoof token); `iPhone|iPad|iPod|iOS → iOS`; `Android([^@]|$) → Android` (the `@` excludes `android@` tokens in ChromeOS UAs); `Windows → Windows`; `CrOS → ChromeOS`; `Mac OS X|Macintosh → macOS`; `Linux|X11 → Linux`; else `unknown`. Flag `ua_os_conflict = True` where this differs from the raw OS column (fixes §3.1).
2. **`browser_family`** — raw browser string with version tokens stripped — both `85.0.4183` and `11_6_3` forms: `Chrome Mobile WebView 85.0.4183 → Chrome Mobile WebView`; `Firefox 20.0.0.1618 → Firefox`; `Unknown Mac OS X 11_6_3 Browser → Unknown Mac OS X Browser`. 4,549 distinct strings collapse to ~200 families, so browser updates no longer look like device changes. Flag `version_stripped`. (Fixes §3.12.)
3. **`device_type`** — derived from UA: `iPad → tablet`; `iPhone|iPod|Mobile|Android([^@]|$).*Mobile → mobile` (the `[^@]` guard stops `android@` tokens in ChromeOS UAs from forcing mobile); `Android → tablet`; else `desktop` (fixes §3.2). Raw `bot`/`unknown` values are preserved in `device_raw`.
4. **`is_private_ip`** — `10.x`, `172.16–31.x`, `192.168.x`, `127.x`, `169.254.x` → True (7.29M rows). When True, set **`geo_unreliable = True`** — country/region/city are kept raw but flagged; nothing is fabricated, and the label columns are untouched (fixes §3.3).
5. **RTT** — `rtt_missing` flag (95.9%); `rtt > 60,000 → NULL + rtt_outlier = True` (fixes §3.4).
6. **Missing geo** — `-` and empty strings both → NULL (fixes §3.5).
7. **Timestamps** — parsed to `TIMESTAMP` for chronological processing; `row_id` added because the `index` column is dataset-local.
8. **`is_generator_bot`** — UA matches `ZipppBot|startmebot|ZoomBot|MetaJobBot|das-group` → True (3.70M rows). Kept + flagged; the **sampling** stage decides whether to cap them (fixes §3.9).
9. **`is_vlc`** — UA matches `VLC` → True (708,927 rows, media players can't do SSO — synthetic noise). Kept + flagged (fixes §3.11).

### Step 3 — Verify

Re-run the scan queries on the cleaned file — every §3 count that is *fixable* drops to ~0; the rest become explicit flags instead of silent contamination:

| §3 | After cleaning |
|---|---|
| 3.1 / 3.2 | fixed (re-derived from UA) |
| 3.3 / 3.4 / 3.5 | flagged (`is_private_ip`, `geo_unreliable`, `rtt_missing/outlier`, geo NULL) |
| 3.8 | kept — synthesis artifact, no fix (features use stripped families) |
| 3.9 / 3.11 | flagged (`is_generator_bot`, `is_vlc`) |
| 3.10 | kept — ASN is informational; row country is internally consistent |
| 3.12 | fixed (browser-family token filter: 713,403 rows / 44 families → 735 rows / 11 real names) |

### Step 4 — Do NOT fix (deliberately)

- The 506,460 private-IP attack flags and the 64 un-flagged ATOs stay as labels — the **model** decides what weight to give them (flag columns exist so the ensemble can learn that private-IP "attacks" are noise).
- Positive/negative User IDs — both are legitimate.
- `XK` country code — keep.
- **Generator-bot and VLC rows are kept + flagged** (`is_generator_bot`, `is_vlc`); removal is a **sampling** decision (`--no-genbots` / `--no-vlc` in the sampling script), never a cleaning decision.
- **Impossible version-vs-date rows (5.3%)** — kept; it's a synthesis artifact with no fix. Features use version-stripped `browser_family` / `os_family`, never raw versions.
- No rows are deleted; a cleaning job must not change the row count (31,269,264 → 31,269,264). Any drop must be intentional and logged.

---

## 6. Reproducibility

Every number in this report is produced by the checks in `src/00_clean_dataset.py --verify`, which re-runs them on any file and prints a comparison table. Rerun after any dataset change.

---

## 7. Blind re-audit (Aug 8, 2026) — full re-derivation without doc context

An independent pass was run against `data/raw/rba-dataset.csv` deriving every number fresh (no prior scan output as input). Purpose: catch what the earlier two scans inherited rather than measured.

### 7.1 Independently re-derived facts (all match this report)

| Fact | This report | Blind re-derivation |
|---|---|---|
| Rows / users / countries | 31,269,264 / 4,304,857 / 229 | same |
| Success / fail | 12,541,442 / 18,727,822 | same |
| Attack-IP / attack+success | 3,096,977 / 804,491 | same |
| ATO rows / users / attack-flagged | 141 / 138 / 77 | same |
| ATO from private IP | 39 | same |
| Robot rows / successes / countries / attack flags | 14,025,899 / 4 / 227 / 1,650,627 | same (44.86% of rows, 53.3% of attack flags) |
| Top-41 users' attack share | — | 53.7% |
| Heavy users (≥10 attacks) / their events | 8,122 / ~14.2M | same (14,264,175) |
| Private IPs / non-NO / attack-on-private / private-success | 7,291,335 / 5,266,810 / 506,460 / 1,920,195 | same |
| RTT missing / >60 s / max | 29,993,329 / 79 / 223,457 | same |
| Region/City dash-dash / dash-set / NULLs | 13,895,698 / 117,683 / 55,999 | same |
| Impossible versions (Chrome-85 / Android-11 / iOS-14 / Chrome 90+) | 7,337 / 38 / 516,751 / 239,712 | same |
| Browser↔OS contradictions | 1,223,315 | same |
| Duplicate rows (whole or key fields) | 0 | same |
| Generator-bot / VLC | 3,704,894 / 708,927 | same |
| Median / p90 events per user | 2 / 9 | same |

### 7.2 What the blind pass found that the earlier scans missed

| Finding | Rows | Why it was missed |
|---|---|---|
| **KaiOS population is 339,945 total** — OS column says `KaiOS` for 278,811 rows, but only 65,233 UAs carry a KaiOS token. The other ~213K are LYF F220B / Nokia 8110 4G KaiOS phones whose UAs say `Android` (205,821), are platform-silent (69,172), or say `iPhone` (5,673) | 278,811 | Earlier scans only counted the UA-token subset; the os_raw authoritative fallback was never checked |
| **`device=tablet` but UA has no tablet marker** | 691,864 | §3.2 only audited the *mobile* side of the device marker issue |
| **`os_raw = "Other "`** (2,883,889 rows, 2,754,361 of them UA-silent) — a 9.2% OS category never documented | 2,883,889 | No scan ever grouped the raw OS column by distinct value |
| **UA completely silent on platform** (no OS token at all) | 3,006,003 | §3.1 counted contradictions, not absences |
| **`device=desktop` but UA says mobile** | 3,388 | Small, opposite direction of the big §3.2 count |
| **`device=mobile` but UA silent** | 30,680 | Small subset of §3.2's browser-based count |
| **Device Type NULL** | 1,526 | Earlier scan said "no NULLs" — checked Browser/OS only |
| **Short UAs (<15 chars)** | 9,715 | Never quantified |

### 7.3 What this means for the pipeline

- **KaiOS is a real OS family in this dataset (339,945 rows, 1.1%)** — it must be its own `os_family` (already done in `src/00_clean_dataset.py`; the union `os_raw LIKE KaiOS OR UA LIKE KaiOS` = 339,945 exactly matches the cleaned parquet's `KaiOS` total, so the fix is complete and the earlier "74,845" figure was just the UA-token subset).
- `os_raw = "Other "` rows are mostly bot/unknown traffic — check they don't pollute `browser_family` features.
- The 3,388 desktop-but-Android-UA rows and 30,680 mobile-but-silent-UA rows should be eyeballed during sampling, not cleaning.
- **Lesson:** a scan that only re-checks previous findings inherits their blind spots. The blind pass found 8 new issues solely because it re-derived counts from scratch and grouped by distinct raw values. Every future scan should start from the raw CSV, not from this report.
