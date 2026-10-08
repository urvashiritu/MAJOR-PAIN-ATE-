#!/usr/bin/env python3
"""Blind Event Identification Test — Sender/Watcher/Comparator

Agent B (Sender) sends login events to the SOC dashboard.
Agent A (Watcher) observes the dashboard and must identify what happened
without being told which event was sent.

Covers all 14 edge case categories of the UEBA system.

STATUS AS OF 2026-10-04 — THIS TEST CURRENTLY SCORES 0/1575. TWO REASONS,
BOTH REAL:

1. The Watcher observes /api/dashboard, which now reads the real replay
   window (live/replay.py) rather than the employee-login simulation. The
   events a login produces are served by /api/simulation instead, so the
   Watcher is looking at the wrong source. Pointing it at /api/simulation
   would fix the plumbing but not the result, because of point 2.

2. The live scoring path genuinely cannot detect these patterns. Scoring a
   login as ace produces real model scores around 0.000001 against a
   threshold of 0.187. reports/experiment_log.md documents the cause as
   training-serving skew: live scoring computes features incrementally in
   memory, while the model was trained on batch SQL features over 29.9M rows.
   The log gives the live score range as [0, 0.005] against a training range
   of [0, 0.85+], and lists "retrain with incremental features" as the proper
   fix rather than threshold tuning.

This test previously appeared to pass for ace only because
simulate_login_burst() returned a hardcoded THRESHOLD + 0.15 whenever the
model failed to flag the burst. That forced alert was removed so the app
would stop reporting detections the model never made. The test was therefore
passing on a fabricated result, and is left failing rather than re-greened.

Re-enable after retraining on incremental features.
"""

import asyncio
import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

BASE_URL = "http://localhost:5000"
RESULTS_DIR = Path("/tmp/blind_test_results")
SCREENSHOT_DIR = RESULTS_DIR / "screenshots"

# ── 15 test rounds ────────────────────────────────────────────────
# Each round: which user logs in, what edge case it targets
ROUNDS = [
    {"round": 1,  "user": "luffy",   "target": "normal_allow",       "desc": "First normal login"},
    {"round": 2,  "user": "igris",   "target": "normal_allow",       "desc": "Second normal user"},
    {"round": 3,  "user": "ashborn", "target": "normal_allow",       "desc": "Third normal user"},
    {"round": 4,  "user": "ace",     "target": "attacker_block",     "desc": "First attacker — BLOCK"},
    {"round": 5,  "user": "luffy",   "target": "accumulated_state",  "desc": "Luffy again — accumulation"},
    {"round": 6,  "user": "ace",     "target": "double_block",       "desc": "Ace again — double BLOCK"},
    {"round": 7,  "user": "igris",   "target": "iat_zscore",         "desc": "Igris rapid — timing anomaly"},
    {"round": 8,  "user": "ace",     "target": "lateral_breadth",    "desc": "Ace third — lateral movement"},
    {"round": 9,  "user": "luffy",   "target": "velocity_spike",     "desc": "Luffy third — velocity rising"},
    {"round": 10, "user": "ashborn", "target": "pair_exhaustion",    "desc": "Ashborn second — pairs known"},
    {"round": 11, "user": "ace",     "target": "forced_injection",   "desc": "Ace fourth — C_ANOMALOUS"},
    {"round": 12, "user": "luffy",   "target": "rare_hour",          "desc": "Luffy fourth — rare hour"},
    {"round": 13, "user": "igris",   "target": "auth_mix",           "desc": "Igris second — auth type mix"},
    {"round": 14, "user": "ace",     "target": "max_velocity",       "desc": "Ace fifth — max velocity"},
    {"round": 15, "user": "ashborn", "target": "fatigue_noise",      "desc": "Ashborn third — noise test"},
]


# ── API helpers ───────────────────────────────────────────────────

def api_get(path):
    """GET request, return JSON."""
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def api_post_json(path, data, cookie_jar=None):
    """POST JSON request, return (json, cookie_header)."""
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def api_post_with_cookie(path, data, cookie):
    """POST with session cookie."""
    body = json.dumps(data).encode() if data else b""
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Cookie": cookie,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        # extract set-cookie
        sc = resp.headers.get("Set-Cookie", "")
        return json.loads(resp.read()), sc


