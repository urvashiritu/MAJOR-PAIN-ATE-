# LANL Anomaly Detection — Live System

## Components

| File | Use | Lines |
|------|-----|-------|
| `live/app.py` | Flask backend. Routes, live events, dashboard data | 1183 |
| `live/scorer.py` | Scoring engine. 21 features, LGB + LSTM-AE | 388 |
| `live/replay.py` | Replays real scored events | 131 |
| `live/auth.py` | Password and TOTP for 5 users | 122 |
| `live/db.py` | Paths, 21 feature names, DuckDB connection | 168 |
| `live/templates/` | Login, analyst dashboard, dataset, employee | — |
| `live/static/js/` | Router, API client, ECharts, components | — |
| `live/static/css/style.css` | Dark theme | 1169 |

## Data

| Path | Size | Rows | Use |
|------|------|------|-----|
| `data/raw/lanl/lanl.duckdb` | 9.7 GiB | 29.9M | Source events. Read only |
| `data/processed/lanl_scores.parquet` | 370 MB | 29.9M | Model scores |
| `models/lanl_lgb_21feat.joblib` | 3.3 MB | — | LGB. The threshold is 0.187195 |
| `models/lanl_lstm_ae_2ep_bs128_*.pt` | 20 MB | — | LSTM-AE. 4,865,002 parameters |

## How the system works

### Sign in

1. The user enters a name, a password, and a TOTP code at `/login`.
2. `auth.py` checks the password with a constant-time compare. Then it checks the
   TOTP code with `pyotp`.
3. An employee goes to `/employee`.
4. An analyst goes to `/analyst`.

The system scores the most recent login of the employee. The system uses the most
common source computer for the user. A login from a known machine produces ALLOW.
This is correct UEBA behavior. The system finds abnormal behavior. It does not
find bad users.

### The 21 features

| # | Name | Meaning |
|---|------|---------|
| 1 | `dst_first` | First time the user sees this destination |
| 2 | `src_first` | First time the user uses this source |
| 3 | `hour_ratio` | Events in this hour, divided by all events |
| 4 | `dst_prior_events` | All events to this destination |
| 5 | `fail_1h` | Failed logins in the last hour |
| 6 | `vel_1h` | Logins in the last hour |
| 7 | `hour_sin` | Sine of the hour |
| 8 | `hour_cos` | Cosine of the hour |
| 9 | `is_ntlm` | 1 if the method is NTLM |
| 10 | `pair_first` | First time this user uses this machine pair |
| 11 | `src_dst_pair_first` | First time any user uses this machine pair |
| 12 | `fail_rate` | `fail_1h` divided by `vel_1h` + 1 |
| 13 | `dst_first_x_ntlm` | `dst_first` multiplied by `is_ntlm` |
| 14 | `log_pair_rank` | Logarithm of the row number of the pair |
| 15 | `pair_freq_ratio` | Pair count divided by the user total |
| 16 | `is_rare_hour` | The hour is rare for this user |
| 17 | `pairs_last_100` | Always 0. An artifact of training |
| 18 | `iat_zscore` | Z-score of the time between events |
| 19 | `velocity_ratio` | `vel_1h` divided by `vel_24h` + 1 |
| 20 | `machine_popularity` | The number of users on this machine |
| 21 | `lstm_ae_recon_error` | Error from the LSTM autoencoder |

### Decisions

The threshold is 0.187195. The flag threshold is 0.7 of this value.

| Condition | Decision |
|-----------|----------|
| Score is above 0.187195 | BLOCK |
| Score is above 0.131 | FLAG |
| All other scores | ALLOW |

### Replay

The replay window contains events 765000 through 767000. The window has 9,954
real events. Of these, 20 are red team attacks.

The team chose the window for one reason. Source machine `C17693` authenticates
as many users against many new destinations. This activity is lateral movement.

Run 14 scored the complete dataset. The run found 590 of 702 attacks. The run
also gave 349 false positives.

## Running

```bash
cd lanl-anomaly
LANL_DEV=1 venv/bin/python -m live.app
```

Startup runs these steps.

1. Load 29.9M scored rows from the parquet. This takes 2 seconds.
2. Aggregate the dashboard data. This takes 3 seconds.
3. Load the models. This takes 2 seconds.
4. Build the global context from 604 users. This takes 13 seconds.
5. Start the replay.
6. Serve on `http://localhost:5000`.

The total time is about 20 seconds.

### Settings

| Name | Default | Meaning |
|------|---------|---------|
| `LANL_DEV` | unset | Show the passwords and the TOTP codes on the login page |
| `LANL_AUTOPLAY` | `1` | Start the replay on boot |
| `LANL_REPLAY_SPEED` | `20` | Events each second. The range is 1 to 500 |

**Warning:** `LANL_DEV` shows live credentials. Do not use it on a server that
the public internet can reach.

## Pages

| Route | Page |
|-------|------|
| `/` | Redirect to `/analyst`. Signs in as the demo analyst |
| `/login` | TOTP and password |
| `/analyst` | Live Monitoring |
| `/analyst/dataset` | Dataset Analysis |
| `/#/behavior` | Behavior Insights |
| `/#/model` | Model Performance |
| `/#/alerts` | Alerts |
| `/#/users` | Users |
| `/#/settings` | Settings |

## API

| Endpoint | Method | Auth | Use |
|----------|--------|------|-----|
| `/api/health` | GET | no | Server status |
| `/api/dashboard` | GET | no | KPIs, recent events, alerts |
| `/api/alerts` | GET | no | Alerts above the threshold |
| `/api/users` | GET | no | Users in the replay window |
| `/api/user_profile/<id>` | GET | no | Behavioral baseline for one user |
| `/api/investigation/<id>` | GET | no | All features for one event |
| `/api/model/metrics` | GET | no | Held-out metrics, importances |
| `/api/dataset/dashboard` | GET | no | KPIs for all 29.9M events |
| `/api/search?q=` | GET | no | Search users, events, alerts |
| `/api/alerts/<id>/ack` | POST | no | Acknowledge an alert |
| `/api/replay/status` | GET | no | Replay position |
| `/api/replay/start` | POST | no | Start the replay |
| `/api/replay/stop` | POST | no | Stop the replay |
| `/api/replay/reset` | POST | no | Go to the first event |
| `/api/replay/jump_attack` | POST | no | Go to the next real attack |
| `/events/stream` | GET | no | SSE. One message for each event |

## Demo users

The values in this table are test data. They are not real accounts.

| Name | User ID | Password | Role | Result |
|------|---------|----------|------|--------|
| `luffy` | U2899@DOM1 | mugiwara | employee | ALLOW |
| `ace` | U293@DOM1 | salvatore | employee | BLOCK |
| `igris` | U2097@DOM1 | shadow01 | employee | ALLOW |
| `ashborn` | U66@DOM1 | monarch99 | employee | ALLOW |
| `soc_admin` | none | defender | analyst | Dashboard |

The script stores the secrets in `live/.totp_secrets.json`. The script creates
the file on the first run. Git does not track the file.

## Known limits

- The Flask development server serves the app. It is not for production use.
- Live events are in memory. A restart removes them.
- The replay shows 9,954 events. It does not show all 29.9M events.
- The demo user `ace` authenticates from a machine that the model knows. The
  BLOCK result comes from the replay window, not from the employee path.