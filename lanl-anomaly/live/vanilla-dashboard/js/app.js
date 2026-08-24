import { getDashboard, getAlerts, getUsers, getStats, getInvestigation, ackAlert, resetDashboard, connectSSE } from "./api.js";
import { severityBadge, kpiCard, eventRow, alertRow, userRow, holdButton, investigationDrawer } from "./components.js";
import { renderSparkline, renderGauge, renderAreaChart, renderDonut, renderHeatmap, renderThreatRings, renderTopOffenders, destroyCharts as destroyChartInstances } from "./charts.js";
import { esc } from "./utils.js";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let _poll = null;
let _gauge = null;
let _currentPage = null;

// ── Router ────────────────────────────────────────────────────
function getPage() {
  const hash = location.hash || "#/";
  if (hash.startsWith("#/alerts")) return "alerts";
  if (hash.startsWith("#/users")) return "users";
  if (hash.startsWith("#/settings")) return "settings";
  return "dashboard";
}

function navigate(page) {
  _currentPage = page;
  location.hash = `#/${page === "dashboard" ? "" : page}`;
  render();
  updateNav();
}

function updateNav() {
  $$(".sidebar-item").forEach(el => {
    el.classList.toggle("active", el.dataset.page === _currentPage);
  });
}

// ── Render ────────────────────────────────────────────────────
async function render() {
  const main = $("#main-content");
  destroyChartInstances();
  main.innerHTML = `<div class="loading"><span class="live-dot"></span><span class="text-faint text-xs ml-2">Loading...</span></div>`;

  try {
    switch (_currentPage) {
      case "dashboard": await renderDashboard(main); break;
      case "alerts":    await renderAlerts(main); break;
      case "users":     await renderUsers(main); break;
      case "settings":  await renderSettings(main); break;
    }
  } catch (err) {
    main.innerHTML = `<div class="text-critical p-4">Error: ${err.message}</div>`;
  }
}