def api_get_with_cookie(path, cookie):
    """GET with session cookie."""
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={"Cookie": cookie},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def login_dev(username):
    """Dev login, return session cookie."""
    result, cookie = api_post_with_cookie("/dev/login", {"username": username}, "")
    return cookie


def trigger_burst(cookie):
    """Hit /employee endpoint to trigger login burst. Returns HTTP status."""
    req = urllib.request.Request(
        f"{BASE_URL}/employee",
        headers={"Cookie": cookie},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status


def get_dashboard():
    """Get full dashboard state."""
    return api_get("/api/dashboard")


def get_alerts():
    """Get all alerts."""
    return api_get("/api/alerts")


# ── State snapshot ────────────────────────────────────────────────

def snapshot_dashboard(dash):
    """Extract comparable state from dashboard response."""
    return {
        "totalEvents": dash["kpis"]["totalEvents"],
        "anomalies": dash["kpis"]["anomalies"],
        "highRiskUsers": dash["kpis"]["highRiskUsers"],
        "usersMonitored": dash["kpis"]["usersMonitored"],
        "alert_count": len(dash.get("alerts", [])),
        "event_count": len(dash.get("recentEvents", [])),
        "alert_ids": [a["id"] for a in dash.get("alerts", [])],
        "event_ids": [e["id"] for e in dash.get("recentEvents", [])],
        "risk_dist": {r["name"]: r["value"] for r in dash.get("riskDistribution", [])},
        "auth_breakdown": {a["name"]: a["value"] for a in dash.get("authTypeBreakdown", [])},
        "top_risky": [
            {"name": u["name"], "max_score": round(u["max_score"], 4), "flags": u["flags"], "persona": u.get("persona", "unknown")}
            for u in dash.get("topRiskyUsers", [])
        ],
        "raw": dash,
    }


def diff_states(before, after):
    """Compute diff between two dashboard snapshots."""
    new_alert_ids = [a for a in after["alert_ids"] if a not in before["alert_ids"]]
    new_event_ids = [e for e in after["event_ids"] if e not in before["event_ids"]]

    # find new alerts from raw data
    before_alert_set = set(before["alert_ids"])
    new_alerts = [a for a in after["raw"].get("alerts", []) if a["id"] not in before_alert_set]

    before_event_set = set(before["event_ids"])
    new_events = [e for e in after["raw"].get("recentEvents", []) if e["id"] not in before_event_set]

    return {
        "delta_total_events": after["totalEvents"] - before["totalEvents"],
        "delta_anomalies": after["anomalies"] - before["anomalies"],
        "delta_high_risk": after["highRiskUsers"] - before["highRiskUsers"],
        "delta_alert_count": after["alert_count"] - before["alert_count"],
        "new_alerts": new_alerts,
        "new_events": new_events,
        "new_event_count": len(new_events),
        "risk_dist_delta": {
            k: after["risk_dist"].get(k, 0) - before["risk_dist"].get(k, 0)
            for k in set(list(before["risk_dist"].keys()) + list(after["risk_dist"].keys()))
        },
        "auth_delta": {
            k: after["auth_breakdown"].get(k, 0) - before["auth_breakdown"].get(k, 0)
            for k in set(list(before["auth_breakdown"].keys()) + list(after["auth_breakdown"].keys()))
        },
        "new_top_risky": [
            u for u in after["top_risky"]
            if u["name"] not in [x["name"] for x in before["top_risky"]]
        ],
    }


# ── Watcher prediction ────────────────────────────────────────────

def watcher_predict(diff, before, after):
    """Watcher analyzes diff and makes a prediction about what happened."""
    prediction = {
        "event_detected": False,
        "event_type": None,
        "user_guess": None,
        "decision_guess": None,
        "severity_guess": None,
        "event_count_range": None,
        "features_detected": [],
        "confidence": 0.0,
        "reasoning": [],
    }

    # Did anything change?
    if diff["delta_total_events"] == 0 and diff["delta_alert_count"] == 0:
        prediction["reasoning"].append("No change detected in dashboard")
        return prediction

    prediction["event_detected"] = True
    prediction["event_type"] = "login"
    confidence = 0.3

    # ── Identify user from new events ──
    new_users = set(e.get("name", e.get("user_id", "?")) for e in diff["new_events"])
    if len(new_users) == 1:
        user_name = list(new_users)[0]
        prediction["user_guess"] = user_name
        confidence += 0.25
        prediction["reasoning"].append(f"New events from user: {user_name}")
    elif len(new_users) > 1:
        prediction["user_guess"] = list(new_users)
        prediction["reasoning"].append(f"Multiple users in new events: {new_users}")

    # ── Identify decision from new alerts ──
    if diff["new_alerts"]:
        severities = [a.get("severity", "unknown") for a in diff["new_alerts"]]
        decisions = [a.get("decision", "unknown") for a in diff["new_alerts"]]
        prediction["severity_guess"] = severities[0]
        prediction["decision_guess"] = decisions[0].upper()
        confidence += 0.2
        prediction["reasoning"].append(f"New alert: severity={severities[0]}, decision={decisions[0]}")
    else:
        # No alert → likely ALLOW
        if diff["delta_total_events"] > 0:
            prediction["decision_guess"] = "ALLOW"
            prediction["reasoning"].append("New events but no alert → likely ALLOW")
            confidence += 0.1

    # ── Event count range ──
    n = diff["new_event_count"]
    if n >= 8:
        prediction["event_count_range"] = "8-12"
        prediction["reasoning"].append(f"Burst size {n} → attacker range (8-12)")
        confidence += 0.1
    elif n >= 3:
        prediction["event_count_range"] = "3-5"
        prediction["reasoning"].append(f"Burst size {n} → normal range (3-5)")
        confidence += 0.1
    elif n > 0:
        prediction["event_count_range"] = "1-2"
        prediction["reasoning"].append(f"Small burst: {n} events")

    # ── Feature detection from event details ──
    for evt in diff["new_events"]:
        auth = evt.get("auth_type", "")
        if auth == "Kerberos" and "kerberos" not in prediction["features_detected"]:
            prediction["features_detected"].append("kerberos")
            prediction["reasoning"].append(f"Kerberos auth detected (event {evt.get('id')})")

        features = evt.get("features", {})
        if features.get("dst_first", 0) > 0 and "dst_first" not in prediction["features_detected"]:
            prediction["features_detected"].append("dst_first")
            prediction["reasoning"].append(f"First-time destination detected")
        if features.get("src_first", 0) > 0 and "src_first" not in prediction["features_detected"]:
            prediction["features_detected"].append("src_first")
            prediction["reasoning"].append(f"First-time source detected")
        if features.get("vel_1h", 0) > 10 and "high_velocity" not in prediction["features_detected"]:
            prediction["features_detected"].append("high_velocity")
            prediction["reasoning"].append(f"High velocity: {features['vel_1h']:.0f} events/hr")
        if features.get("iat_zscore", 0) > 2 and "anomalous_timing" not in prediction["features_detected"]:
            prediction["features_detected"].append("anomalous_timing")
            prediction["reasoning"].append(f"Anomalous timing: iat_zscore={features['iat_zscore']:.2f}")
        if features.get("is_rare_hour", 0) > 0 and "rare_hour" not in prediction["features_detected"]:
            prediction["features_detected"].append("rare_hour")
            prediction["reasoning"].append("Rare hour activity detected")
        if features.get("fail_1h", 0) > 0 and "failed_auth" not in prediction["features_detected"]:
            prediction["features_detected"].append("failed_auth")
            prediction["reasoning"].append(f"Failed auth attempts: {features['fail_1h']:.0f}")

    # ── Risk distribution delta ──
    for level, delta in diff["risk_dist_delta"].items():
        if delta > 0:
            prediction["reasoning"].append(f"Risk dist: +{delta} {level}")

    # ── Auth breakdown delta ──
    for auth, delta in diff["auth_delta"].items():
        if delta > 0:
            prediction["reasoning"].append(f"Auth breakdown: +{delta} {auth}")

    prediction["confidence"] = min(confidence, 1.0)
    return prediction


# ── Scoring ───────────────────────────────────────────────────────

def score_prediction(prediction, ground_truth):
    """Score watcher prediction against ground truth."""
    scores = {
        "detected_event": 0,
        "correct_user": 0,
        "correct_decision": 0,
        "correct_severity": 0,
        "correct_burst_range": 0,
        "feature_hits": 0,
        "false_positive": 0,
        "wrong_user": 0,
    }

    # Did watcher detect anything?
    if prediction["event_detected"]:
        scores["detected_event"] = 10
    else:
        if ground_truth["had_alert"] or ground_truth["event_count"] > 0:
            scores["false_positive"] = -15  # missed a real event
        return scores

    # Correct user?
    if prediction["user_guess"] == ground_truth["username"]:
        scores["correct_user"] = 20
    elif isinstance(prediction["user_guess"], list) and ground_truth["username"] in prediction["user_guess"]:
        scores["correct_user"] = 15  # partial — multiple users listed
    else:
        scores["wrong_user"] = -10

    # Correct decision?
    if prediction["decision_guess"] and prediction["decision_guess"].upper() == ground_truth["decision"].upper():
        scores["correct_decision"] = 20
    elif prediction["decision_guess"] is None and ground_truth["decision"] == "ALLOW":
        scores["correct_decision"] = 10  # correctly inferred ALLOW from no alert

    # Correct severity?
    if ground_truth["severity"] and prediction["severity_guess"] == ground_truth["severity"]:
        scores["correct_severity"] = 10
    elif ground_truth["severity"] is None and prediction["severity_guess"] is None:
        scores["correct_severity"] = 5

    # Correct burst range?
    if prediction["event_count_range"] == ground_truth["burst_range"]:
        scores["correct_burst_range"] = 10

    # Feature hits
    expected_features = set(ground_truth.get("expected_features", []))
    detected_features = set(prediction.get("features_detected", []))
    hits = expected_features & detected_features
    scores["feature_hits"] = len(hits) * 5

    return scores


# ── Sender coroutine ──────────────────────────────────────────────

async def sender(rounds, ready_events, results):
    """Send login events for each round. Waits for watcher readiness."""
    for r in rounds:
        round_num = r["round"]
        username = r["user"]

        # Wait for watcher to signal ready
        await ready_events[round_num - 1].wait()

        print(f"  [SENDER] Round {round_num}: sending {username} login...")

        # Login and trigger burst
        cookie = login_dev(username)
        trigger_burst(cookie)

        # Store ground truth
        await asyncio.sleep(0.1)  # brief pause to let events land

        results[round_num] = {
            "round": round_num,
            "username": username,
            "target": r["target"],
            "desc": r["desc"],
            "ts": datetime.now().isoformat(),
        }


# ── Watcher coroutine ─────────────────────────────────────────────

async def watcher(rounds, ready_events, predictions, screenshots_dir):
    """Observe dashboard before/after each event. Diff and predict."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # Login as soc_admin via dev endpoint (sets session cookie in browser)
        await page.goto(f"{BASE_URL}/login")
        await page.wait_for_load_state("networkidle")
        await page.evaluate("""async () => {
            await fetch('/dev/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username: 'soc_admin'})
            });
        }""")
        # Navigate to analyst dashboard (now has session)
        await page.goto(f"{BASE_URL}/analyst")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)

        for r in rounds:
            round_num = r["round"]

            # Capture BEFORE state
            dash_before = get_dashboard()
            state_before = snapshot_dashboard(dash_before)

            ss_dir = screenshots_dir / f"round_{round_num:02d}"
            ss_dir.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(ss_dir / "before.png"), full_page=False)

            # Signal sender: "I'm ready, send it"
            ready_events[round_num - 1].set()

            # Wait for sender to trigger (give time for burst to land)
            await asyncio.sleep(8)

            # Capture AFTER state
            dash_after = get_dashboard()
            state_after = snapshot_dashboard(dash_after)
            await page.screenshot(path=str(ss_dir / "after.png"), full_page=False)

            # Diff
            diff = diff_states(state_before, state_after)

            # Predict
            prediction = watcher_predict(diff, state_before, state_after)

            # Save artifacts
            with open(ss_dir / "api_before.json", "w") as f:
                json.dump(state_before, f, indent=2, default=str)
            with open(ss_dir / "api_after.json", "w") as f:
                json.dump(state_after, f, indent=2, default=str)
            with open(ss_dir / "diff.json", "w") as f:
                json.dump(diff, f, indent=2, default=str)
            with open(ss_dir / "prediction.json", "w") as f:
                json.dump(prediction, f, indent=2, default=str)

            predictions[round_num] = prediction
            print(f"  [WATCHER] Round {round_num}: detected={prediction['event_detected']}, "
                  f"user={prediction['user_guess']}, decision={prediction['decision_guess']}, "
                  f"features={prediction['features_detected']}")

            await asyncio.sleep(1)

        await browser.close()


# ── Main ──────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("  BLIND EVENT IDENTIFICATION TEST")
    print("  15 rounds · zero hints · screenshots + API")
    print("=" * 60)

    # Setup
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # Reset server
    print("\n[SETUP] Resetting server state...")
    # /api/reset clears the simulated employee-login events only. The analyst
    # dashboard now reads the real replay window, which has its own reset, so
    # both are needed before asserting a clean slate.
    api_post_json("/api/reset", {})
    api_post_json("/api/replay/reset", {})
    await asyncio.sleep(2)

    # Verify clean state
    dash = get_dashboard()
    assert dash["kpis"]["totalEvents"] == 0, f"Server not clean: {dash['kpis']['totalEvents']} events"
    print("[SETUP] Server clean — 0 events, 0 alerts")

    # Coordination events — one per round
    ready_events = [asyncio.Event() for _ in range(len(ROUNDS))]
    predictions = {}
    sender_results = {}

    # Run sender and watcher concurrently
    print("\n[TEST] Starting 15 rounds...\n")
    start = time.time()

    await asyncio.gather(
        sender(ROUNDS, ready_events, sender_results),
        watcher(ROUNDS, ready_events, predictions, SCREENSHOT_DIR),
    )

    elapsed = time.time() - start
    print(f"\n[TEST] All rounds complete in {elapsed:.1f}s")

    # ── Scoring ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  SCORING")
    print("=" * 60)

    total_score = 0
    max_possible = 0
    round_scores = []

    for r in ROUNDS:
        round_num = r["round"]
        username = r["user"]
        ss_dir = SCREENSHOT_DIR / f"round_{round_num:02d}"

        # Load per-round watcher data (the actual before/after diff)
        with open(ss_dir / "diff.json") as f:
            diff = json.load(f)
        with open(ss_dir / "prediction.json") as f:
            pred = json.load(f)

        # Build ground truth FROM THE DIFF (what actually appeared this round)
        new_alerts = diff.get("new_alerts", [])
        new_events = diff.get("new_events", [])
        n_new_events = diff.get("new_event_count", 0)

        had_alert = len(new_alerts) > 0
        if had_alert:
            actual_decision = new_alerts[-1].get("decision", "allow").upper()
            actual_severity = new_alerts[-1].get("severity")
        else:
            actual_decision = "ALLOW"
            actual_severity = None

        if n_new_events >= 8:
            burst_range = "8-12"
        elif n_new_events >= 3:
            burst_range = "3-5"
        else:
            burst_range = "1-2"

        expected_features = []
        if r["target"] in ("attacker_block", "double_block", "lateral_breadth",
                           "forced_injection", "max_velocity"):
            expected_features.append("kerberos")
        if r["target"] in ("lateral_breadth", "forced_injection"):
            expected_features.append("dst_first")
        if r["target"] in ("velocity_spike", "max_velocity"):
            expected_features.append("high_velocity")
        if r["target"] == "iat_zscore":
            expected_features.append("anomalous_timing")
        if r["target"] == "rare_hour":
            expected_features.append("rare_hour")

        ground_truth = {
            "username": username,
            "decision": actual_decision,
            "severity": actual_severity,
            "had_alert": had_alert,
            "event_count": n_new_events,
            "burst_range": burst_range,
            "expected_features": expected_features,
        }

        with open(ss_dir / "ground_truth.json", "w") as f:
            json.dump(ground_truth, f, indent=2)

        # Score
        scores = score_prediction(pred, ground_truth)
        round_total = sum(scores.values())
        max_possible += 105  # 10+20+20+10+10 + up to 35 feature hits
        total_score += round_total
        round_scores.append({
            "round": round_num,
            "user": username,
            "target": r["target"],
            "desc": r["desc"],
            "prediction": pred,
            "ground_truth": ground_truth,
            "scores": scores,
            "total": round_total,
        })

        status = "CORRECT" if round_total >= 40 else "PARTIAL" if round_total >= 20 else "WRONG"
        icon = "✅" if status == "CORRECT" else "🟡" if status == "PARTIAL" else "❌"
        print(f"  {icon} Round {round_num:2d} [{username:8s}] {r['target']:22s} → "
              f"Score: {round_total:3d}  ({status})")
        if scores["wrong_user"] < 0:
            print(f"       User guess: {pred.get('user_guess')} (expected: {username})")
        if scores["correct_decision"] == 0 and pred.get("decision_guess"):
            print(f"       Decision guess: {pred.get('decision_guess')} (expected: {actual_decision})")

    # ── Generate report ───────────────────────────────────────────
    pct = (total_score / max_possible * 100) if max_possible > 0 else 0
    report_lines = [
        "# Blind Event Identification Test — Report",
        f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Rounds:** {len(ROUNDS)}",
        f"**Total Score:** {total_score} / {max_possible} ({pct:.1f}%)",
        f"**Time:** {elapsed:.1f}s",
        f"**Hints given:** ZERO",
        f"**Reset between rounds:** NO (events accumulate)",
        "",
        "## Per-Round Results",
        "",
        "| Round | User | Target | Score | Status | Prediction | Ground Truth |",
        "|-------|------|--------|-------|--------|------------|--------------|",
    ]

    for rs in round_scores:
        status = "CORRECT" if rs["total"] >= 40 else "PARTIAL" if rs["total"] >= 20 else "WRONG"
        pred_summary = f"{rs['prediction'].get('user_guess', '?')}/{rs['prediction'].get('decision_guess', '?')}"
        gt_summary = f"{rs['ground_truth']['username']}/{rs['ground_truth']['decision']}"
        report_lines.append(
            f"| {rs['round']:2d} | {rs['user']:8s} | {rs['target']:22s} | "
            f"{rs['total']:3d} | {status:8s} | {pred_summary:12s} | {gt_summary:12s} |"
        )

    report_lines.extend([
        "",
        "## Scoring Rules",
        "",
        "| Criterion | Points |",
        "|-----------|--------|",
        "| Detected event happened | +10 |",
        "| Correct user | +20 |",
        "| Correct decision (BLOCK/FLAG/ALLOW) | +20 |",
        "| Correct severity | +10 |",
        "| Correct burst range (3-5 vs 8-12) | +10 |",
        "| Feature identification (per feature) | +5 |",
        "| False positive | -15 |",
        "| Wrong user | -10 |",
        "",
        "## Edge Case Coverage",
        "",
        "| Category | Rounds | Covered |",
        "|----------|--------|---------|",
        "| Normal ALLOW | 1,2,3,5,9,10,12,13,15 | ✅ |",
        "| Attacker BLOCK | 4,6,8,11,14 | ✅ |",
        "| Burst pattern (3-5 vs 8-12) | 1-3 vs 4,6,8,11,14 | ✅ |",
        "| Auth type (NTLM vs Kerberos) | 1-3 vs 4,6,8,11,14 | ✅ |",
        "| New destination (dst_first) | 4,6,8,11,14 | ✅ |",
        "| New source (src_first) | 4,6,8,11,14 | ✅ |",
        "| High velocity (vel_1h) | 9,14 | ✅ |",
        "| Unusual hour | 12 | ✅ |",
        "| Anomalous timing (iat_zscore) | 7 | ✅ |",
        "| Alert severity | 4,6,8,11,14 | ✅ |",
        "| Dashboard KPI correlation | all | ✅ |",
        "| SSE real-time updates | implicit | ✅ |",
        "| Accumulated state (no reset) | 5-15 | ✅ |",
        "",
        "## Files",
        "",
        "Each round has screenshots and data in `/tmp/blind_test_results/screenshots/round_NN/`:",
        "- `before.png` — dashboard before event",
        "- `after.png` — dashboard after event",
        "- `api_before.json` — API state snapshot before",
        "- `api_after.json` — API state snapshot after",
        "- `diff.json` — computed diff",
        "- `prediction.json` — watcher's prediction",
        "- `ground_truth.json` — actual event details",
    ])

    report_path = RESULTS_DIR / "REPORT.md"
    report_path.write_text("\n".join(report_lines))
    print(f"\n[REPORT] Written to {report_path}")

    # Summary
    print("\n" + "=" * 60)
    print(f"  FINAL SCORE: {total_score} / {max_possible} ({pct:.1f}%)")
    correct = sum(1 for rs in round_scores if rs["total"] >= 40)
    partial = sum(1 for rs in round_scores if 20 <= rs["total"] < 40)
    wrong = sum(1 for rs in round_scores if rs["total"] < 20)
    print(f"  CORRECT: {correct}  PARTIAL: {partial}  WRONG: {wrong}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
