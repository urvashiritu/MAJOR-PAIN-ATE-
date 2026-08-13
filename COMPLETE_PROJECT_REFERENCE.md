# Complete Project Reference (plain-English edition)

**This replaces the old 96 KB design reference.** Every number here is measured and
reproducible from the repo. The old version survives in git history if you ever need it.

---

## Team

| Member | USN |
|---|---|
| Hemanth Kumar KS | 1SK23CS020 |
| Urvashi Tanwar | 1SK23CS055 |
| Veenashree S T | 1SK23CS057 |
| Vishwanath Sanapur | 1SK23CS059 |

**Guide:** Dr. Anitha A C — Government Sri Krishnarajendra Silver Jubilee Technological
Institute, CSE

---

## Status (Aug 11, 2026)

- Phases 0–6 done, every gate PASS, honest numbers in `reports/`.
- Phase 6+ extension done: supervised models on the gold label (gold F1 0.110 → **0.287**).
- Next: Phase 7 (user-profile + risk API), Phase 8 (website + dashboard), Phase 9 (live demo).

---

## The system in one minute

A **login bouncer**:

1. Every login event is compared against the user's *own* history (country, device,
   time of day, frequency, recent failures).
2. Two scorers run: the **rules** (explainable checklist) and the **models** (statistical).
3. The dashboard shows green (safe) / yellow (medium) / red (critical) — **with the
   reasons written out**.
4. The demo streams live logins from a second laptop.

The system was trained on the **RBA dataset** (Telenor Norway, Wiefling et al., ACM TOPS
2022): 31.3M login events, 4.3M users, 13 months.

> **Dataset warning:** RBA is *synthesized* — statistically reconstructed, "totally
> artificial" per the authors. Benchmark/demo use only, never production.

---

## The pipeline (order matters)

```
raw CSV (31.3M)
  → 00_clean_dataset.py        clean + flags          (~30 s)
  → 02_feature_engineering.py  21 features full pass  (~8 min)   ← before sampling, on purpose
  → 01_load_and_sample.py      1M-row sample          (~2 min)
  → 03_validate_contract.py    must print PASS        (seconds)
  → 04_rule_baseline.py        rule scores + reasons  (~1 min)
  → 05_models_evaluation.py    anomaly models, eval   (~3 min)
  → 06_supervised_model.py     supervised models      (~1 min)
```