// ── Dashboard Page ────────────────────────────────────────────
async function renderDashboard(main) {
  const data = await getDashboard();
  const kpis = data.kpis || {};
  const events = data.recentEvents || [];
  const alerts = data.alerts || [];
  const riskDist = data.riskDistribution || [];

  main.innerHTML = `
    <div class="grid-4 gap-4 mb-4" id="kpi-grid"></div>
    <div id="banner-container" class="mb-4"></div>
    <div class="grid-12 gap-4 mb-4">
      <div class="col-7"><div class="panel p-4 h-full" id="alert-feed"><div class="flex-between mb-3"><span class="section-title">Recent Alerts</span><span class="flex-center gap-1 text-10 text-faint uppercase tracking-widest"><span class="live-dot"></span>live</span></div><div class="space-y-2 max-h-300 overflow-y" id="alert-list"></div></div></div>
      <div class="col-5"><div class="panel p-4 h-full flex-center" id="gauge-container"></div></div>
    </div>
    <div class="grid-12 gap-4 mb-4">
      <div class="col-8 panel p-4" id="score-trend"><div class="section-title">Anomaly Score Trend</div><div style="height:200px" id="score-chart"></div></div>
      <div class="col-4 panel p-4" id="risk-split"><div class="section-title">Risk Split</div><div style="height:150px" id="risk-donut"></div></div>
    </div>
    <div class="panel overflow-hidden" id="event-table-container">
      <div class="flex-between px-4 py-3 hairline"><span class="section-title">Scored Events</span><span class="text-10 text-faint uppercase tracking-widest">top 10 of ${events.length}</span></div>
      <div class="overflow-auto" style="max-height:260px"><table class="table-glass"><thead><tr>
        <th>User</th><th>Source</th><th>Dest</th><th>Auth</th><th>Result</th><th>Score</th><th>Decision</th><th>Time</th>
      </tr></thead><tbody id="event-tbody"></tbody></table></div>
    </div>`;

  // KPI cards
  const kpiConfigs = [
    { key: "totalEvents", label: "Events Scored", icon: "⚡", color: "#6ea8e8" },
    { key: "anomalies", label: "Anomalies", icon: "🛡", color: "#e5484d" },
    { key: "highRiskUsers", label: "High-Risk Users", icon: "⚠", color: "#ff9b9e" },
    { key: "usersMonitored", label: "Users Monitored", icon: "👥", color: "#57b06c" },
  ];
  const kpiGrid = $("#kpi-grid");
  kpiConfigs.forEach(cfg => {
    const card = kpiCard(cfg, kpis[cfg.key] || 0);
    kpiGrid.appendChild(card);
    const sparkEl = card.querySelector(`#spark-${cfg.key}`);
    if (sparkEl) {
      const sparkData = events.slice(-20).map((_, i) => {
        if (cfg.key === "totalEvents") return { value: i + 1 };
        const upto = events.slice(0, i + 1);
        if (cfg.key === "anomalies") return { value: upto.filter(x => x.decision === "flag" || x.decision === "block").length };
        if (cfg.key === "highRiskUsers") return { value: new Set(upto.filter(x => x.decision === "flag" || x.decision === "block").map(x => x.user_id)).size };
        return { value: new Set(upto.map(x => x.user_id)).size };
      });
      renderSparkline(sparkEl, sparkData, cfg.color);
    }
  });

  // High risk banner
  const bannerAlert = alerts.find(a => a.severity === "critical" || a.severity === "high");
  if (bannerAlert) {
    const bc = $("#banner-container");
    const isCritical = bannerAlert.severity === "critical";
    bc.innerHTML = `<div class="panel p-3 banner" style="border-left:3px solid ${isCritical ? "#e5484d" : "#ff9b9e"}">
      <div class="flex-center gap-4">
        <div class="banner-icon" style="border-color:${isCritical ? "#e5484d66" : "#ff9b9e80"};color:${isCritical ? "#e5484d" : "#ff9b9e"}">⚠</div>
        <div class="flex-1 min-w-0">
          <div class="flex-center gap-2 mb-1"><span class="stamp ${isCritical ? "stamp-critical" : "stamp-high"} badge-pulse">${isCritical ? "VERDICT: CRITICAL" : "VERDICT: HIGH"}</span><span class="text-sm font-semibold text-ink tracking-wide">Live Attack Activity</span></div>
          <p class="text-sm text-dim truncate mono"><span class="font-bold" style="color:${isCritical ? "#e5484d" : "#ff9b9e"}">${esc(bannerAlert.name || bannerAlert.raw_id || `User ${bannerAlert.user_id}`)}</span><span class="text-faint"> :: </span>${esc(bannerAlert.reasons || "flagged for investigation")}</p>
        </div>
        <button class="btn-investigate" id="banner-investigate">Investigate →</button>
      </div></div>`;
    bc.querySelector("#banner-investigate").addEventListener("click", () => openInvestigate(bannerAlert.eventId));
  }

  // Alert feed
  const alertList = $("#alert-list");
  if (alerts.length === 0) {
    alertList.innerHTML = `<div class="panel-inset text-faint text-xs text-center py-10">No alerts yet — feed will update live</div>`;
  } else {
    alerts.slice(0, 12).forEach(a => {
      const row = document.createElement("button");
      row.className = "alert-item";
      row.innerHTML = `
        <div class="flex-between mb-1"><span class="badge-transition"></span><span class="text-10 text-faint">${esc(a.timestamp)}</span></div>
        <div class="text-xs text-ink mono">${esc(a.name || a.raw_id || `User ${a.user_id}`)}</div>
        <div class="flex-between mt-1">
          <div class="text-11 text-dim">Score: ${(a.combined_score ?? 0).toFixed(3)}</div>
          <div class="score-bar-bg"><div class="score-bar" style="width:${Math.min(100, (a.combined_score ?? 0) * 100)}%;background:${a.severity === "critical" ? "#e5484d" : a.severity === "high" ? "#ff9b9e" : "#e8a33d"}"></div></div>
        </div>`;
      row.querySelector(".badge-transition").appendChild(severityBadge(a.severity));
      row.addEventListener("click", () => openInvestigate(a.eventId));
      alertList.appendChild(row);
    });
  }

  // Threat gauge
  const threatValue = events.length ? Math.max(...events.map(e => e.combined_score || 0)) : 0;
  _gauge = renderGauge($("#gauge-container"), threatValue);

  // Score trend
  renderAreaChart($("#score-chart"), events);

  // Risk split
  renderDonut($("#risk-donut"), riskDist);

  // Event table
  const tbody = $("#event-tbody");
  events.slice(0, 10).forEach(e => {
    tbody.appendChild(eventRow(e, (id) => openInvestigate(id)));
  });
}

