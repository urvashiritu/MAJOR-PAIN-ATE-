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

The system scored the complete dataset and found 598 of 702 attacks, with 269
false positives.

## Running

```bash
cd lanl-anomaly
LANL_DEV=1 venv/bin/python -m live.app
```

Startup runs these steps. The times are measured from a real boot.

1. Load 29.9M scored rows from the parquet. This takes 2 seconds.
2. Aggregate the dashboard data. This takes 15 to 17 seconds. This is the
   longest step.
3. Load the models. This is immediate.
4. Build the global context from 8085 machines and 604 users. This takes about
   11 seconds.
5. Prepare the four per-user contexts and the real login samples. This takes
   about 2 seconds.
6. Start the replay.
7. Serve on `http://localhost:5000`.

The total time is about 32 seconds.

### Settings

| Name | Default | Meaning |
|------|---------|---------|
| `LANL_DEV` | unset | Show the passwords and the TOTP codes on the login page. Also signs the session in as the demo analyst on `/` and `/analyst` |
| `LANL_AUTOPLAY` | `1` | Start the replay on boot |
| `LANL_REPLAY_SPEED` | `20` | Events each second. The range is 1 to 500 |

**Warning:** `LANL_DEV` shows live credentials and opens the analyst pages to
anyone who can reach the port. Do not use it on a server that the public
internet can reach.

## Pages

The analyst pages need the SOC analyst role. An employee account that opens
`/analyst` is sent back to `/employee`. The employee accounts exist to generate
sign-in events, not to read the analyst views.

| Route | Page | Who |
|-------|------|-----|
| `/` | Redirect to `/analyst`. Signs in as the demo analyst when `LANL_DEV=1` | anyone |
| `/login` | TOTP and password | anyone |
| `/employee` | One scored login for the signed-in employee | employee (an analyst is redirected to `/analyst`) |
| `/analyst` | Live Monitoring | analyst |
| `/analyst/dataset` | Dataset Analysis | analyst |
| `/#/behavior` | Behavior Insights | analyst |
| `/#/model` | Model Performance | analyst |
| `/#/alerts` | Alerts | analyst |
| `/#/users` | Users | analyst |
| `/#/settings` | Settings | analyst |

Without `LANL_DEV`, an employee that opens `/analyst` is redirected to
`/employee` and an anonymous visitor is redirected to `/login`. With
`LANL_DEV=1` the route signs the session in as the demo analyst instead, so a
presenter can return to the dashboard with one keystroke after showing an
employee login.

## API

| Endpoint | Method | Auth | Use |
|----------|--------|------|-----|
| `/api/health` | GET | no | Server status |
| `/api/dashboard` | GET | analyst | KPIs, recent events, alerts |
| `/api/alerts` | GET | analyst | Alerts above the threshold |
| `/api/users` | GET | analyst | Users in the replay window |
| `/api/user_profile/<id>` | GET | analyst | Behavioral baseline for one user |
| `/api/investigation/<id>` | GET | analyst | All features for one event |
| `/api/model/metrics` | GET | analyst | Held-out metrics, importances |
| `/api/dataset/dashboard` | GET | analyst | KPIs for all 29.9M events |
| `/api/search?q=` | GET | analyst | Search users, events, alerts |
| `/api/alerts/<id>/ack` | POST | analyst | Acknowledge an alert |
| `/api/simulation` | GET | analyst | Logins generated by the employee page |
| `/api/replay/status` | GET | analyst | Replay position |
| `/api/replay/start` | POST | analyst | Start the replay |
| `/api/replay/stop` | POST | analyst | Stop the replay |
| `/api/replay/reset` | POST | analyst | Go to the first event |
| `/api/replay/jump_attack` | POST | analyst | Go to the next real attack |
| `/events/stream` | GET | analyst | SSE. One message for each event |

An endpoint marked `analyst` answers `401` to a visitor with no session and
`403` to an employee session. `/api/health` stays open so a monitor can poll it.

## Demo users

The values in this table are test data. They are not real accounts.

| Name | User ID | Password | Role | Result |
|------|---------|----------|------|--------|
| `luffy` | U2899@DOM1 | mugiwara | employee | ALLOW |
| `ace` | U293@DOM1 | salvatore | employee | ALLOW |
| `igris` | U2097@DOM1 | shadow01 | employee | ALLOW |
| `ashborn` | U66@DOM1 | monarch99 | employee | ALLOW |
| `soc_admin` | none | defender | analyst | Dashboard |

Every employee login shows ALLOW. The page scores one real successful sign-in
taken from that user's own history, so the verdict is stable. Measured in a
browser: one login per account, all four scored 0.0 and returned ALLOW.

The attacks appear on the analyst side instead. The replay window holds 20
confirmed red-team events, and Dataset Analysis covers all 702. `ace` is the
account with the clearest red-team activity in the data: 31 of his 241,473
events are red, and the model scores every one of them a BLOCK. The employee
page draws only successful sign-ins that are not red events, so none of those
31 can appear there.

The script stores the secrets in `live/.totp_secrets.json`. The script creates
the file on the first run. Git does not track the file.

## Known limits

- The Flask development server serves the app. It is not for production use.
- Live events are in memory. A restart removes them.
- The replay shows 9,954 events. It does not show all 29.9M events.
- The demo user `ace` authenticates from a machine that the model knows. The
  BLOCK result comes from the replay window, not from the employee path.