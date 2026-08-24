import { esc } from "./utils.js";

let _chartInstances = [];

export function destroyCharts() {
  _chartInstances.forEach(c => c.destroy());
  _chartInstances = [];
}

function track(chart) {
  _chartInstances.push(chart);
  return chart;
}

export function renderSparkline(container, data, color) {
  const canvas = document.createElement("canvas");
  canvas.width = 64; canvas.height = 32;
  container.appendChild(canvas);
  return track(new Chart(canvas, {
    type: "line",
    data: {
      labels: data.map((_, i) => i),
      datasets: [{
        data: data.map(d => d.value),
        borderColor: color,
        borderWidth: 2,
        fill: true,
        backgroundColor: color + "25",
        pointRadius: 0,
        tension: 0.4,
      }]
    },
    options: {
      responsive: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } },
      animation: { duration: 600 },
    }
  }));
}

export function renderGauge(container, value) {
  const target = Math.min(Math.max(value, 0), 1);
  function getColor(v) {
    if (v < 0.4) return "#57b06c";
    if (v < 0.7) return "#e8a33d";
    return "#e5484d";
  }
  function getLabel(v) {
    if (v < 0.4) return "LOW";
    if (v < 0.7) return "ELEVATED";
    return "CRITICAL";
  }

  container.innerHTML = `
    <div class="gauge-label">Current Threat Level</div>
    <div class="gauge-wrap">
      <canvas id="gauge-canvas" width="180" height="100"></canvas>
      <div class="gauge-center">
        <div class="gauge-value" id="gauge-val">${Math.round(target * 100)}</div>
        <div class="gauge-status" id="gauge-status">${getLabel(target)}</div>
      </div>
    </div>
    <div class="gauge-legend">
      <span class="gauge-legend-item"><span class="dot-sm" style="background:#57b06c"></span>Safe</span>
      <span class="gauge-legend-item"><span class="dot-sm" style="background:#e8a33d"></span>Elevated</span>
      <span class="gauge-legend-item"><span class="dot-sm" style="background:#e5484d"></span>Critical</span>
    </div>`;

  const canvas = document.getElementById("gauge-canvas");
  const ctx = canvas.getContext("2d");
  const cx = 90, cy = 85, r = 70, stroke = 14;

  function draw(val) {
    const color = getColor(val);
    const angle = val * Math.PI;
    ctx.clearRect(0, 0, 180, 100);
    ctx.beginPath();
    ctx.arc(cx, cy, r, Math.PI, 0, false);
    ctx.strokeStyle = "#1a213220";
    ctx.lineWidth = stroke;
    ctx.lineCap = "round";
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy, r, Math.PI, Math.PI + angle, false);
    ctx.strokeStyle = color;
    ctx.lineWidth = stroke;
    ctx.lineCap = "round";
    ctx.stroke();
  }

  let current = 0;
  function animate() {
    current += (target - current) * 0.08;
    if (Math.abs(current - target) < 0.001) current = target;
    draw(current);
    const valEl = document.getElementById("gauge-val");
    const statEl = document.getElementById("gauge-status");
    if (valEl) { valEl.textContent = Math.round(current * 100); valEl.style.color = getColor(current); }
    if (statEl) { statEl.textContent = getLabel(current); statEl.style.color = getColor(current); }
    if (current !== target) requestAnimationFrame(animate);
  }
  animate();

  return {
    update(newValue) {
      const t = Math.min(Math.max(newValue, 0), 1);
      if (t !== target) { target = t; animate(); }
    }
  };
}

