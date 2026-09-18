/* Chart.js configs + sparklines + gauge + risk donut */

const MONO = "'JetBrains Mono', monospace";

const CHART_DEFAULTS = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: { display: false },
        tooltip: {
            backgroundColor: '#1e2736',
            titleColor: '#e8ecf4',
            bodyColor: '#8b93a5',
            borderColor: 'rgba(255,255,255,0.08)',
            borderWidth: 1,
            padding: 12,
            cornerRadius: 6,
            titleFont: { family: MONO, weight: '600', size: 12 },
            bodyFont: { family: MONO, size: 11 },
            displayColors: false
        }
    },
    scales: {
        x: {
            grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
            ticks: { color: '#5a6274', font: { family: MONO, size: 10 } },
            border: { display: false }
        },
        y: {
            grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
            ticks: { color: '#5a6274', font: { family: MONO, size: 10 } },
            border: { display: false }
        }
    },
    animation: { duration: 800, easing: 'easeOutQuart' }
};

/* ── Sparkline (SVG) ────────────────────────────────────────── */
function renderSparkline(container, data, color) {
    if (!container || !data || data.length < 2) return;
    const w = container.clientWidth || 64;
    const h = container.clientHeight || 28;
    const max = Math.max(...data, 0.001);
    const min = Math.min(...data, 0);
    const range = max - min || 0.001;
    const points = data.map((v, i) => {
        const x = (i / (data.length - 1)) * w;
        const y = h - ((v - min) / range) * (h - 4) - 2;
        return `${x},${y}`;
    }).join(' ');

    container.innerHTML = `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
        <polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;
}

/* ── Gauge (SVG semicircle) ─────────────────────────────────── */
function renderGauge(container, value) {
    if (!container) return;
    const pct = Math.min(1, Math.max(0, value));
    const radius = 45;
    const cx = 60;
    const cy = 55;
    const circumference = Math.PI * radius;
    const offset = circumference * (1 - pct);

    let color = 'var(--low)';
    if (pct > 0.7) color = 'var(--critical)';
    else if (pct > 0.4) color = 'var(--medium)';

    container.innerHTML = `
        <div class="gauge-wrap">
            <svg class="gauge-svg" viewBox="0 0 120 70">
                <path class="gauge-track" d="M 15 55 A 45 45 0 0 1 105 55"/>
                <path class="gauge-fill" d="M 15 55 A 45 45 0 0 1 105 55"
                    stroke="${color}"
                    stroke-dasharray="${circumference}"
                    stroke-dashoffset="${offset}"/>
                <text class="gauge-center" x="${cx}" y="${cy - 5}" text-anchor="middle">${(pct * 100).toFixed(0)}%</text>
            </svg>
            <span class="gauge-label">threat level</span>
        </div>`;
}

/* ── Risk Donut (SVG) ───────────────────────────────────────── */
function renderRiskDonut(container, data) {
    if (!container || !data) return;
    const total = data.reduce((s, d) => s + d.value, 0) || 1;
    const size = 120;
    const cx = size / 2;
    const cy = size / 2;
    const r = 45;
    const circumference = 2 * Math.PI * r;

    let offset = 0;
    const arcs = data.map(d => {
        const pct = d.value / total;
        const dash = pct * circumference;
        const gap = circumference - dash;
        const html = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${d.color}" stroke-width="12"
            stroke-dasharray="${dash} ${gap}" stroke-dashoffset="${-offset}" transform="rotate(-90 ${cx} ${cy})"/>`;
        offset += dash;
        return html;
    }).join('');

    container.innerHTML = `
        <div class="donut-wrap">
            <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
                <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--wash-strong)" stroke-width="12"/>
                ${arcs}
            </svg>
            <div class="donut-center">
                <div class="donut-center-num">${total}</div>
                <div class="donut-center-label">events</div>
            </div>
        </div>`;
}

/* ── Timeline Chart (dataset) ───────────────────────────────── */
function createTimelineChart(ctx, data) {
    const labels = data.map((_, i) => i);
    const meanScores = data.map(d => d.mean_score);
    const maxScores = data.map(d => d.max_score);

    return new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Max Score',
                    data: maxScores,
                    borderColor: 'rgba(229, 72, 77, 0.8)',
                    backgroundColor: 'rgba(229, 72, 77, 0.08)',
                    fill: true,
                    borderWidth: 1.5,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    tension: 0.3
                },
                {
                    label: 'Mean Score',
                    data: meanScores,
                    borderColor: 'rgba(232, 163, 61, 0.9)',
                    backgroundColor: 'rgba(232, 163, 61, 0.1)',
                    fill: true,
                    borderWidth: 1.5,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    tension: 0.3
                }
            ]
        },
        options: {
            ...CHART_DEFAULTS,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                ...CHART_DEFAULTS.plugins,
                tooltip: {
                    ...CHART_DEFAULTS.plugins.tooltip,
                    callbacks: {
                        title: (items) => `Hour ${items[0].label}`,
                        label: (item) => `${item.dataset.label}: ${item.raw.toFixed(6)}`
                    }
                }
            },
            scales: {
                ...CHART_DEFAULTS.scales,
                x: { ...CHART_DEFAULTS.scales.x, ticks: { ...CHART_DEFAULTS.scales.x.ticks, maxTicksLimit: 12 } },
                y: { ...CHART_DEFAULTS.scales.y, ticks: { ...CHART_DEFAULTS.scales.y.ticks, callback: (v) => v.toFixed(2) } }
            }
        }
    });
}

/* ── Distribution Chart (dataset) ───────────────────────────── */
function createDistributionChart(ctx, scores, isRed) {
    const bins = 50;
    const maxScore = Math.max(...scores);
    const binSize = maxScore / bins;
    const normalBins = new Array(bins).fill(0);
    const redBins = new Array(bins).fill(0);

    for (let i = 0; i < scores.length; i++) {
        const bin = Math.min(Math.floor(scores[i] / binSize), bins - 1);
        if (isRed[i]) redBins[bin]++;
        else normalBins[bin]++;
    }

    const labels = Array.from({ length: bins }, (_, i) => (i * binSize).toFixed(3));

    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                {
                    label: 'Normal',
                    data: normalBins,
                    backgroundColor: 'rgba(139, 147, 165, 0.35)',
                    borderWidth: 0,
                    barPercentage: 1,
                    categoryPercentage: 1
                },
                {
                    label: 'Attack',
                    data: redBins,
                    backgroundColor: 'rgba(229, 72, 77, 0.6)',
                    borderWidth: 0,
                    barPercentage: 1,
                    categoryPercentage: 1
                }
            ]
        },
        options: {
            ...CHART_DEFAULTS,
            plugins: {
                ...CHART_DEFAULTS.plugins,
                tooltip: {
                    ...CHART_DEFAULTS.plugins.tooltip,
                    callbacks: {
                        title: (items) => `Score: ${items[0].label}`,
                        label: (item) => `${item.dataset.label}: ${item.raw.toLocaleString()}`
                    }
                }
            },
            scales: {
                ...CHART_DEFAULTS.scales,
                x: { ...CHART_DEFAULTS.scales.x, stacked: true, ticks: { ...CHART_DEFAULTS.scales.x.ticks, maxTicksLimit: 10 } },
                y: { ...CHART_DEFAULTS.scales.y, stacked: true, ticks: { ...CHART_DEFAULTS.scales.y.ticks, callback: (v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v } }
            }
        }
    });
}
