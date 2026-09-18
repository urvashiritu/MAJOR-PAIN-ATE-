/* Chart.js dark theme configurations — updated for new color tokens */

const CHART_DEFAULTS = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: {
            display: false
        },
        tooltip: {
            backgroundColor: '#1E2130',
            titleColor: '#E8EAED',
            bodyColor: '#9CA3AF',
            borderColor: 'rgba(255,255,255,0.08)',
            borderWidth: 1,
            padding: 12,
            cornerRadius: 8,
            titleFont: { family: "'Plus Jakarta Sans', sans-serif", weight: '500', size: 13 },
            bodyFont: { family: "'SF Mono', monospace", size: 12 },
            displayColors: false
        }
    },
    scales: {
        x: {
            grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
            ticks: { color: '#6B7280', font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 } },
            border: { display: false }
        },
        y: {
            grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
            ticks: { color: '#6B7280', font: { family: "'SF Mono', monospace", size: 11 } },
            border: { display: false }
        }
    },
    animation: {
        duration: 800,
        easing: 'easeOutQuart'
    }
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
                    borderColor: 'rgba(239, 68, 68, 0.7)',
                    backgroundColor: 'rgba(239, 68, 68, 0.06)',
                    fill: true,
                    borderWidth: 1.5,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    pointHoverBackgroundColor: '#EF4444',
                    tension: 0.3
                },
                {
                    label: 'Mean Score',
                    data: meanScores,
                    borderColor: 'rgba(99, 102, 241, 0.8)',
                    backgroundColor: 'rgba(99, 102, 241, 0.08)',
                    fill: true,
                    borderWidth: 1.5,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    pointHoverBackgroundColor: '#6366F1',
                    tension: 0.3
                }
            ]
        },
        options: {
            ...CHART_DEFAULTS,
            interaction: {
                mode: 'index',
                intersect: false
            },
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
                    ticks: {
                        ...CHART_DEFAULTS.scales.x.ticks,
                        maxTicksLimit: 12
                    }
                },
                y: {
                    ...CHART_DEFAULTS.scales.y,
                    ticks: {
                        ...CHART_DEFAULTS.scales.y.ticks,
                        callback: (v) => v.toFixed(2)
                    }
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
                    backgroundColor: 'rgba(156, 163, 175, 0.4)',
                    borderColor: 'rgba(156, 163, 175, 0.2)',
                    borderWidth: 0,
                    barPercentage: 1,
                    categoryPercentage: 1
                },
                {
                    label: 'Attack',
                    data: redBins,
                    backgroundColor: 'rgba(239, 68, 68, 0.6)',
                    borderColor: 'rgba(239, 68, 68, 0.4)',
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
                    ticks: {
                        ...CHART_DEFAULTS.scales.x.ticks,
                        maxTicksLimit: 10
                    }
                },
                y: {
                    ...CHART_DEFAULTS.scales.y,
                    stacked: true,
                    ticks: {
                        ...CHART_DEFAULTS.scales.y.ticks,
                        callback: (v) => v >= 1000 ? `${(v/1000).toFixed(0)}k` : v
                    }
                }
            }
        }
    });
}