export function renderAreaChart(container, events) {
  const canvas = document.createElement("canvas");
  container.appendChild(canvas);

  const reversed = [...events].reverse();
  const data = reversed.map(e => ({
    score: e.combined_score || 0,
    name: e.name || `User ${e.user_id}`,
    dst: e.dst_computer,
    decision: e.decision,
    time: e.ts,
    color: e.decision === "block" ? "#e5484d" : e.decision === "flag" ? "#ff9b9e" : "#57b06c",
  }));

  const chart = track(new Chart(canvas, {
    type: "line",
    data: {
      labels: data.map((_, i) => i),
      datasets: [{
        data: data.map(d => d.score),
        borderColor: "#e8a33d",
        borderWidth: 2,
        fill: true,
        backgroundColor: "rgba(232,163,61,0.15)",
        pointRadius: data.map(d => d.decision === "block" ? 5 : d.decision === "flag" ? 4 : 3),
        pointBackgroundColor: data.map(d => d.color),
        pointBorderColor: data.map(d => d.color),
        pointBorderWidth: 1,
        pointFill: data.map(d => d.color + "cc"),
        tension: 0.3,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#1e2736",
          borderColor: "#e8a33d55",
          borderWidth: 1,
          titleFont: { family: "monospace", size: 10 },
          bodyFont: { family: "monospace", size: 11 },
          callbacks: {
            title: (items) => data[items[0].dataIndex]?.time || "",
            label: (item) => `Score: ${item.raw.toFixed(3)}`,
            afterLabel: (item) => {
              const d = data[item.dataIndex];
              return `${d.name} -> ${d.dst} [${d.decision}]`;
            }
          }
        },
        annotation: undefined,
      },
      scales: {
        x: { display: false },
        y: { min: 0, max: 1, grid: { color: "rgba(255,255,255,0.04)" }, ticks: { color: "#5a6274", font: { size: 9, family: "monospace" } } }
      },
    }
  }));

  const originalDraw = chart.draw.bind(chart);
  chart.draw = function () {
    originalDraw();
    const yAxis = chart.scales.y;
    const chartArea = chart.chartArea;
    const ctx = chart.ctx;
    [0.65, 0.75].forEach((yVal, i) => {
      const y = yAxis.getPixelForValue(yVal);
      ctx.save();
      ctx.beginPath();
      ctx.setLineDash(i === 0 ? [4, 4] : [2, 2]);
      ctx.strokeStyle = `rgba(229,72,77,${i === 0 ? 0.5 : 0.3})`;
      ctx.lineWidth = 1;
      ctx.moveTo(chartArea.left, y);
      ctx.lineTo(chartArea.right, y);
      ctx.stroke();
      ctx.restore();
    });
  };
  chart.draw();

  return chart;
}

export function renderDonut(container, data) {
  const total = data.reduce((s, d) => s + (d.value || 0), 0);
  if (!data.length || !total) {
    container.innerHTML = `<div class="h-150 flex-center text-faint text-10">No events yet</div>`;
    return null;
  }

  const canvas = document.createElement("canvas");
  canvas.style.position = "relative";
  container.appendChild(canvas);

  const chart = track(new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: data.map(d => d.name),
      datasets: [{
        data: data.map(d => d.value),
        backgroundColor: data.map(d => d.color),
        borderWidth: 0,
        borderRadius: 3,
        spacing: 3,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "58%",
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#1e2736",
          borderColor: "#e8a33d55",
          borderWidth: 1,
          titleFont: { family: "monospace", size: 10 },
          bodyFont: { family: "monospace", size: 11 },
          callbacks: {
            label: (item) => {
              const pct = Math.round((item.raw / total) * 100);
              return `${item.raw} events (${pct}%)`;
            }
          }
        }
      },
    }
  }));

  const center = document.createElement("div");
  center.className = "donut-center";
  center.innerHTML = `<div class="donut-total">${total}</div><div class="donut-label">events</div>`;
  container.style.position = "relative";
  container.appendChild(center);

  const legend = document.createElement("div");
  legend.className = "flex-wrap-center gap-x-3 gap-y-1 mt-1";
  data.forEach(d => {
    legend.innerHTML += `<span class="flex-center gap-1 text-10 text-faint"><span class="dot-sm" style="background:${d.color}"></span>${d.name}: ${d.value}</span>`;
  });
  container.appendChild(legend);

  return chart;
}

