/* Main controller — theme, routing, data loading */

(function() {
    'use strict';

    /* === Theme Toggle === */
    function initTheme() {
        const saved = localStorage.getItem('theme');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        if (saved === 'dark' || (!saved && prefersDark)) {
            document.documentElement.classList.add('dark');
        }
        const btn = document.getElementById('theme-toggle');
        if (btn) {
            btn.addEventListener('click', () => {
                document.documentElement.classList.toggle('dark');
                localStorage.setItem('theme',
                    document.documentElement.classList.contains('dark') ? 'dark' : 'light'
                );
            });
        }
    }

    /* === Number Formatting === */
    function fmt(n) {
        if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
        if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
        return n.toLocaleString();
    }

    /* === Live Page: KPIs + Live Logins === */
    function isLivePage() {
        return !!document.getElementById('live-logins-tbody');
    }

    function isDatasetPage() {
        return !!document.getElementById('chart-timeline');
    }

    function renderLiveKPIs(kpis) {
        const el = (id) => document.getElementById(id);
        if (el('kpi-total')) el('kpi-total').textContent = fmt(kpis.total_events);
        if (el('kpi-blocked')) el('kpi-blocked').textContent = fmt(kpis.detections);
        if (el('kpi-rate')) el('kpi-rate').textContent = kpis.detection_rate + '%';
    }

    function renderDatasetKPIs(kpis) {
        const el = (id) => document.getElementById(id);
        if (el('kpi-total')) el('kpi-total').textContent = fmt(kpis.total_events);
        if (el('kpi-detections')) el('kpi-detections').textContent = fmt(kpis.detections);
        if (el('kpi-fp')) el('kpi-fp').textContent = fmt(kpis.false_positives);
        if (el('kpi-rate')) el('kpi-rate').textContent = kpis.detection_rate + '%';
        if (el('kpi-threshold')) el('kpi-threshold').textContent = kpis.threshold.toFixed(4);
    }

    function renderLiveLogins(events) {
        const tbody = document.getElementById('live-logins-tbody');
        if (!tbody || !events.length) return;
        tbody.innerHTML = events.map(e => {
            const date = new Date(e.time * 1000);
            const timeStr = date.toISOString().slice(11, 19);
            const decClass = 'stamp stamp-' + (e.decision === 'BLOCK' ? 'critical' : e.decision === 'FLAG' ? 'medium' : 'low');
            return `<tr>
                <td>${timeStr}</td>
                <td>${e.username}</td>
                <td>${e.src_computer}</td>
                <td>${e.dst_computer}</td>
                <td>${e.auth_type}</td>
                <td>${e.score.toFixed(6)}</td>
                <td><span class="${decClass}">${e.decision}</span></td>
            </tr>`;
        }).join('');
    }

    async function pollLiveEvents() {
        try {
            const events = await API.liveEvents();
            renderLiveLogins(events);
        } catch (e) { /* silent */ }
    }

    /* === Dataset Page: Charts + Heatmap + Alerts === */
    function renderTopUsers(users) {
        const container = document.getElementById('top-users-list');
        if (!container) return;
        container.innerHTML = users.map((u, i) => `
            <div class="offender-row">
                <span class="offender-name">${u.src_user}</span>
                <div class="offender-bar-bg">
                    <div class="offender-bar" style="width: ${Math.min(100, (u.events / users[0].events) * 100)}%"></div>
                </div>
                <span class="offender-count">${u.events}</span>
            </div>
        `).join('');
    }

    function renderHeatmap(heatmapData) {
        const container = document.getElementById('heatmap-container');
        if (!container || !heatmapData.length) return;

        const users = [...new Set(heatmapData.map(d => d.user))];
        const hours = Array.from({ length: 24 }, (_, i) => i);
        const maxScore = Math.max(...heatmapData.map(d => d.score));

        const scoreMap = {};
        heatmapData.forEach(d => { scoreMap[`${d.user}-${d.hour}`] = d.score; });

        function cellClass(score) {
            if (!score || score === 0) return 'heatmap-empty';
            const ratio = score / maxScore;
            if (ratio < 0.25) return 'heatmap-l1';
            if (ratio < 0.5) return 'heatmap-l2';
            if (ratio < 0.75) return 'heatmap-l3';
            return 'heatmap-l4';
        }

        let html = '<div style="display: grid; grid-template-columns: 120px repeat(24, 1fr); gap: 2px; align-items: center; margin-bottom: 2px">';
        html += '<span></span>';
        hours.forEach(h => {
            html += `<span class="heatmap-hour">${h}</span>`;
        });
        html += '</div>';

        users.forEach(user => {
            html += '<div style="display: grid; grid-template-columns: 120px repeat(24, 1fr); gap: 2px; align-items: center; margin-bottom: 2px">';
            html += `<span class="heatmap-day">${user}</span>`;
            hours.forEach(h => {
                const score = scoreMap[`${user}-${h}`] || 0;
                html += `<div class="heatmap-cell ${cellClass(score)}" title="${user} @ ${h}:00 — ${score.toFixed(6)}"></div>`;
            });
            html += '</div>';
        });

        container.innerHTML = html;
    }

    function renderAlerts(alerts) {
        const tbody = document.getElementById('alerts-tbody');
        if (!tbody) return;
        tbody.innerHTML = alerts.slice(0, 50).map(a => {
            const date = new Date(a.time * 1000);
            const timeStr = date.toISOString().slice(0, 19).replace('T', ' ');
            const decClass = 'stamp stamp-' + (a.decision === 'BLOCK' ? 'critical' : a.decision === 'FLAG' ? 'medium' : 'low');
            return `<tr>
                <td>${timeStr}</td>
                <td>${a.src_user}</td>
                <td>${a.dst_computer}</td>
                <td>${a.anomaly_score.toFixed(6)}</td>
                <td><span class="${decClass}">${a.decision}</span></td>
            </tr>`;
        }).join('');
    }

    /* === Init === */
    async function init() {
        initTheme();

        if (isLivePage()) {
            // Live page: load KPIs + start polling
            try {
                const dash = await API.dashboard();
                renderLiveKPIs(dash.kpis);
            } catch (e) {
                console.error('failed to load live KPIs:', e);
            }
            pollLiveEvents();
            setInterval(pollLiveEvents, 2000);
        }

        if (isDatasetPage()) {
            // Dataset page: load everything
            try {
                const [dash, alerts] = await Promise.all([
                    API.dashboard(),
                    API.alerts()
                ]);

                renderDatasetKPIs(dash.kpis);
                renderTopUsers(dash.top_users);
                renderHeatmap(dash.heatmap);
                renderAlerts(alerts);

                // Charts
                const timelineCtx = document.getElementById('chart-timeline').getContext('2d');
                createTimelineChart(timelineCtx, dash.timeline);

                const scores = alerts.map(a => a.anomaly_score);
                const isRed = alerts.map(a => a.is_red);
                const distCtx = document.getElementById('chart-distribution').getContext('2d');
                createDistributionChart(distCtx, scores, isRed);

            } catch (err) {
                console.error('failed to load dataset:', err);
            }
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