**Why features before sampling?** A sampled event must carry the exact feature the live
system would compute (from the user's *full* history). Sampling first would corrupt the
history features — we found this the hard way with the bot user.

---

## The 6 phases (what each one did)

| Phase | Plain-language summary |
|---|---|
| 0–2 | Scope + dataset audit. Scanned all 31.3M rows; found the messiness (bots, impossible versions, contradictions) and the big discovery: the main label is a **blocklist** |
| 3 | Cleaning + sampling. Fixed values, kept every row, added flags. Sampled 1M rows keeping ALL 141 takeover rows, capping the 45%-of-everything bot user at 50K |
| 4 | Features. 21 per event: new country? new device? failed login ≤5 min ago? rapid burst ≤60 s? many today? unusual hour? seen-this-value-before (IP/country/ASN/device/OS/browser)? — all computed from strictly-earlier events only |
| 5 | Rules. New country +30, new IP +25, recent failure +20, rapid +15, night +15, new ASN +15, new device +10, frequency +10, new OS +7, new browser +7 → low <30 / medium 30–64 / high 65–89 / critical ≥90 |
| 6 | 4 anomaly models (learn "normal", flag the rest), compared honestly under a 5% FPR budget. Best: Local Outlier Factor, gold F1 0.110 |
| 6+ | Supervised models trained WITH the gold label as answer key. Best: HistGradientBoosting, gold F1 **0.287** (2.6×), ROC-AUC 0.752 |

---

## Labels — the thing to understand before anything else

| Label | What it really is | Verdict |
|---|---|---|
| `is_attack_ip` | An **IP blacklist** — the same IP always has the same value (sample: 229,326 IPs, 12,583 always-attack, 0 mixed) | A lookup table, not a behavior label |
| gold = `is_attack_ip` AND `login_success` | Successful login from a blocked IP (153,352 rows in sample) | Our tuning/evaluation target |
| `is_ato` | Confirmed account takeover (141 rows, 138 users) | The behavioral gold standard, too rare to train on |

**Consequence:** behavior models can never beat a blocklist lookup. Measured: the IP
prior (zero ML) scores 0.747 gold F1; the best Phase 6 behavior model scored 0.110. The
gap is the label's fault, not the models'. Supervised learning on the gold label raised
the behavioral score to 0.287 — a 2.6× improvement, with the blocklist ceiling still
standing.

**Why we keep (don't delete) private-IP attack rows:** an attacker on a stolen company
laptop IS behind a private 10.x IP — deleting those 506K rows would erase a real attack
scenario. We flag them (`is_private_ip`, `geo_unreliable`) and let the model decide.

---

## Metrics in plain words (defend these)

| Metric | Meaning | Our number |
|---|---|---|
| Precision | Of everything we flagged, how much was really attack | HGB 0.436 |
| Recall | Of all real attacks, how many we caught | HGB 0.214 |
| F1 | Balanced single number (0–1) | HGB 0.287, LOF 0.110, IP prior 0.747 |
| FPR | Normal events wrongly flagged (the cost of annoying legit users) | 5.0% budget, respected |
| ROC-AUC | Ranking quality (0.5 = random, 1 = perfect) | HGB 0.752, LOF 0.560 |
| Recall@k / replay | "If we double-check the top X% most suspicious, how many attacks do we catch?" | Rules @10%: 79% of ATOs, 11% of legit re-checked |

**Why not accuracy?** The data is ~99.9% normal. A model that flags nothing is 99.9%
"accurate" while catching zero attacks. That's why security uses F1/FPR/recall.

**Rules vs models:** the rules are the demo workhorse (deterministic, explainable, 79%
ATO at 10% challenge). The models are the comparison — and Phase 6+ honestly documents
that supervised learning improves behavioral detection 2.6×.

---

## Sampling design (the parts to remember)

- 1,000,003 rows, 192,649 users, natural attack share 24.76% (not forced).
- Tiers: ATO users (all 141 rows), heavy-attack users, light users, normal users, bot
  capped at 50,000. No non-robot user exceeds 10,000 rows.
- Deterministic (hash-based, seeded) — reproducible.
- Labels are read for *stratification only*; features never touch them.

---

## What's next (Phases 7–11)

**Phase 7 — risk API:** per-user profile (known devices, usual countries/hours, daily
counts, failure history) + `POST /login`, `POST /events`, `GET /risk/{event_id}`,
`GET /users/{user_id}/profile`, `GET /alerts`, `WS /dashboard`. Flow: receive event →
live features → load profile → rules + model → allow/challenge/block → dashboard →
update profile (only after accepted normal events). Fake accounts, no real passwords.

**Phase 8 — website + dashboard:** login/verification/blocked pages; live feed with
scores, reasons, user profile, alerts, allow/challenge/block totals.

**Phase 9 — demo:** Laptop 1 dashboard, Laptop 2 website. The key demo message: *the
score changes because specific behavioral evidence changed* — not just red/green.

**Phase 10 — tests** (data/feature/model/app). **Phase 11 — report** with only measured
numbers.

---

## Live demo script (5-minute plan)

**Setup:** Laptop 1 runs server + dashboard; Laptop 2 runs the client; same WiFi;
dashboard on projector; client terminal visible (mode toggle: normal / attack). If the
network fails: dashboard has a "Simulate Events" replay button — demo continues.

| Time | What happens | What to say |
|---|---|---|
| 0:00 | Start; dashboard "SYSTEM READY" | "We monitor login events in real time, trained on 31.3M events from a real enterprise SSO." |
| 0:30 | Laptop 2 sends normal logins | "Normal: India, Chrome, daytime. Score 5/100, green, all features normal." |
| 1:00 | Night login (normal user, odd hour) | "Score rises slightly — but country and device match, so still low. No overreaction to a single change." |
| 1:30 | **ATTACK MODE** — Russia, 3am, Android | "Never-seen country, device, hour, rapid attempts. Red alert ~90+. Reasons listed." |
| 2:00 | Expand the alert | "country_change, device_change, night, failed_recently, rapid_rate — each reason is visible and human-readable." |
| 2:30 | "This was me" | "Traveling user? One click adds Russia to known. Future events there won't re-alert. Alert, don't block." |
| 3:00 | Normal again | "Score drops. The system adapts — that's false-positive handling in action." |
| 3:15 | Same-laptop attack (stolen device) | "Device matches but behavior is wrong — features still fire. Combined score rises." |
| 3:30 | Honest numbers | "We report honestly: the rules catch ~79% of real takeovers at a 10% challenge rate; supervised models improved behavioral F1 2.6×. We don't claim unmeasured accuracy." |
| 3:45 | Limitations slide | "Perfect mimic, MFA bypass, post-login threats — out of scope by design; documented." |
| 4:00 | Q&A | See below. |

---

## Viva Q&A (answers you can actually defend)

**Q1: Why did you use rules AND models?**
Rules give explainable decisions with written reasons — perfect for a demo where the
examiner watches the score change. Models are the statistical comparison. Phase 6 showed
behavior models can't beat a blocklist; the rules catch the takeover tail (~79% at 10%
challenge) and the supervised model improves behavioral F1 2.6×. Each layer has a job.

**Q2: Why these features?**
They cover the dimensions of identity: who (user history), what (device/OS/browser),
where (country/IP/ASN), when (hour, night, weekend), how (frequency, rapid rate, recent
failures). All computable from the RBA columns and from a live login event — one shared
feature function for both.

**Q3: Why not deep learning?**
Deep learning needs thousands of diverse attack samples; we have 141 confirmed ATOs and
a blocklist label. Our models are interpretable — we can show exactly why a row was
flagged. Explainability matters more than a marginal accuracy gain for this project.

**Q4: How is this different from a rule-based system?**
The rules are our baseline, and the models learn interactions from data (e.g. *new
country + night + failures* is worse than *new country + daytime*). Phase 6 measured
both honestly; Phase 6+ showed supervised models beat anomaly models 2.6×.

**Q5: Is your ML actually learning, or memorizing your rules?**
Features are computed only from strictly-earlier events (no future info). Labels are
never features. The supervised model trains on the gold label and is evaluated on events
it never saw, under a 5% FPR budget. The IP list itself never enters the model — only
behavioral "has this user seen this before" signals.

**Q6: What can't you detect?**
1) Perfect mimic (stolen device + password + exact behavior) — needs MFA. 2) MFA bypass —
the login looks normal. 3) Post-login threats — we monitor logins only. Production
systems add endpoint agents and continuous verification.

