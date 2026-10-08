#!/usr/bin/env python3
"""
Full Playwright audit of LANL UEBA demo.
Tests every page/flow like a brand new user.
Produces numbered screenshots + text report.

Usage:
    cd lanl-anomaly/live
    python3 test_audit.py

Requirements:
    - Flask server running at localhost:5000
    - LANL_DEV=1 (for dev/login bypass)
    - playwright + chromium installed
"""

import os, sys, time, json, urllib.request, urllib.error
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5000"
OUT = Path(__file__).parent / "audit_screenshots"
OUT.mkdir(exist_ok=True)
report = []


def _post_json(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=10)
    return resp.status, json.loads(resp.read())


def log(msg, level="INFO"):
    line = f"[{level}] {msg}"
    print(line)
    report.append(line)


def screenshot(page, name, full_page=False):
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=full_page)
    log(f"Screenshot: {path.name}")


def check(condition, desc):
    status = "PASS" if condition else "FAIL"
    log(f"{status}: {desc}", status)
    return condition


# ── Phase 0: Server health ──────────────────────────────────────
log("=" * 60)
log("PHASE 0: Server Health")
log("=" * 60)

try:
    health = json.loads(urllib.request.urlopen(f"{BASE}/api/health", timeout=5).read())
    check(health.get("status") == "ok", "Server health check")
except Exception as e:
    log(f"FATAL: Server not running: {e}", "ERROR")
    sys.exit(1)

