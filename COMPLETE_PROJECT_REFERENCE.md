# Complete Project Reference (plain-English edition)

*A short, beginner-friendly guide to the whole project. No ML jargon needed.*

---

## Team

| Member | USN |
|---|---|
| Hemanth Kumar KS | 1SK23CS020 |
| Urvashi Tanwar | 1SK23CS055 |
| Veenashree S T | 1SK23CS057 |
| Vishwanath Sanapur | 1SK23CS059 |

**Guide:** Dr. Anitha A C — Government Sri Krishnarajendra Silver Jubilee Technological Institute, CSE

---

## What this project is (one minute)

A **login bouncer**. Every time someone logs in, the system asks: *"Is this how this user normally behaves?"*

- Normal login (usual country, usual device, daytime) → **allowed**
- Strange login (new country, new device, 3 a.m., failed attempts just before) → **flagged or blocked**, with a written reason for *why*

The system was trained on the **RBA dataset** — 31.3 million real login events from a telecom company's SSO (published academic dataset, Telenor Norway). During the demo, logins from a second laptop are scored in real time and appear on a dashboard.

> **Dataset warning:** the RBA dataset is *synthesized* — statistically recreated from real login patterns, but the values are "totally artificial" per the authors. We use it only as an academic benchmark, never for production.

---

## The one discovery that shapes everything

The main "attack" label in the data (`is_attack_ip`) is **not about behavior at all**. It is an **IP blocklist** — a list of "bad" IP addresses. The same IP always gets the same label.

That means: **a model that studies behavior can never learn to predict a list.** We proved this with numbers:

- Just *looking up the IP* (no AI at all) scores **0.75**
- Our best behavior-based model scores **0.11**

That gap is the *label's* fault, not the model's. This is the most important thing to remember — it is our honest, defensible finding.

The **real** behavioral signal is *account takeover* (a hacked account) — but there are only **141** such events in 31 million rows. A needle in a haystack, too rare to train a model on.

---

## What we built

A reproducible pipeline, then a live demo.

```
raw data (31M logins)
  → clean it                          (~30 s)
  → compute 21 "features" per login   (~8 min)
  → pick a 1M-row sample              (~2 min)
  → check it (must print PASS)
  → rule engine: score + reasons      ← what the demo uses to decide
  → train 4 anomaly models on the full 1M sample  ← the honest comparison
```

**Features** are the questions we ask about each login, over the user's *own past*:
new country? new device? failed login just now? too many today? unusual hour?
never-seen IP / device / OS / browser? Each feature only uses *earlier* events —
no "future" information ever leaks in.

**Rule engine** = a bouncer's checklist. New country +30, new IP +25, recent failure
+20, and so on → a score 0–100 and a readable reason. This is what decides in the demo.

**4 anomaly models** = "learn what *normal* looks like, then flag the unusual."
Isolation Forest, Local Outlier Factor, One-Class SVM, Elliptic Envelope. All trained on
the **same full 1M-row sample** (no model gets special treatment).

---

## The results, in plain words

A few simple numbers — and what they mean.

| What we measured | Number | Plain meaning |
|---|---|---|
| IP lookup only (no ML) | **0.75** | The ceiling. The blocklist alone beats any behavior model |
| Best behavior model (ensemble) | **0.11** | Our best ML, honest and measured — far below the ceiling |
| Best single model (Local Outlier Factor) | **0.09** | Close to the ensemble |
| Rule engine "double-check" test | **79% of real takeovers caught** at a 10% double-check rate, 11% of normal users bothered | The rules are the practical winner |

**F1 explained simply:** one number (0 = useless, 1 = perfect) that balances "when we
flag something, are we right?" and "do we catch enough attacks?". Security people use it
because accuracy is meaningless here — the data is ~99.9% normal, so a model that flags
nothing would be "99.9% accurate" while catching zero attacks.

---

## Why the demo has no "ML score"

We also tried a **supervised** model (trained with the attack label as the answer key;
it reached 0.29 F1). But when we audited the demo, we found that score **never changed a
single decision** — the things the demo shows (new device, foreign login) moved it the
*wrong* way, and its trigger was never reached. Showing an ML meter that never moves
would have been misleading.

So we removed it. The demo is honestly **rule-driven**:

```
blocklist IP  → BLOCK (hard kill)
rule ≥ 90     → BLOCK
rule ≥ 45     → FLAG (extra verification)
otherwise     → ALLOW
```

The model comparison still exists in `reports/` as the honest research result.

---

## How to run everything

```bash
make all        # rebuild the whole pipeline (data → rules → models)
make demo       # seed the demo database and start the app
# open http://127.0.0.1:5000  (login form)  and  /dashboard  (live dashboard)
```

The demo has persona cards (alice, bob, carol = normal users; attacker = a fresh account
on a blocklisted IP). One-tap presets: **usual setup** → allowed · **new device** → flag ·
**foreign · night** → blocked · attacker burst → blocked.