// ── Alerts Page ───────────────────────────────────────────────
async function renderAlerts(main) {
  const [alerts, dashData] = await Promise.all([getAlerts(), getDashboard()]);
  const events = dashData?.recentEvents || [];
  const kpis = dashData?.kpis || {};

  let currentFilter = "all";

  main.innerHTML = `
    <div class="flex-center gap-3 mb-4">
      <h2 class="text-sm font-bold text-ink uppercase tracking-wider">Alerts</h2>
      <div class="flex gap-1" id="filter-btns"></div>
    </div>
    <div class="grid-12 gap-4 mb-4">
      <div class="col-8 panel p-4" id="heatmap-container"></div>
      <div class="col-4 panel p-4 flex-center" id="rings-container"></div>
    </div>
    <div class="panel p-4 mb-4" id="offenders-container"></div>
    <div class="panel overflow-hidden">
      <table class="table-glass"><thead><tr>
        <th>Severity</th><th>User</th><th>Score</th><th>Decision</th><th>Time</th><th>Status</th><th></th>
      </tr></thead><tbody id="alerts-tbody"></tbody></table>
    </div>`;

  // Filter buttons
  const filterBtns = $("#filter-btns");
  ["all", "critical", "high", "medium", "low"].forEach(f => {
    const btn = document.createElement("button");
    btn.className = `filter-btn ${f === "all" ? "active" : ""}`;
    btn.textContent = f;
    btn.addEventListener("click", () => {
      currentFilter = f;
      filterBtns.querySelectorAll(".filter-btn").forEach(b => b.classList.toggle("active", b.textContent === f));
      renderAlertTable(alerts, currentFilter);
    });
    filterBtns.appendChild(btn);
  });

  function renderAlertTable(allAlerts, filter) {
    const filtered = filter === "all" ? allAlerts : allAlerts.filter(a => a.severity === filter);
    const tbody = $("#alerts-tbody");
    tbody.innerHTML = "";
    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-faint py-8">No alerts</td></tr>`;
      return;
    }
    filtered.forEach(a => tbody.appendChild(alertRow(a, (id) => openInvestigate(id), async (id) => { await ackAlert(id); })));
  }

  renderHeatmap($("#heatmap-container"), events);
  renderThreatRings($("#rings-container"), kpis);
  renderTopOffenders($("#offenders-container"), events);
  renderAlertTable(alerts, currentFilter);
}

// ── Users Page ────────────────────────────────────────────────
async function renderUsers(main) {
  const users = await getUsers();
  main.innerHTML = `
    <h2 class="text-sm font-bold text-ink uppercase tracking-wider mb-4">Users</h2>
    <div class="panel overflow-hidden">
      <table class="table-glass"><thead><tr>
        <th>User</th><th>Raw ID</th><th>Persona</th><th>Live Events</th><th>Flags</th><th>Max Score</th>
      </tr></thead><tbody id="users-tbody"></tbody></table>
    </div>`;
  const tbody = $("#users-tbody");
  users.forEach(u => tbody.appendChild(userRow(u)));
}

