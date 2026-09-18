/* Chart.js theme — ochre accent, JetBrains Mono */

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
                    pointHoverBackgroundColor: '#e5484d',
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
                    pointHoverBackgroundColor: '#e8a33d',
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
                x: {
                    ...CHART_DEFAULTS.scales.x,
                    ticks: { ...CHART_DEFAULTS.scales.x.ticks, maxTicksLimit: 12 }
                },
                y: {
                    ...CHART_DEFAULTS.scales.y,
                    ticks: { ...CHART_DEFAULTS.scales.y.ticks, callback: (v) => v.toFixed(2) }
                }
            }
        }
    });
}

function createDistributionChart(ctx, scores, isRed) {
    const bins = 50;
    const maxScore = Math.max(...scores);
    const binSize = maxScore / bins;

    const normalBins = new Array(bins).fill(0);
    const redBins = new Array(bins).fill(0);

    for (let i = 0; i < scores.length; i++) {
        const bin = Math.min(Math.floor(scores[i] / binSize), bins - 1);
        if (isRed[i]) {
            redBins[bin]++;
        } else {
            normalBins[bin]++;
        }
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
                    borderColor: 'rgba(139, 147, 165, 0.15)',
                    borderWidth: 0,
                    barPercentage: 1,
                    categoryPercentage: 1
                },
                {
                    label: 'Attack',
                    data: redBins,
                    backgroundColor: 'rgba(229, 72, 77, 0.6)',
                    borderColor: 'rgba(229, 72, 77, 0.35)',
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
                x: {
                    ...CHART_DEFAULTS.scales.x,
                    stacked: true,
                    ticks: { ...CHART_DEFAULTS.scales.x.ticks, maxTicksLimit: 10 }
                },
                y: {
                    ...CHART_DEFAULTS.scales.y,
                    stacked: true,
                    ticks: {
                        ...CHART_DEFAULTS.scales.y.ticks,
                        callback: (v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v
                    }
                }
            }
        }
    });
}
