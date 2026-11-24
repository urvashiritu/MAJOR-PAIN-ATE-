# LANL UEBA — Demo Runbook (tomorrow)

**TL;DR:** Replay = the ML detection story (20/20). Live = normal ALLOW + a real
dormant-account BLOCK + a labelled brute-force rule. Nothing is forced.

## Run it

```bash
cd lanl-anomaly
LANL_DEV=1 LANL_REPLAY_SPEED=500 venv/bin/python -m live.app
```

Wait for `starting server on http://localhost:5000` (~30 sec).

Fast replay: `500/s` finishes in ~20 sec. Want to watch it? Use the default `20/s`.

`LANL_DEV=1` shows the TOTP code and the demo controls on the employee page.

## Open 2 windows

| Window | URL | Who |
|---|---|---|
| Normal | `http://localhost:5000/analyst` | Analyst (auto in dev mode) |
| Incognito | `http://localhost:5000/login` | Employee |

Why incognito? Logging in as the employee replaces the session in that browser.

## Demo users

| Name | Username | Password | User ID |
|---|---|---|---|
| Alex | `alex` | `alex2026` | U2899@DOM1 |
| Sam | `sam` | `sam2026` | U293@DOM1 |
| Maya | `maya` | `maya2026` | U2097@DOM1 |
| Leo | `leo` | `leo2026` | U66@DOM1 |

TOTP code is shown on the login page in dev mode.

## The 3-minute demo

1. **Replay Feed** (analyst) → **20/20** attacks caught, 12 false positives.
   Say: *"Real LANL window. The model caught every red-team event."*
2. **Login as Alex** (incognito) → **Access granted**, score `0.0000`.
   Say: *"Normal sign-in. Real inputs, real model."*
3. On the employee page, click **Dormant + new device**.
   → **Access Denied**, score `0.6727`, BLOCK.
   Say: *"The account was silent for an hour, then an NTLM login from a machine
   it has never used. The model blocked it."*
4. Click **Reset demo state**, then **10 failed logins** → **Flagged**.
5. Click **25 failed logins** → **Blocked**.
   Say: *"The model doesn't see live failures, so a labelled brute-force rule
   handles them: 10 flags, 25 blocks."*
   The page says **Brute-force rule** and shows **Model score 0.0000** next to
   it. That is deliberate: the rule escalated, the model did not score it.
6. Analyst window → **Live Monitoring** → the rows are there with their reasons.
7. **Users / Dataset** → Alex, Sam, Maya, Leo · 29.9M events · 702 red.

## What the numbers mean

| Thing | Meaning |
|---|---|
| `0.0000` | Normal score. Block threshold is `0.187195`. |
| `Model score 0.0000` | Shown only when the brute-force rule escalated. The model scored the login normal; the rule made the decision. |
| `0.6727` | Alex's dormant-account BLOCK score. |
| `iat_z 989.6` | The one-hour gap is far outside Alex's normal timing. |
| `20/20` | Red-team events caught in the 9,954-event replay window. |
| `12` | Normal events the replay also flagged. That is the tradeoff. |

## Say this

- "Real LANL features, real model, real score. Only the clock is synthetic."
- "The model blocked the dormant account on a new device."
- "The brute-force rule blocked the 25 failures. That is a rule, not the model."
- "The replay catches 20/20 in this window. It also flags 12 normal events."
- "LANL has no real names in the data. Alex, Sam, Maya and Leo are labels."

## Do NOT say

- "The model blocked the brute force." It doesn't. The rule does.
- "The model blocked a live login because the machine was rare." At a normal
  first login that scenario scores ALLOW; the BLOCK comes from the one-hour gap
  plus the new device.
- "100% accurate." 20/20 is this curated window. Held-out is 136/240.
- "The score is exactly zero." It is tiny; the UI shows `0.0000`.

## If it breaks

- No new row? Check `http://localhost:5000/api/health`, then refresh the analyst tab.
- Scores show `0.000000`? Hard refresh with `Ctrl+Shift+R` (stale JS).
- Replay already done? Press Reset, or restart with the default speed.
- Login code fails? Use the code shown on the page; codes rotate every 30 sec.
- Restart keeps live rows (they are stored in SQLite). Click **Reset demo
  state** to clear them.
- After a brute-force demo, click **Reset demo state** before showing ALLOW again.

## Verified before this runbook

- Normal login: ALLOW `0.0000` for all four users.
- Dormant + new device: BLOCK `0.6727 / 0.5074 / 0.6396 / 0.3824`, identical
  across two fresh processes.
- Replay: 9,954 events, 20 attacks, 20/20 caught, 31 blocked, 1 flagged, 12 FP.
- Dataset: 29,905,488 events, 604 users, 702 red, 8,162 src / 8,085 dst machines.