// ── Settings Page ─────────────────────────────────────────────
async function renderSettings(main) {
  const stats = await getStats();
  main.innerHTML = `
    <div class="flex-center gap-2 mb-4"><span class="text-lg">⚙</span><h1 class="text-lg font-bold text-ink">Settings</h1></div>
    <div class="panel p-4 mb-4">
      <div class="section-title mb-3">System Status</div>
      <div class="grid-4 gap-3">
        <div class="panel-inset p-3 rounded"><div class="text-xl font-bold mono text-ochre">${(stats.live_events ?? 0).toLocaleString()}</div><div class="text-11 text-faint mt-1 uppercase tracking-wide">Live Events</div></div>
        <div class="panel-inset p-3 rounded"><div class="text-xl font-bold mono text-critical">${(stats.alerts ?? 0).toLocaleString()}</div><div class="text-11 text-faint mt-1 uppercase tracking-wide">Alerts</div></div>
        <div class="panel-inset p-3 rounded"><div class="text-xl font-bold mono text-low">${(stats.history_events ?? 0).toLocaleString()}</div><div class="text-11 text-faint mt-1 uppercase tracking-wide">History Events</div></div>
        <div class="panel-inset p-3 rounded"><div class="text-xl font-bold mono text-ink">${(stats.users ?? 0).toLocaleString()}</div><div class="text-11 text-faint mt-1 uppercase tracking-wide">Users</div></div>
      </div>
    </div>
    <div class="panel p-4 mb-4" style="border-left:3px solid #e5484d40">
      <div class="flex-center gap-2 mb-2"><span class="text-critical">⚠</span><h2 class="section-title text-critical">Danger Zone</h2></div>
      <p class="text-sm text-dim mb-4">Clears all scored live events and alerts. Seeded history and user profiles are preserved.</p>
      <div id="reset-btn-container"></div>
      <div id="reset-msg" class="mt-3 text-sm text-low"></div>
    </div>
    <div class="panel p-4 mb-4">
      <div class="flex-center gap-2 mb-3"><span class="text-ochre">🛡</span><h2 class="section-title">Model Configuration</h2></div>
      <div class="space-y-2 text-sm">
        <div class="flex-between py-15 border-bottom"><span class="text-faint">IF Model</span><span class="text-ink mono text-xs">lanl_if.joblib</span></div>
        <div class="flex-between py-15 border-bottom"><span class="text-faint">LGB Model</span><span class="text-ink mono text-xs">lanl_lgb.joblib (display only)</span></div>
        <div class="flex-between py-15 border-bottom"><span class="text-faint">Flag Threshold</span><span class="text-ink mono text-xs">≥ 0.65</span></div>
        <div class="flex-between py-15 border-bottom"><span class="text-faint">Block Threshold</span><span class="text-ink mono text-xs">≥ 0.75</span></div>
        <div class="flex-between py-15"><span class="text-faint">Deviation Checks</span><span class="text-ink mono text-xs">new_dst, new_src, velocity, auth_failures</span></div>
      </div>
    </div>
    <div class="panel p-4">
      <h2 class="section-title mb-3">Quick Commands</h2>
      <div class="panel-inset p-25 rounded mono text-dim text-sm"><span class="text-ochre">$</span> make demo-reset <span class="text-faint"># full reset + re-seed</span></div>
      <div class="panel-inset p-25 rounded mono text-dim text-sm mt-2"><span class="text-ochre">$</span> make demo <span class="text-faint"># start server</span></div>
    </div>`;

  const resetContainer = $("#reset-btn-container");
  resetContainer.appendChild(holdButton("Hold to Reset Live Data", 3000, async () => {
    await resetDashboard();
    $("#reset-msg").textContent = "Live data cleared.";
    setTimeout(() => { $("#reset-msg").textContent = ""; }, 3000);
    renderSettings(main);
  }));
}

// ── Investigation ─────────────────────────────────────────────
async function openInvestigate(eventId) {
  if (!eventId) return;
  try {
    const data = await getInvestigation(eventId);
    investigationDrawer(data);
  } catch (err) {
    console.error("Investigation failed:", err);
  }
}

// ── Health dot ────────────────────────────────────────────────
function setHealth(ok) {
  const dot = $("#health-dot");
  const label = $("#health-label");
  if (!dot || !label) return;
  dot.classList.toggle("err", !ok);
  label.textContent = ok ? "connected" : "reconnecting";
}

// ── Init ──────────────────────────────────────────────────────
function init() {
  _currentPage = getPage();
  updateNav();
  render();

  window.addEventListener("hashchange", () => {
    _currentPage = getPage();
    updateNav();
    render();
  });

  $$(".sidebar-item").forEach(el => {
    el.addEventListener("click", () => navigate(el.dataset.page));
  });

  // Theme toggle
  const themeBtn = $("#theme-toggle");
  if (themeBtn) {
    const saved = localStorage.getItem("theme");
    if (saved === "dark" || (!saved && window.matchMedia("(prefers-color-scheme: dark)").matches)) {
      document.documentElement.classList.add("dark");
    }
    themeBtn.addEventListener("click", () => {
      document.documentElement.classList.toggle("dark");
      localStorage.setItem("theme", document.documentElement.classList.contains("dark") ? "dark" : "light");
    });
  }

  // SSE + polling
  let refreshTimer = null;
  function scheduleRefresh() {
    if (refreshTimer) return;
    refreshTimer = setTimeout(() => { refreshTimer = null; render(); }, 500);
  }
  connectSSE({
    onScore: scheduleRefresh,
    onConnect: () => setHealth(true),
    onDisconnect: () => setHealth(false),
  });
  setInterval(scheduleRefresh, 3000);
}

document.addEventListener("DOMContentLoaded", init);