export function renderHeatmap(container, events) {
  const counts = Array(24).fill(0);
  events.forEach(e => {
    const ts = e.ts;
    if (!ts) return;
    const hour = parseInt(ts.split(":")[0], 10);
    if (!isNaN(hour)) counts[hour]++;
  });
  const maxVal = Math.max(1, ...counts);

  let svg = `<svg viewBox="0 0 720 60" class="heatmap-svg">`;
  svg += `<text x="0" y="12" class="heatmap-title">Activity Heatmap (last 24h)</text>`;

  counts.forEach((val, h) => {
    const intensity = val / maxVal;
    let cls = "heatmap-empty";
    if (intensity > 0 && intensity <= 0.25) cls = "heatmap-l1";
    else if (intensity > 0.25 && intensity <= 0.5) cls = "heatmap-l2";
    else if (intensity > 0.5 && intensity <= 0.75) cls = "heatmap-l3";
    else if (intensity > 0.75) cls = "heatmap-l4";
    const barH = Math.max(2, intensity * 30);
    svg += `<rect x="${10 + h * 29}" y="${55 - barH}" width="24" height="${barH}" rx="3" class="heatmap-cell ${cls}">
      <title>${String(h).padStart(2, "0")}:00 — ${val} events</title></rect>`;
    svg += `<text x="${22 + h * 29}" y="58" class="heatmap-hour" text-anchor="middle">${h}</text>`;
  });
  svg += `</svg>`;
  container.innerHTML = svg;
}

export function renderThreatRings(container, kpis) {
  const rings = [
    { label: "Events", value: kpis.totalEvents || 0, max: Math.max(1, kpis.totalEvents || 1), color: "#6ea8e8" },
    { label: "Anomalies", value: kpis.anomalies || 0, max: Math.max(1, kpis.totalEvents || 1), color: "#e5484d" },
    { label: "Users", value: kpis.usersMonitored || 0, max: 100, color: "#57b06c" },
  ];

  let svg = `<svg viewBox="0 0 160 160" class="threat-rings-svg">`;
  const cx = 80, cy = 80;
  const radii = [65, 50, 35];
  const strokeW = 8;

  rings.forEach((r, i) => {
    const radius = radii[i];
    const circumference = 2 * Math.PI * radius;
    const pct = Math.min(1, r.value / r.max);
    const offset = circumference * (1 - pct);
    svg += `<circle cx="${cx}" cy="${cy}" r="${radius}" fill="none" class="ring-track" stroke-width="${strokeW}"/>`;
    svg += `<circle cx="${cx}" cy="${cy}" r="${radius}" fill="none" stroke="${r.color}" stroke-width="${strokeW}"
      stroke-dasharray="${circumference}" stroke-dashoffset="${offset}" stroke-linecap="round"
      transform="rotate(-90 ${cx} ${cy})" style="transition: stroke-dashoffset 0.8s ease"/>`;
  });
  svg += `</svg>`;

  const legend = document.createElement("div");
  legend.className = "ring-legend";
  rings.forEach(r => {
    legend.innerHTML += `<span class="flex-center gap-1 text-10 text-faint"><span class="dot-sm" style="background:${r.color}"></span>${r.label}: ${r.value}</span>`;
  });

  container.innerHTML = svg;
  container.appendChild(legend);
}

export function renderTopOffenders(container, events) {
  const counts = {};
  events.forEach(e => {
    if (e.decision === "flag" || e.decision === "block") {
      const name = e.name || e.raw_id || `User ${e.user_id}`;
      counts[name] = (counts[name] || 0) + 1;
    }
  });
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const maxCount = sorted.length ? sorted[0][1] : 1;

  let html = `<div class="section-title">Top Offenders</div>`;
  sorted.forEach(([name, count]) => {
    const pct = (count / maxCount) * 100;
    html += `<div class="offender-row">
      <span class="offender-name">${esc(name)}</span>
      <div class="offender-bar-bg"><div class="offender-bar" style="width:${pct}%"></div></div>
      <span class="offender-count">${count}</span>
    </div>`;
  });
  if (!sorted.length) html += `<div class="text-faint text-10 text-center py-4">No flagged events</div>`;
  container.innerHTML = html;
}