---

## 5-minute demo script

| Time | What happens | What to say |
|---|---|---|
| 0:00 | Dashboard up | "Every login is compared to the user's own habits. Trained on 31.3M real login events." |
| 0:30 | Normal login | "Usual country, usual device, daytime. Score 0 — green, allowed." |
| 1:00 | New device | "Same user, new device. Score rises — we ask for extra verification, not a block." |
| 1:30 | Foreign + night | "Never-seen country, odd hour, new device. Score 100+ — blocked, with the reasons listed." |
| 2:00 | Attacker burst | "Rapid failed attempts from a blocklisted IP. Every one blocked." |
| 2:30 | Dashboard | "Watch the alerts appear live, with the exact reasons written out." |
| 3:00 | Honest numbers | "Behavior can't beat a blocklist: the IP lookup scores 0.75, our best ML 0.11. The rules catch ~79% of real account takeovers at a 10% double-check rate." |
| 3:30 | Q&A | See below. |

---

## Viva Q&A (short, defensible answers)

**Q1. Why rules AND models?**
Rules give transparent, explainable decisions — perfect for a demo where you watch the
score change. Models are the honest statistical comparison. Both run on the same features.

**Q2. Why these features?**
They cover identity: *who* (user history), *what* (device/OS/browser), *where*
(country/IP), *when* (hour/night), *how* (frequency, rapid attempts, recent failures).
All computable from the dataset and from a live login.

**Q3. Why not deep learning?**
Deep learning needs thousands of diverse attack examples. We have 141 confirmed
takeovers. Our models are interpretable — we can show exactly why something was flagged,
which matters more here.

**Q4. How is this different from a plain rule-based system?**
The rules are the baseline. The models add a learned "what is normal?" view — and we
measured both honestly (rules 79% takeover catch at 10% double-check; best ML 0.11 F1).

**Q5. Is the ML actually learning, or just memorizing your rules?**
Features use only the user's *earlier* events (no future info), and labels never enter
the features. Models are tested on events they never saw, under a 5% false-positive
budget.

**Q6. What can't you detect?**
Perfect mimic (stolen device + password), MFA bypass (login looks normal), and
post-login threats. Out of scope by design — documented.

**Q7. Travel → false positives?**
We alert, we don't block. The system remembers "seen before" and adapts the profile —
the Google/Microsoft approach.

**Q8. Which dataset and why?**
RBA (Telenor Norway, Wiefling et al., ACM TOPS 2022): 31.3M logins with country, device,
browser, OS, time, success/failure, attack labels. We checked LANL, CERT and Cloud-UEBA
as alternatives and rejected them — they lack the login columns and event-level attack
labels our pipeline needs. It's synthesized; we say so openly and treat it as a benchmark.

**Q9. Are your metrics real?**
Yes — every number in `reports/` is produced by running the scripts. Early drafts quoted
unmeasured 94% figures; we deleted them and re-measured honestly. Reproducibility is the
point of the pipeline (`make all` regenerates everything).

**Q10. Industry relevance?**
The design mirrors real systems (Microsoft Defender for Identity, Google BeyondCorp):
behavioral features, risk scoring, alerts, human confirmation. Simplified for BE scope.

**Q11. Could a real company use it?**
The detection core, yes. In production you'd add streaming (Kafka), a database, and SSO
integration to revoke sessions. Documented as future work.

**Q12. Hardest part?**
Building features across 31M rows with no future leakage, and handling the rare-attack
problem honestly — 141 takeovers in 31M rows, and a blocklist label behavior can't
predict. Solved with whole-user sampling, chronological splits, a contract validator, and
honest reporting.

**Q13. Who answers what?**

| Member | Expected to answer |
|---|---|
| **Hemanth** | Features: how "new country" / "seen before" are computed from the user's history; the no-cheating rule |
| **Urvashi** | Models & metrics: split, 5% FPR budget, why the ensemble (0.11) beats single models, the 0.75 blocklist ceiling |
| **Veenashree** | Dataset story: the scans, the messy findings, the cleaning decisions, the blocklist discovery |
| **Vishwanath** | Pipeline & demo: script order, contract validator, sampling (takeovers kept, bot capped), demo architecture |

---

## Honest limitations (say these out loud)

- The dataset is **synthesized** — a benchmark, not production data.
- **One dataset only.** LANL, CERT R4.2 and Cloud-UEBA were checked and rejected (no
  login columns, no event-level attack labels). This is a single-dataset study.
- **Behavior cannot predict a blocklist** — proven with numbers, not hidden.
- Only **141 confirmed account takeovers** exist in 31M rows — catching them is a
  rare-event problem, reported honestly.
- Perfect mimic, MFA bypass, and post-login threats are **out of scope** by design.