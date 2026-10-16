# UI-REVIEW.md — LANL Anomaly Detection Live Demo

> **This file was rewritten on 2026-10-04.** The previous version was dated
> Sep 20 and audited a different application. At that time the live dashboard
> generated its own synthetic events, so several findings below no longer
> describe the current build. Findings have been re-verified against the
> running app; anything unverified is marked as such rather than asserted.

> **Updated 2026-10-16.** The findings below are kept as written on 2026-10-04.
> Four of them no longer describe the shipped build. They are corrected here
> rather than edited in place, so the review history stays intact.
>
> - **The dataset figures moved.** A log-base bug in the offline pipeline made
>   `log_pair_rank` disagree with training: DuckDB's `log` is base 10 and
>   `np.log1p` is natural. Fixed, and the parquet rebuilt. Item 3 under "Known
>   limitations" quotes 591/702 caught at 349 false positives; the shipped
>   build is 598/702 at 269. The held-out figures are unchanged at 136/240 and
>   183 false positives, PR-AUC 0.3682.
> - **Item 4 is resolved.** Model Performance figures are no longer hardcoded
>   in JavaScript. `renderModelPerformance()` reads `/api/model/metrics`, which
>   recomputes the held-out metrics from the parquet at boot. The page says so
>   when the displayed values reproduce the training run, and discloses the
>   difference when they do not.
> - **The employee page is no longer random.** Pillar 6 describes it as
>   "randomly generated". It now scores one real successful sign-in drawn from
>   that user's own history, and the page says so: "Real inputs, real models.
>   The machine, hour and authentication type are a genuine sign-in taken from
>   this user's own history." Measured in a browser: one login per employee
>   account, all four scored 0.0 and returned ALLOW. The retired random draw
>   showed a normal user "ACCESS DENIED" on 4 of 14 page loads.
> - **Access control was missing and now exists.** `/analyst` and
>   `/analyst/dataset` checked only "is somebody logged in", so an employee
>   session could load the entire dashboard by typing the URL. The analyst
>   `/api/*` endpoints checked nothing at all, and five of them were verified
>   answering 200 to a bare `curl` with no cookies. Both now require the
>   analyst role: 401 with no session, 403 for an employee. With `LANL_DEV=1`
>   the route signs the session in as the demo analyst instead, so the presenter
>   still reaches the dashboard with one keystroke.
>
> Item 2 still stands and is the reason every employee login reads ALLOW: the
> live serving path scores real sign-ins at 0.0 against a 0.187 threshold.

## Data honesty (the issue that mattered)

The previous build invented its data. `simulate_login_burst()` drew machine
names, hours and auth types with `random.choice`, and the BLOCK shown for a
known attacker came from a hardcoded `THRESHOLD + 0.15` rather than from the
model. Three further pages (Alerts, Users, Behavior Insights) presented that
fabricated data with no label.

Current state, all verified:

| Page | Source | Verified |
|---|---|---|
| Live Monitoring | real scored events from `lanl_scores.parquet` | 9,954-event window, ground-truth column shown |
| Alerts | real replay events, tagged with `is_red` | states when the model was wrong |
| Users | real replay events | per-user caught / missed / false positives |
| Behavior Insights | training baseline **and** replay window, labelled separately | banner explains the two sources |
| Search, investigation, ack, stats | real replay window | simulated data reachable only via `/api/simulation` |
| Simulation Lab | synthetic, behind an amber banner | Truth column reads `n/a` |

`reports/experiment_log.md` (RUN 14) had already concluded the model produces
meaningful scores on the full dataset and that the live demo needed rebuilding.

## Pillar 1: Copywriting — 4/4

- Replay table, KPI tiles and narrative describe real scored events
- Alerts state accuracy plainly: "Confirmed red-team attack. Model detection
  was correct." and "Normal traffic the model flagged. False positive."
- The narrative reports misses rather than hiding them
- Empty states direct the user to the replay controls instead of describing
  the retired pipeline

## Pillar 2: Visuals — 3/4

Fixed since the previous review:

- Topbar subtitle no longer wraps to three lines (verified 16px / 1 line at a
  1100px viewport); `.topbar-left-inner` needed `min-width: 0`
- Loading skeletons added for the dashboard alerts table, the Alerts and Users
  tables, and Behavior Insights. Verified 3 rows on first paint, 0 after load
- Users page no longer leaves dead space; a table footer carries catch rate,
  caught, missed and false positives

Remaining:

- The Users page is still sparse when few users have been replayed
- No skeleton exists for ECharts canvases specifically, so charts still pop in

## Pillar 3: Color — 3/4

- Semantic colors are used consistently: red = threat, amber = flagged or
  false positive, green = allowed
- Simulation Lab uses an amber banner so synthetic data is visually distinct
  from real data

Not re-audited in detail: the two-greens issue and chart contrast noted in the
previous review were not re-measured.

## Pillar 4: Typography — 3/4

Not re-audited. The previous review's notes on font loading across templates
were not re-verified.

## Pillar 5: Spacing — 3/4

Fixed: hardcoded percentage KPI columns that squeezed the fifth tile are gone;
the grid is now `repeat(4, 1fr)` with four tiles.

Not re-audited: employee-page container width and login form field gaps.

## Pillar 6: Experience Design — 3/4

Fixed:

- Employee page labels its decision as a "Simulated check" and explains that
  the events are randomly generated
- Header role no longer hardcoded to "Analyst", so logging in as an employee
  no longer renders an employee name beside the analyst role
- Footer no longer claims "Real Users. Real Behavior. Real Security."
  unconditionally
- `destroyCharts()` now clears all five ECharts references; it previously left
  three pointing at disposed instances, which broke charts when navigating
  away from the dashboard and back

## Known limitations, stated plainly

1. The demo replays a single 9,954-event window. It is real data, but it is a
   slice, not all 29.9M events.
2. Live scoring of freshly generated events is weak because of
   training-serving skew (`experiment_log.md`): incremental in-memory features
   against a model trained on batch SQL features, giving live scores near 0.001
   against a 0.187 threshold. The proper fix is retraining, not threshold
   tuning.
3. Two different metric sets exist and must be labelled when presented:
   full-dataset figures (591/702 caught, 349 false positives) include training
   rows, while the held-out test split from RUN 9 gives 136/240 at 183 false
   positives. The honest headline number is the test-split one.
4. Model Performance figures on that page are hardcoded in JavaScript rather
   than read from a results file, so they can drift from the experiment log.