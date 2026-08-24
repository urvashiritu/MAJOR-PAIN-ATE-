import { esc } from "./utils.js";

export function severityBadge(level) {
  const span = document.createElement("span");
  span.className = `stamp stamp-${level}`;
  span.textContent = level;
  return span;
}

const SEV_COLORS = { low: "#57b06c", medium: "#e8a33d", high: "#ff9b9e", critical: "#e5484d", info: "#6ea8e8" };

export function sevColor(level) {
  return SEV_COLORS[level] || "#718296";
}

export function kpiCard({ key, label, icon, color }, value, sparkData) {
  const el = document.createElement("div");
  el.className = "panel panel-hover p-3 h-full";
  el.innerHTML = `
    <div class="flex-between mb-2">
      <div class="kpi-icon" style="border-color:${color}33;color:${color}">${icon}</div>
      <span class="tape-label">${label}</span>
    </div>
    <div class="flex-between gap-3">
      <div class="tape-perf pr-3 flex-1 min-w-0">
        <p class="tape-num" style="color:${color}">${value}</p>
        <div class="flex-center gap-1 mt-1">
          <span class="text-faint text-10 uppercase tracking-widest">live</span>
          <span class="live-dot"></span>
        </div>
      </div>
      <div class="sparkline-box" id="spark-${key}"></div>
    </div>`;
  return el;
}

export function eventRow(e, onClick) {
  const tr = document.createElement("tr");
  tr.className = "clickable";
  tr.addEventListener("click", () => onClick?.(e.id));
  const resClass = e.result === "Success" ? "text-low" : "text-critical";
  tr.innerHTML = `
    <td class="text-ink">${esc(e.name || e.raw_id || e.user_id)}</td>
    <td>${esc(e.src_computer)}</td>
    <td>${esc(e.dst_computer)}</td>
    <td>${esc(e.auth_type)}</td>
    <td><span class="${resClass}">${esc(e.result)}</span></td>
    <td class="text-ink font-bold">${(e.combined_score ?? 0).toFixed(3)}</td>
    <td><span class="text-10 uppercase ${e.decision === "block" ? "text-critical" : e.decision === "flag" ? "text-high" : "text-low"}">${esc(e.decision)}</span></td>
    <td class="text-faint">${esc(e.ts)}</td>`;
  return tr;
}

