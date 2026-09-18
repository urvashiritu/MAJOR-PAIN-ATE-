# LANL Anomaly Detection — Live Demo System

## Architecture

```
login (TOTP + password) → employee view (model scores event) → Welcome/Access Denied
                        → analyst dashboard (historical batch + live events polling)
```

### Components

| File | What | Lines |
|------|------|-------|
| `live/app.py` | Flask backend — routes, live events, pre-aggregated dashboard | 280 |
| `live/scorer.py` | Live scoring engine — 21 features, LGB + LSTM-AE, ~19ms/event | 388 |
| `live/auth.py` | TOTP + password auth for 5 demo users | 116 |
| `live/db.py` | DuckDB connection, FEATURE_COLS, SCORES_PARQUET path | 168 |
| `live/templates/login.html` | Terminal/corporate SSO themed login page | - |
| `live/templates/employee.html` | Welcome/Access Denied page (no scores shown) | 170 |
| `live/templates/index.html` | SOC analyst dashboard (KPIs, charts, alerts, live logins) | 139 |
| `live/static/js/api.js` | API fetch wrappers (dashboard, alerts, liveEvents, health) | 25 |
| `live/static/js/app.js` | Dashboard controller — renders KPIs, charts, live poll | 170 |
| `live/static/js/charts.js` | Chart.js dark theme configs (timeline, distribution) | 191 |
| `live/static/css/style.css` | Dark theme design system | 480 |

### Data

| Path | Size | Rows | Purpose |
|------|------|------|---------|
| `data/raw/lanl/lanl.duckdb` | ~2GB | 29.9M feat rows | Source database (read-only) |
| `data/processed/lanl_scores.parquet` | 370MB | 29.9M rows | Precomputed batch scores |
| `models/lanl_lgb_21feat.joblib` | - | - | LGB model (threshold=0.187195) |
| `models/lanl_lstm_ae_2ep_bs128_*.pt` | - | - | LSTM-AE model (4.8M params) |

---

## How It Works

### Login Flow

1. User enters username + password + TOTP at `/login`
2. `auth.py` verifies password (constant-time compare) + TOTP (pyotp, valid_window=1)
3. Employee users → `/employee` (model scores their most common login pattern)
4. SOC analyst → `/analyst` (dashboard)

### Scoring (employee route)

The employee route simulates the user's most recent login event:

```python
time_val = _scorer._last_timestamps.get(user_id, 0) + 60
hour = int((time_val % 86400) // 3600)
src_pc = next(iter(_scorer._seen_src_computers.get(user_id, {'C0'})), 'C0')
dst_pc = next(iter(_scorer._seen_dst_computers.get(user_id, {'C0'})), 'C0')
score, decision, _ = score_event(user_id, src_pc, dst_pc, 'NTLM', 'Network', hour, time_val)
```

This uses the user's **most common source computer** — the model scores based on behavioral anomaly. Normal logins from known machines → ALLOW. This is correct UEBA behavior: it detects anomalous behavior, not bad users.

### 21 Features

| # | Feature | Description |
|---|---------|-------------|
| 1 | dst_first | First time this dst for user? |
| 2 | src_first | First time this src for user? |
| 3 | hour_ratio | Events at this hour / total events |
| 4 | dst_prior_events | Total events to this dst (all users) |
| 5 | fail_1h | Failed logins in last hour |
| 6 | vel_1h | Total logins in last hour |
| 7 | hour_sin | sin(hour/24 * 2π) |
| 8 | hour_cos | cos(hour/24 * 2π) |
| 9 | is_ntlm | 1 if NTLM auth |
| 10 | pair_first | First time this (user,src,dst) combo? |
| 11 | src_dst_pair_first | First time this (src,dst) pair globally? |
| 12 | fail_rate | fail_1h / (vel_1h + 1) |
| 13 | dst_first_x_ntlm | dst_first * is_ntlm |
| 14 | log_pair_rank | log(row_number of this pair + 1) |
| 15 | pair_freq_ratio | pair_count / user_total |
| 16 | is_rare_hour | Is this hour in user's rare hours? |
| 17 | pairs_last_100 | Always 0 (training artifact) |
| 18 | iat_zscore | Inter-arrival time z-score |
| 19 | velocity_ratio | vel_1h / (vel_24h + 1) |
| 20 | machine_popularity | Distinct users on this dst |
| 21 | lstm_ae_recon_error | LSTM-AE reconstruction error |