# ── Phase 1: Analyst Dashboard (auto-login) ────────────────────
log("\n" + "=" * 60)
log("PHASE 1: Analyst Dashboard (auto-login)")
log("=" * 60)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})

    # --- Step 1: Auto-login ---
    page = ctx.new_page()
    page.goto(f"{BASE}/", wait_until="networkidle")
    time.sleep(2)
    check("/analyst" in page.url, f"Auto-redirect to /analyst (got: {page.url})")
    screenshot(page, "01_dashboard_default")

    # --- Step 2: Check sidebar exists ---
    sidebar = page.query_selector(".sidebar")
    check(sidebar is not None, "Sidebar rendered")
    sidebar_text = sidebar.inner_text() if sidebar else ""
    check("Live Monitoring" in sidebar_text, "Sidebar has 'Live Monitoring'")
    check("Dataset Analysis" in sidebar_text, "Sidebar has 'Dataset Analysis'")
    check("Behavior Insights" in sidebar_text or "Behavior" in sidebar_text, "Sidebar has Behavior link")

    # --- Step 3: Check header ---
    header = page.query_selector(".topbar")
    check(header is not None, "Topbar rendered")

    # --- Step 4: Navigate to each SPA page ---
    spa_pages = [
        ("#/behavior", "02_behavior_empty", "Behavior Insights"),
        ("#/model", "03_model_performance", "Model Performance"),
        ("#/alerts", "04_alerts", "Alerts"),
        ("#/users", "05_users", "Users"),
        ("#/settings", "06_settings", "Settings"),
    ]

    for hash_route, img_name, title in spa_pages:
        page.goto(f"{BASE}/analyst{hash_route}", wait_until="networkidle")
        time.sleep(2)
        screenshot(page, img_name, full_page=True)
        content = page.content()
        check(title.lower().replace(" ", "") in content.lower().replace(" ", "") or
              title.split()[0].lower() in content.lower(),
              f"Page '{title}' rendered content")

    # ── Phase 2: Employee Login → Events → Dashboard ────────────
    log("\n" + "=" * 60)
    log("PHASE 2: Employee Login → Events → Dashboard")
    log("=" * 60)

    # Step 5: Login as ACE (attacker) via dev/login
    ace_status, ace_data = _post_json(f"{BASE}/dev/login", {"username": "ace"})
    check(ace_status == 200, f"Dev login as ace: {ace_status}")
    check(ace_data.get("ok"), f"ace login response ok: {ace_data}")
    check(ace_data.get("role") == "employee", f"ace role is employee: {ace_data.get('role')}")

    # Navigate employee page
    ace_page = ctx.new_page()
    ace_page.goto(f"{BASE}/employee", wait_until="networkidle")
    time.sleep(3)
    screenshot(ace_page, "07_ace_employee_result", full_page=True)

    # Check employee page shows decision
    emp_text = ace_page.content()
    has_decision = any(w in emp_text.upper() for w in ["BLOCK", "ALLOW", "FLAG", "GRANTED", "DENIED"])
    check(has_decision, "Employee page shows access decision")

    # Step 6: Back to analyst dashboard - events should appear via SSE
    page.goto(f"{BASE}/analyst#/dashboard", wait_until="networkidle")
    time.sleep(5)
    screenshot(page, "08_dashboard_after_ace", full_page=True)

    # Step 7: Login as LUFFY (normal)
    resp2_status, _ = _post_json(f"{BASE}/dev/login", {"username": "luffy"})
    check(resp2_status == 200, f"Dev login as luffy: {resp2_status}")

    luffy_page = ctx.new_page()
    luffy_page.goto(f"{BASE}/employee", wait_until="networkidle")
    time.sleep(3)
    screenshot(luffy_page, "09_luffy_employee_result", full_page=True)

    # Step 8: Login as IGRIS
    resp3_status, _ = _post_json(f"{BASE}/dev/login", {"username": "igris"})
    check(resp3_status == 200, f"Dev login as igris: {resp3_status}")

    igris_page = ctx.new_page()
    igris_page.goto(f"{BASE}/employee", wait_until="networkidle")
    time.sleep(3)
    screenshot(igris_page, "10_igris_employee_result", full_page=True)

    # Step 9: Login as ASHBORN
    resp4_status, _ = _post_json(f"{BASE}/dev/login", {"username": "ashborn"})
    check(resp4_status == 200, f"Dev login as ashborn: {resp4_status}")

    ash_page = ctx.new_page()
    ash_page.goto(f"{BASE}/employee", wait_until="networkidle")
    time.sleep(3)
    screenshot(ash_page, "11_ashborn_employee_result", full_page=True)

    # Step 10: Dashboard with all users' events
    page.goto(f"{BASE}/analyst#/dashboard", wait_until="networkidle")
    time.sleep(5)
    screenshot(page, "12_dashboard_all_users", full_page=True)

    # Check KPIs populated
    kpi_text = page.inner_text("body")
    check("U66" in kpi_text or "Ace" in kpi_text or "Igris" in kpi_text or
          "Luffy" in kpi_text or "events" in kpi_text.lower(),
          "Dashboard shows user names or event data after logins")

    # ── Phase 3: SPA Pages with Data ───────────────────────────
    log("\n" + "=" * 60)
    log("PHASE 3: SPA Pages with Live Data")
    log("=" * 60)

    for hash_route, img_name, title in [
        ("#/behavior", "13_behavior_with_data", "Behavior Insights"),
        ("#/alerts", "14_alerts_with_data", "Alerts"),
        ("#/users", "15_users_with_data", "Users"),
        ("#/model", "16_model_performance", "Model Performance"),
        ("#/settings", "17_settings", "Settings"),
    ]:
        page.goto(f"{BASE}/analyst{hash_route}", wait_until="networkidle")
        time.sleep(2)
        screenshot(page, img_name, full_page=True)

    # Check behavior page has user names and badges.
    # Use text_content, not inner_text: .section-title sets
    # text-transform: uppercase, so inner_text returns "ACE" and a
    # case-sensitive "Ace" check fails against a page that renders correctly.
    page.goto(f"{BASE}/analyst#/behavior", wait_until="networkidle")
    time.sleep(2)
    behavior_text = page.inner_text("body")
    behavior_raw = page.text_content("body") or ""
    check("Ace" in behavior_raw, "Behavior page shows 'Ace'")
    check("ATTACKER" in behavior_text, "Behavior page shows ATTACKER badge")
    check("Igris" in behavior_raw, "Behavior page shows 'Igris'")
    check("NORMAL" in behavior_text, "Behavior page shows NORMAL badge")
    # The page mixes a training baseline with live replay counts; both must be
    # labelled or a reader cannot tell which number came from where.
    check("Training baseline" in behavior_text,
          "Behavior page labels the training baseline")
    check("Replay window" in behavior_text,
          "Behavior page labels the replay window")

    # ── Phase 4: Dataset Page ───────────────────────────────────
    log("\n" + "=" * 60)
    log("PHASE 4: Dataset Analysis Page")
    log("=" * 60)

    page.goto(f"{BASE}/analyst/dataset", wait_until="networkidle")
    time.sleep(4)
    screenshot(page, "18_dataset_top", full_page=False)
    screenshot(page, "19_dataset_full", full_page=True)

    # Scroll to specific sections
    for section_id, img_name in [
        ("chart-timeline", "20_dataset_timeline"),
        ("chart-distribution", "21_dataset_score_dist"),
        ("chart-attackers", "22_dataset_top_attackers"),
        ("chart-network", "23_dataset_network"),
        ("chart-heatmap", "24_dataset_heatmap"),
    ]:
        el = page.query_selector(f"#{section_id}")
        if el:
            el.scroll_into_view_if_needed()
            time.sleep(1)
            screenshot(page, img_name)
        else:
            log(f"Section #{section_id} not found", "WARN")

    # Check dataset KPIs
    dataset_text = page.inner_text("body")
    check("29.9M" in dataset_text or "29.9" in dataset_text, "Dataset shows total events KPI")
    check("590" in dataset_text or "Threats" in dataset_text or "detections" in dataset_text.lower(),
          "Dataset shows threats detected KPI")

    # ── Phase 5: Search Overlay ─────────────────────────────────
    log("\n" + "=" * 60)
    log("PHASE 5: Search Overlay")
    log("=" * 60)

    page.goto(f"{BASE}/analyst#/dashboard", wait_until="networkidle")
    time.sleep(2)

    # Ctrl+K to open search
    page.keyboard.press("Control+k")
    time.sleep(1)
    screenshot(page, "25_search_overlay_open")

    search_overlay = page.query_selector(".search-overlay.open")
    check(search_overlay is not None, "Search overlay opens on Ctrl+K")

    # Type a search query
    search_input = page.query_selector("#search-modal-input")
    if search_input:
        search_input.fill("ace")
        time.sleep(1)
        screenshot(page, "26_search_results_ace")
        search_text = page.inner_text("body")
        check("ace" in search_text.lower() or "U293" in search_text, "Search results show ace")
    else:
        log("Search input not found", "WARN")

    # Escape to close
    page.keyboard.press("Escape")
    time.sleep(0.5)
    search_closed = page.query_selector(".search-overlay.open")
    check(search_closed is None, "Search overlay closes on Escape")

    # ── Phase 6: Logout → Login Form ────────────────────────────
    log("\n" + "=" * 60)
    log("PHASE 6: Logout → Login Form")
    log("=" * 60)

    page.goto(f"{BASE}/logout", wait_until="networkidle")
    time.sleep(1)
    check("/login" in page.url, f"Logout redirects to /login (got: {page.url})")
    screenshot(page, "27_login_page")

    # Check login form exists
    login_form = page.query_selector("form")
    check(login_form is not None, "Login form rendered")
    username_input = page.query_selector("input[name='username']")
    password_input = page.query_selector("input[name='password']")
    totp_input = page.query_selector("input[name='totp']")
    check(username_input is not None, "Username input exists")
    check(password_input is not None, "Password input exists")
    check(totp_input is not None, "TOTP input exists")

    # Try logging in as luffy
    if username_input and password_input and totp_input:
        username_input.fill("luffy")
        password_input.fill("mugiwara")
        totp_input.fill("000000")
        page.query_selector("form").evaluate("el => el.submit()")
        time.sleep(2)
        screenshot(page, "28_after_luffy_login")
        # May succeed (dev mode ignores TOTP) or fail
        log(f"After luffy login, URL: {page.url}")

    browser.close()

# ── Summary ─────────────────────────────────────────────────────
log("\n" + "=" * 60)
log("AUDIT COMPLETE")
log("=" * 60)
log(f"Screenshots saved to: {OUT}")
log(f"Total screenshots: {len(list(OUT.glob('*.png')))}")

passes = sum(1 for l in report if l.startswith("[PASS]"))
fails = sum(1 for l in report if l.startswith("[FAIL]"))
warns = sum(1 for l in report if l.startswith("[WARN]"))
log(f"Results: {passes} PASS, {fails} FAIL, {warns} WARN")

# Write report
report_path = OUT / "audit_report.txt"
report_path.write_text("\n".join(report))
log(f"Report saved to: {report_path}")