export function alertRow(a, onInvestigate, onAck) {
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td></td>
    <td class="text-ink font-bold">${esc(a.name || a.raw_id)}</td>
    <td class="text-ink font-bold">${(a.combined_score ?? 0).toFixed(3)}</td>
    <td class="text-dim">${esc(a.decision)}</td>
    <td class="text-faint">${esc(a.timestamp)}</td>
    <td><span class="text-10 uppercase ${a.status === "acknowledged" ? "text-low" : "text-critical"}">${a.status}</span></td>
    <td class="flex gap-1"></td>`;
  tr.children[0].appendChild(severityBadge(a.severity));

  const btns = tr.children[6];
  const invBtn = document.createElement("button");
  invBtn.className = "btn-ochre";
  invBtn.textContent = "Investigate";
  invBtn.addEventListener("click", () => onInvestigate?.(a.eventId));
  btns.appendChild(invBtn);

  if (a.status !== "acknowledged") {
    const ackBtn = document.createElement("button");
    ackBtn.className = "btn-muted";
    ackBtn.textContent = "Ack";
    ackBtn.addEventListener("click", async () => {
      await onAck?.(a.id);
      ackBtn.replaceWith(Object.assign(document.createElement("span"), {
        className: "text-10 uppercase text-low", textContent: "acknowledged"
      }));
    });
    btns.appendChild(ackBtn);
  }
  return tr;
}

export function userRow(u) {
  const tr = document.createElement("tr");
  const personaClass = u.persona === "attacker" ? "bg-critical-20 text-critical" : "bg-low-20 text-low";
  tr.innerHTML = `
    <td class="text-ink font-bold">${esc(u.name)}</td>
    <td class="text-dim">${esc(u.raw_id)}</td>
    <td><span class="badge-sm ${personaClass}">${esc(u.persona)}</span></td>
    <td class="text-ink">${u.live_events ?? 0}</td>
    <td class="text-ink">${u.flags ?? 0}</td>
    <td class="text-ink font-bold">${(u.max_score ?? 0).toFixed(3)}</td>`;
  return tr;
}

export function holdButton(label, duration, onDone) {
  const btn = document.createElement("button");
  btn.className = "btn-hold";
  btn.textContent = label;
  let timer = null;
  let filling = false;

  btn.addEventListener("mousedown", () => {
    filling = true;
    btn.classList.add("filling");
    btn.style.setProperty("--hold-duration", `${duration}ms`);
    timer = setTimeout(() => {
      if (filling) { onDone?.(); btn.classList.remove("filling"); }
    }, duration);
  });
  btn.addEventListener("mouseup", cancel);
  btn.addEventListener("mouseleave", cancel);

  function cancel() {
    filling = false;
    clearTimeout(timer);
    btn.classList.remove("filling");
  }
  return btn;
}

export function investigationDrawer(data, onClose) {
  const close = onClose || (() => {});
  const overlay = document.createElement("div");
  overlay.className = "drawer-overlay";
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });

  const drawer = document.createElement("div");
  drawer.className = "drawer";

  const features = data?.featureContributions || [];
  const timeline = data?.timeline || [];
  const baseline = data?.baseline || {};

  drawer.innerHTML = `
    <div class="drawer-header">
      <div>
        <div class="flex-center gap-2 mb-1"><span class="stamp stamp-${data?.severity}">${data?.severity}</span><span class="text-dim text-xs">${data?.type}</span></div>
        <h3 class="text-ink font-bold">${esc(data?.displayName || "Unknown")}</h3>
        <p class="text-11 text-faint mt-05">${esc(data?.rawId)}</p>
      </div>
      <button class="drawer-close">&times;</button>
    </div>
    <div class="drawer-body">
      <div class="panel p-3">
        <div class="grid-3 text-center">
          <div><div class="kpi-label">Risk Score</div><div class="text-lg font-bold text-ink">${(data?.combinedScore ?? 0).toFixed(3)}</div></div>
          <div><div class="kpi-label">Anomaly (IF)</div><div class="text-lg font-bold text-info">${(data?.ifScore ?? 0).toFixed(3)}</div></div>
          <div><div class="kpi-label">Habit Breaks</div><div class="text-lg font-bold ${(data?.devPoints ?? 0) > 0 ? "text-critical" : "text-low"}">${data?.devPoints ?? 0}</div></div>
        </div>
        ${data?.devReasons ? `<div class="mt-2 text-11 text-dim">${esc(data.devReasons)}</div>` : ""}
      </div>
      <div class="panel p-3">
        <div class="section-title">Event</div>
        <div class="grid-2 gap-2 text-xs">
          <div><span class="text-faint">Source:</span> <span class="text-ink">${esc(data?.src_computer)}</span></div>
          <div><span class="text-faint">Dest:</span> <span class="text-ink">${esc(data?.dst_computer)}</span></div>
          <div><span class="text-faint">Auth:</span> <span class="text-ink">${esc(data?.auth_type)}</span></div>
          <div><span class="text-faint">Result:</span> <span class="${data?.result === "Success" ? "text-low" : "text-critical"}">${esc(data?.result)}</span></div>
        </div>
        <div class="mt-2 text-11 text-dim">${esc(data?.description)}</div>
      </div>
      ${features.length ? `<div class="panel p-3">
        <div class="section-title">Feature Signals</div>
        <div class="space-y-2">${features.map(f => `
          <div class="flex-start gap-2">
            <div class="dot mt-15" style="background:${f.color}"></div>
            <div><div class="text-xs text-ink font-semibold">${esc(f.feature)}</div><div class="text-11 text-dim">${esc(f.detail)}</div></div>
          </div>`).join("")}
        </div>
      </div>` : ""}
      ${data?.features ? `<div class="panel p-3">
        <div class="section-title">Raw Features</div>
        <div class="grid-2 gap-15">${Object.entries(data.features).map(([k, v]) => `
          <div class="flex-between text-11"><span class="text-faint">${esc(k)}</span><span class="text-ink mono">${typeof v === "number" ? v.toFixed(4) : v}</span></div>`).join("")}
        </div>
      </div>` : ""}
      ${baseline.totalEvents ? `<div class="panel p-3">
        <div class="section-title">User Baseline</div>
        <div class="grid-2 gap-2 text-11">
          <div><span class="text-faint">Total events:</span> <span class="text-ink">${baseline.totalEvents}</span></div>
          <div><span class="text-faint">Failure rate:</span> <span class="text-ink">${(baseline.failureRate * 100).toFixed(1)}%</span></div>
          <div><span class="text-faint">Avg events/hr:</span> <span class="text-ink">${baseline.avgEventsPerHour}</span></div>
          <div><span class="text-faint">Typical src:</span> <span class="text-ink">${(baseline.typicalSrcComputers || []).join(", ")}</span></div>
        </div>
      </div>` : ""}
      ${timeline.length ? `<div class="panel p-3">
        <div class="section-title">Recent Events</div>
        <div class="space-y-15">${timeline.map(t => `
          <div class="flex-center gap-2 text-11">
            <div class="dot ${t.severity === "critical" ? "bg-critical" : t.severity === "high" ? "bg-high" : "bg-faint"}"></div>
            <span class="text-faint w-50">${esc(t.time)}</span>
            <span class="text-ink flex-1">${esc(t.event)}</span>
            <span class="text-dim">${(t.score ?? 0).toFixed(3)}</span>
          </div>`).join("")}
        </div>
      </div>` : ""}
      <div class="flex gap-2">
        <button class="btn-low flex-1" id="drawer-ack">Acknowledge</button>
        <button class="btn-muted flex-1" id="drawer-close">Close</button>
      </div>
    </div>`;

  overlay.appendChild(drawer);
  document.body.appendChild(overlay);
  requestAnimationFrame(() => overlay.classList.add("open"));

  drawer.querySelector(".drawer-close").addEventListener("click", closeDrawer);
  drawer.querySelector("#drawer-close").addEventListener("click", closeDrawer);
  drawer.querySelector("#drawer-ack").addEventListener("click", async () => {
    const { ackAlert } = await import("./api.js");
    await ackAlert(data.eventId || data.id);
    closeDrawer();
  });

  function closeDrawer() {
    overlay.classList.remove("open");
    setTimeout(() => overlay.remove(), 300);
    close();
  }
}
