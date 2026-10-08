#!/usr/bin/env python3
"""Smoke test for the LANL live demo.

Targets the endpoints that actually exist. The previous version of this file
asserted on a "models_loaded" key, requested "/dashboard", and POSTed to
"/events" -- none of which the application has ever served, so it failed on
its first assertion and never exercised anything.

Run with the Flask server up:
    cd lanl-anomaly && venv/bin/python3 test_live.py
"""
import json
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"


def get_json(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def post_json(path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def test_api():
    print("1. GET /api/health")
    d = get_json("/api/health")
    assert d["status"] == "ok", d
    assert d["scorer_ready"] is True, d
    print(f"   PASS {d}")

    print("2. GET /api/replay/status")
    d = get_json("/api/replay/status")
    assert d["meta"]["total"] == 9954, d["meta"]
    assert d["meta"]["attacks"] == 20, d["meta"]
    print(f"   PASS window={d['meta']['total']} attacks={d['meta']['attacks']}")

    print("3. GET /api/model/metrics")
    d = get_json("/api/model/metrics")
    assert d["feature_count"] == 21, d
    top = d["feature_importance"][0]
    # Importances must be real feature names, not positional placeholders.
    assert not top["feature"].startswith("Column_"), top
    assert set(d["feature_importance"][0]) == {"feature", "importance"}, d
    print(f"   PASS top feature={top['feature']} gain={top['importance']:.0f}")

    print("4. replay reset -> start -> status -> stop")
    post_json("/api/replay/reset", {})
    post_json("/api/replay/start", {"speed": 200})
    time.sleep(3)
    d = get_json("/api/replay/status")
    assert d["progress"]["emitted"] > 0, d
    assert len(d["events"]) == d["progress"]["emitted"], (
        f"status returned {len(d['events'])} events but emitted "
        f"{d['progress']['emitted']}")
    post_json("/api/replay/stop", {})
    print(f"   PASS emitted={d['progress']['emitted']} "
          f"status_events={len(d['events'])}")

    print("5. alerts and users read the replay window")
    alerts = get_json("/api/alerts")
    users = get_json("/api/users")
    assert isinstance(alerts, list), alerts
    assert isinstance(users, list), users
    for u in users:
        assert "attacks" in u and "false_positives" in u, u
    print(f"   PASS alerts={len(alerts)} users={len(users)}")

    print("6. simulated data is quarantined")
    sim = get_json("/api/simulation")
    assert "SIMULATED" in sim["disclaimer"], sim["disclaimer"]
    stats = get_json("/api/stats")
    assert "replay_events" in stats and "simulated_events" in stats, stats
    print(f"   PASS stats={stats}")


def test_browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        errors = []
        page.on("console", lambda m: errors.append(m.text)
                if m.type == "error" else None)

        print("7. dashboard renders replay controls")
        page.goto(f"{BASE}/", wait_until="networkidle")
        time.sleep(2)
        assert page.locator("#replay-tbody").count() == 1, "replay table missing"
        assert page.locator("#replay-play").count() == 1, "play button missing"
        page.screenshot(path="test_dashboard.png", full_page=True)
        print("   PASS saved test_dashboard.png")

        print("8. play streams events into the table")
        page.click("#replay-play")
        time.sleep(5)
        page.click("#replay-play")
        rows = page.locator("#replay-tbody tr").count()
        assert rows > 1, f"expected replay rows, got {rows}"
        page.screenshot(path="test_dashboard_after_events.png", full_page=True)
        print(f"   PASS {rows} rows, saved test_dashboard_after_events.png")

        print("9. every SPA page loads without console errors")
        for route in ["#/simulation", "#/alerts", "#/users", "#/behavior",
                      "#/model", "#/settings"]:
            page.goto(f"{BASE}/analyst{route}", wait_until="networkidle")
            time.sleep(1)
            assert page.locator("#main-content").count() == 1, \
                f"{route} rendered no content"
        page.goto(f"{BASE}/analyst/dataset", wait_until="networkidle")
        time.sleep(2)
        assert page.locator("canvas").count() > 0, "dataset page has no charts"

        assert not errors, f"console errors: {errors}"
        print("   PASS no console errors on any page")

        browser.close()


if __name__ == "__main__":
    test_api()
    test_browser()
    print("\nALL TESTS PASSED")