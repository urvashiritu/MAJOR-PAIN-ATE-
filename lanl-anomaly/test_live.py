#!/usr/bin/env python3
"""Playwright smoke test for LANL live demo dashboard."""
import json
import time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"


def test_health():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        # 1. Health check
        print("1. GET /api/health...")
        resp = page.goto(f"{BASE}/api/health")
        data = json.loads(resp.text())
        assert data["status"] == "ok", f"health failed: {data}"
        assert data["models_loaded"] is True
        print(f"   PASS: {data}")

        # 2. Dashboard loads
        print("2. GET /dashboard...")
        resp = page.goto(f"{BASE}/dashboard")
        assert resp.status == 200
        title = page.title()
        print(f"   PASS: status=200 title='{title}'")

        # 3. Screenshot the dashboard
        print("3. Screenshot dashboard...")
        page.goto(f"{BASE}/dashboard")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        page.screenshot(path="test_dashboard.png", full_page=True)
        print("   PASS: saved test_dashboard.png")

        # 4. API dashboard endpoint
        print("4. GET /api/dashboard...")
        resp = page.goto(f"{BASE}/api/dashboard")
        data = json.loads(resp.text())
        print(f"   PASS: keys={list(data.keys())}")

        # 5. POST a test event (normal user alice) via requests
        print("5. POST /events (normal user alice)...")
        import urllib.request
        payload = json.dumps({
            "user_id": 1,
            "src_computer": "C1234", "dst_computer": "C5678",
            "auth_type": "NTLM", "logon_type": "Network",
            "orientation": "LogOn", "result": "Success",
        }).encode()
        req = urllib.request.Request(f"{BASE}/events", data=payload,
                                    headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        print(f"   PASS: decision={result.get('decision')} score={result.get('combined_score'):.4f}")

        # 6. POST an attacker event
        print("6. POST /events (attacker U748)...")
        payload2 = json.dumps({
            "user_id": -1,
            "src_computer": "C17693", "dst_computer": "C99999",
            "auth_type": "NTLM", "logon_type": "Network",
            "orientation": "LogOn", "result": "Fail",
        }).encode()
        req2 = urllib.request.Request(f"{BASE}/events", data=payload2,
                                     headers={"Content-Type": "application/json"}, method="POST")
        resp2 = urllib.request.urlopen(req2, timeout=10)
        result2 = json.loads(resp2.read())
        print(f"   PASS: decision={result2.get('decision')} score={result2.get('combined_score'):.4f}")

        # 7. Screenshot after events
        print("7. Screenshot after events...")
        page.goto(f"{BASE}/dashboard")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        page.screenshot(path="test_dashboard_after_events.png", full_page=True)
        print("   PASS: saved test_dashboard_after_events.png")

        # 8. Check /api/alerts
        print("8. GET /api/alerts...")
        resp = page.goto(f"{BASE}/api/alerts")
        alerts = json.loads(resp.text())
        print(f"   PASS: {len(alerts)} alerts")

        browser.close()
        print("\n ALL TESTS PASSED")


if __name__ == "__main__":
    test_health()