**Q7: Travel → false positives?**
Handled by "seen before" memory, profile adaptation, and a "This was me" button. We
alert, we don't block — the Google/Microsoft approach.

**Q8: Which dataset and why?**
RBA (Telenor Norway, Wiefling et al., ACM TOPS 2022): 31.3M logins with country, device,
browser, OS, timestamp, success/failure, attack labels. LANL and CERT lack these columns,
so we did not add a second dataset: auth events with no country/device/IP/success cannot
run through our shared feature/rule SQL, and none of them provides event-level attack
ground truth (CERT is user+day scenarios, Cloud-UEBA is unlabeled by design). It's
synthesized — we say so in the report and treat it as a benchmark.

**Q9: Are your metrics real?**
Yes — every number in `reports/` is produced by running the scripts. Early drafts quoted
unmeasured 94% figures; we deleted them and re-measured honestly (real F1s: 0.110 → 0.287
supervised). Reproducibility is the point of the pipeline.

**Q10: Industry relevance?**
The architecture mirrors production UEBA systems (Microsoft Defender for Identity, Google
BeyondCorp, Cloudflare): behavioral features, risk scoring, alert-based response,
human-in-the-loop confirmation. Simplified for BE scope.

**Q11: Deployable in a real company?**
The detection core is. At scale you'd add streaming (Kafka), a database, SSO integration
to revoke sessions, and broader telemetry. Documented as future work.

**Q12: Hardest part?**
Feature engineering across 31.3M rows without future leakage (features must use only
earlier events), and handling the rare-attack problem honestly — 141 ATOs in 31M rows,
and a blocklist label that behavior can't predict. We solved it with whole-user sampling,
chronological splits, the contract validator, and honest reporting.

**Q13: Individual contributions (who answers what)**

| Member | Expected to answer |
|---|---|
| **Hemanth** | Feature engineering logic with user history; how `country_change` / seen-before features are computed; the no-leakage rule |
| **Urvashi** | Models and metrics: train/test split, FPR budget, threshold tuning, why supervised beat anomaly models, the 0.747 blocklist ceiling |
| **Veenashree** | Dataset audit story: the 5 scans, the messiness findings, cleaning decisions, the blocklist discovery |
| **Vishwanath** | Pipeline + demo: script order, contract validator, sampling tiers (ATO kept, bot capped), demo architecture |

---

## Honest limitations (say these out loud)

- The dataset is synthesized — a benchmark, not production data.
- One dataset only. We evaluated LANL, CERT R4.2 and Cloud-UEBA as a second dataset and
  rejected all three: they lack the login columns (country/device/IP/browser, success/
  failure) our shared feature and rule SQL requires, and none provides event-level attack
  ground truth. This is a single-dataset study; transfer to other login telemetry is
  future work, not a claim.
- Behavior cannot predict a blocklist — proven, not hidden.
- The gold label and ATO are different populations: supervised models catch gold events
  (0.287 F1) but not ATOs; the rules catch the ATO tail (~79% @ 10% challenge).
- Test users also appear in training (later events) — consistent across all models;
  we do not claim new-user generalization.
- Perfect mimic, MFA bypass, and post-login threats are out of scope by design.
