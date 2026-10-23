# LANL UEBA — 5-Second Demo Doc

**TL;DR:** Real login → real score → new live row. Click the row → see why. Replay → 20/20 attacks caught. Don't demo cold start.

## Run it

```bash
cd lanl-anomaly   # skip if already here
LANL_DEV=1 LANL_REPLAY_SPEED=500 venv/bin/python -m live.app
```

Wait for `starting server on http://localhost:5000` (~30 sec).

Fast replay: `500/s` finishes in ~20 sec. Want to watch it? Use the default `20/s`.

`LANL_DEV=1` is demo-only. It shows the current TOTP code on the login page.

## Open 2 windows

| Window | URL | Who |
|---|---|---|
| Normal | `http://localhost:5000/analyst` | Analyst (auto in dev mode) |
| Incognito | `http://localhost:5000/login` | Employee |

Why incognito? Logging in as the employee replaces the session in that browser.

## 60-second demo

1. Analyst window → **Live Monitoring**. Point at the empty table.
2. Employee window → `igris` / `shadow01` / TOTP code shown on the page.
3. Employee page says **Access granted** + **Your baseline**.
4. Analyst window → new row pops in. Toast. Green flash.
5. Click the row → drawer: score, Why, baseline bars, 21 features.
6. Say: **"It didn't call this an attack. It compared it to Igris's own history."**
7. Replay Feed → **20/20** attacks caught, **12** false positives.

## What the numbers mean

| Thing | Meaning |
|---|---|
| Score `3.35e-8` | Tiny = normal. Block threshold is `0.187195`. |
| `190 logins/hr` | This login's hourly volume. |
| `percentile 26.0` | Igris's own history: 26% of his hours are quieter. |
| `median 209` | His normal hour is 209 logins. |
| `284,931` | Prior events used for his baseline. |

Numbers drift a little each login. That's expected. The story stays the same.

## Say this

- "Real LANL features, real model, real score. Only the clock is synthetic."
- "The model scores the event, not the person."
- "This is normal for Igris. That's why it's ALLOW."
- "The replay catches 20/20 red-team events in this window. It also flags 12 normal events. That's the tradeoff."
- "Held-out split: 136 of 240 attacks caught. It's not magic."

## Do NOT say

- "Igris is an attacker." No. This is a normal login.
- "100% accurate." No. 20/20 is this curated window; held-out is 136/240.
- "Cold start works." Not demoed. The explanation branch is tested; the model behavior is not.
- "The score is zero." It's tiny, not zero. Exponential notation is intentional.

## If it breaks

- No new row? Check `http://localhost:5000/api/health`, then refresh the analyst tab.
- Scores show `0.000000`? Hard refresh with `Ctrl+Shift+R` (stale JS).
- Replay already done? Press Reset, or restart with the default speed.
- Login code fails? Use the code shown on the page; codes rotate every 30 sec.
- Restart wipes live rows. That's expected.

## Verified (last run)

- Real `/login` → `302` → `/employee`; igris ALLOW.
- Live score `3.35e-8`; `190/hr`; p`26.0`; median `209`; history `284,931`.
- SSE live row + toast + drawer; 21 features; no cold-start panel.
- Replay `9,954/9,954`; `20` caught; `0` missed; `12` flagged.
- Dataset `29.9M`; `702` red; held-out `136/240`.
- Mobile 390 px: no horizontal body scroll; drawer fits.
- Console: 0 errors after reload.

## What's new

- P0: adaptive scores (no more `0.000000`), per-user percentile Why, employee baseline note, cold-start guard.
- P1: clickable live drawer, toast, row flash, NEW badge, name/ID split, auth-type label, percentile bars, mobile fixes.
- Core P0/P1 commit: `22827a4` on `exp/live-feature-parity`.
