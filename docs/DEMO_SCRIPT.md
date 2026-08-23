# DEMO SCRIPT — LANL SOC Live Demo

Everything needed to run and present the live demo. Read once, rehearse twice.

---

## 1. The 30-second pitch (memorize)

> "We studied account-takeover detection on two public datasets, found that
> the popular one has a labeling flaw that makes ML results misleading, and
> pivoted to the MITRE CERT dataset where attacks have real ground truth.
> Our final system combines an Isolation Forest with a per-user behavioral
> baseline, streams live auth events over HTTP, scores each event against
> that user's own habits in milliseconds, and displays detections on a
> real-time SOC dashboard."

## 2. Datasets (slide answer)

| | RBA (Zenodo 6782156) | LANL cyber1 (MITRE CERT) — *this demo* |
|---|---|---|
| Size | 31.3M logins, 4.3M users, 229 countries | 1.05B auth events total; 29.9M slice, 604 users |
| Labels | `is_attack_ip` = IP blocklist, not behavior | 702 red-team events = real attack behavior |
| Lesson | Weak labels → ML learns the blocklist (F1 0.747 rules vs 0.13 ML) | Honest labels → honest ML |

## 3. Models — what to claim, honestly

- **Detector: Isolation Forest** (unsupervised anomaly detection), ROC-AUC 0.879 on test split.
- **Second signal: per-user habit deviation** — first-ever machine outside their usual set,
  velocity above personal floor, repeated auth failures. Fused:
  `risk = if_score + 0.10 × min(habit_breaks, 3)`.
- **Thresholds are measured, not guessed**: FLAG ≥ 0.70, BLOCK ≥ 0.80, set from a recorded
  scenario sweep (`live/measure_scores.py`).
- LightGBM was trained (ROC-AUC 0.859) but is displayed only, not used: it saturates on
  small-history users. We report it as a finding.
- Honest limitation: holdout ranking ~0.57 — one attacker machine dominates the red-team
  data, so full generalization is unmeasurable. Said out loud, this is maturity.

## 4. How it works live (if asked "how do models work right now")

```
auth event (HTTP POST /events)
  → DuckDB pulls THIS user's history
  → 8 features computed (first-time dst/src? failures last hour? velocity? hour habits?)
  → IF scores anomaly; habit checks add points if this breaks THEIR normal
  → risk fused → ALLOW (<0.70) / FLAG (≥0.70) / BLOCK (≥0.80)
  → Server-Sent Events push verdict instantly to React dashboard
```

## 5. Run order

```bash
# Laptop 1 (demo machine)
make demo-reset          # stop any running backend FIRST (DuckDB lock)
make demo                # serves API on 0.0.0.0:5000 + dashboard at /dashboard
# open http://127.0.0.1:5000/dashboard   (big screen)
# open http://127.0.0.1:5000/            (login page — can also open from laptop 2)
```

```bash
# Laptop 2 (attacker/victim) — just a browser, nothing installed
open http://<laptop1-ip>:5000/
```

Find laptop 1's IP: `hostname -I | awk '{print $1}'`

## 6. Click-by-click story (~4 min)

| # | Action | Expected on dashboard |
|---|---|---|
| 1 | Alice logs in normally ×3 (from laptop 2 browser) | green ALLOW rows, no alerts; score ≈ 0.3–0.5 |
| 2 | Same login, wrong password ×3 | escalation → FLAG by third strike ("three strikes" habit rule) |
| 3 | Alice logs in from an unseen machine | **BLOCK**, Habit Breaks = 2, reasons shown in drawer |
| 4 | Open investigation drawer on the blocked event | Risk Score / Anomaly (IF) / Habit Breaks + which habits broke |
| 5 | Attacker burst (login page ATTACK persona or `generate.py`) | red alerts stream, Critical banner |
| 6 | KPIs: events/min, alert counts, per-user stats | talking point: "every verdict explains itself" |

Optional second tab: `generate.py --url http://<laptop1>:5000` replays real LANL traffic.

## 7. Numbers you can quote (measured 2026-08-23)

- Quiet logins: p50 IF score 0.35–0.38 → all ALLOW (zero false blocks)
- New machine: fused ≈ 0.84 → BLOCK ×10/10
- Wrong password: three-strikes → FLAG/BLOCK
- Failure bursts: FLAG→BLOCK escalation
- Attacker behaving quietly: correctly ALLOWed (no cry-wolf)

Full table: `lanl-anomaly/reports/score_measurements.json`.

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `make demo-reset` fails with IO/lock error | Stop the backend first: DuckDB allows ONE writer |
| Dashboard shows old labels | `cd lanl-anomaly/live/web && npm run build`, restart backend |
| Port 5000 busy | `pkill -f "lanl-anomaly/live/app.py"` then restart |
| Laptop 2 can't connect | Same Wi-Fi/LAN? `sudo ufw allow 5000/tcp` if firewall active |
| Scores look wrong after experiments | Re-run `make demo-reset` for a clean slate |

## 9. Emergency rollback

```bash
git reset --hard pre-demo-fix        # code back to pre-fix state
cd lanl-anomaly/live/web && npm run build
# stop backend → venv/bin/python lanl-anomaly/live/seed_demo.py → start backend
```