### Feature Importances (top 5)

1. hour_sin (3423)
2. hour_cos (3291)
3. hour_ratio (3215)
4. machine_popularity (3205)
5. vel_1h (2971)

### Live Events Collection

When an employee logs in, `score_event()` is called and the result is appended to `_live_events` (in-memory list, capped at 100 entries). The `/api/live_events` endpoint returns the last 50 events. The dashboard polls this endpoint every 2 seconds and renders events in the "Live Logins" table.

### Dashboard

Pre-aggregated on startup for fast responses:
- `/api/dashboard` → cached KPIs + timeline + top_users + heatmap
- `/api/alerts` → cached top 200 alerts above threshold
- `/api/live_events` → live events from employee logins (real-time)

---

## Demo Users

| Username | Display | User ID | Password | Role | Behavior |
|----------|---------|---------|----------|------|----------|
| luffy | Luffy | U2899@DOM1 | mugiwara | employee | ALLOW (normal) |
| ace | Ace | U293@DOM1 | salvatore | employee | BLOCK (anomalous pattern) |
| igris | Igris | U2097@DOM1 | shadow01 | employee | ALLOW (normal) |
| ashborn | Ashborn | U66@DOM1 | monarch99 | employee | ALLOW (normal login) |
| soc_admin | SOC Analyst | none | defender | analyst | Dashboard only |

### TOTP

Secrets stored in `live/.totp_secrets.json`. TOTP codes shown on login page when `LANL_DEV=1`.

---

## Running

### Start Server

```bash
cd lanl-anomaly
LANL_DEV=1 python3 -m live.app
```

Startup sequence:
1. Load 30M row parquet (~2s)
2. Pre-aggregate dashboard data (timeline, top users, heatmap, alerts) (~3s)
3. Initialize scorer: load models (~2s), precompute global context (~13s), per-user context (~0.1s each)
4. Flask server on http://localhost:5000

### API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/health` | GET | no | Server status |
| `/api/dashboard` | GET | no | Pre-aggregated dashboard data |
| `/api/alerts` | GET | no | Top 200 alerts above threshold |
| `/api/live_events` | GET | no | Last 50 live login events |
| `/api/score` | POST | yes | Score a custom login event |

---

## Bugs Fixed During Development

1. **`precompute_global()` missing `global` declarations** — all dicts were local variables, never assigned to module state. Fixed by adding `global` for all 11 dicts.

2. **Dashboard 500 — KeyError 'user'** — `heatmap_data` comprehension used `r['user']` and `r['score']` but DataFrame columns are `src_user` and `mean_score`. Fixed column names.

3. **Dashboard slow on every request** — 30M row groupby on every HTTP request (~3s). Fixed by pre-aggregating on startup and caching in `_cached_dashboard`/`_cached_alerts`.

4. **Live events not on dashboard** — Employee route scored events but didn't feed results to dashboard. Fixed by adding `_live_events` collection, `/api/live_events` endpoint, and 2s polling panel.

---

## Known Limitations

- **Server is single-threaded** (Flask dev server) — concurrent requests block each other
- **Live events are in-memory** — lost on server restart
- **Employee route uses most common source** — shows correct UEBA behavior but ashborn/luffy/igris all get ALLOW for normal logins (model detects anomalous behavior, not bad users)
- **Dashboard precomputed data is static** — doesn't update with new batch scores
- **LSTM-AE tokenization** — unknown sources map to token 0, still produces meaningful recon errors
