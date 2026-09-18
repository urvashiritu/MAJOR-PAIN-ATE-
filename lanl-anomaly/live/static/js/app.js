/* Main controller — data loading, rendering, IntersectionObserver */

(function() {
    'use strict';

    /* === Entrance Animation === */
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });

    document.querySelectorAll('.reveal').forEach(el => observer.observe(el));

    /* === Number Formatting === */
    function fmt(n) {
        if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
        if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
        return n.toLocaleString();
    }

    function fmtScore(n) {
        return n.toFixed(6);
    }

    /* === Render KPIs === */
    function renderKPIs(kpis) {
        document.getElementById('kpi-total').textContent = fmt(kpis.total_events);
        document.getElementById('kpi-detections').textContent = kpis.detections;
        document.getElementById('kpi-fp').textContent = kpis.false_positives;
        document.getElementById('kpi-rate').textContent = kpis.detection_rate + '%';
        document.getElementById('kpi-threshold').textContent = kpis.threshold.toFixed(4);
        document.getElementById('nav-status-text').textContent =
            `${kpis.detections}/${kpis.red_events} threats detected`;
    }

    /* === Render Top Users === */
    function renderTopUsers(users) {
        const container = document.getElementById('top-users-list');
        container.innerHTML = users.map((u, i) => `
            <div class="top-user-row">
                <span class="top-user-rank">${i + 1}</span>
                <span class="top-user-name">${u.src_user}</span>
                <span class="top-user-events">${u.events} events</span>
                <span class="top-user-score">${u.max_score.toFixed(4)}</span>
            </div>
        `).join('');
    }

    /* === Render Heatmap === */
    function renderHeatmap(heatmapData) {
        const container = document.getElementById('heatmap-container');
        if (!heatmapData.length) return;

        const users = [...new Set(heatmapData.map(d => d.user))];
        const hours = Array.from({ length: 24 }, (_, i) => i);
        const maxScore = Math.max(...heatmapData.map(d => d.score));

        const scoreMap = {};
        heatmapData.forEach(d => { scoreMap[`${d.user}-${d.hour}`] = d.score; });

        function cellColor(score) {
            if (!score || score === 0) return 'rgba(255,255,255,0.02)';
            const intensity = score / maxScore;
            // Teal to red gradient based on intensity
            const r = Math.round(45 + (239 - 45) * intensity);
            const g = Math.round(212 - 144 * intensity);
            const b = Math.round(191 - 123 * intensity);
            return `rgba(${r}, ${g}, ${b}, ${0.2 + intensity * 0.7})`;
        }

        let html = '<div class="heatmap-hour-labels" style="grid-template-columns: repeat(24, 1fr)">';
        hours.forEach(h => {
            html += `<span class="heatmap-hour-label">${h}</span>`;
        });
        html += '</div>';

        users.forEach(user => {
            html += '<div style="display: grid; grid-template-columns: 120px repeat(24, 1fr); gap: 2px; align-items: center; margin-bottom: 2px">';
            html += `<span class="heatmap-label">${user}</span>`;
            hours.forEach(h => {
                const score = scoreMap[`${user}-${h}`] || 0;
                html += `<div class="heatmap-cell" style="background: ${cellColor(score)}" title="${user} @ ${h}:00 — ${score.toFixed(6)}"></div>`;
            });
            html += '</div>';
        });

        container.innerHTML = html;
    }

    /* === Render Alerts Table === */
    function renderAlerts(alerts) {
        const tbody = document.getElementById('alerts-tbody');
        tbody.innerHTML = alerts.slice(0, 50).map(a => {
            const date = new Date(a.time * 1000);
            const timeStr = date.toISOString().slice(0, 19).replace('T', ' ');
            return `<tr>
                <td>${timeStr}</td>
                <td>${a.src_user}</td>
                <td>${a.dst_computer}</td>
                <td>${a.anomaly_score.toFixed(6)}</td>
                <td><span class="decision-badge decision-${a.decision}">${a.decision}</span></td>
            </tr>`;
        }).join('');
    }

    /* === Render Live Logins === */
    function renderLiveLogins(events) {
        const tbody = document.getElementById('live-logins-tbody');
        if (!events.length) return;
        tbody.innerHTML = events.map(e => {
            const date = new Date(e.time * 1000);
            const timeStr = date.toISOString().slice(0, 19).replace('T', ' ');
            const scoreClass = e.decision === 'BLOCK' ? 'score-block' : (e.decision === 'FLAG' ? 'score-flag' : 'score-allow');
            return `<tr class="${e.decision === 'BLOCK' ? 'row-block' : ''}">
                <td>${timeStr}</td>
                <td>${e.username}</td>
                <td>${e.src_computer}</td>
                <td>${e.dst_computer}</td>
                <td>${e.auth_type}</td>
                <td class="${scoreClass}">${e.score.toFixed(6)}</td>
                <td><span class="decision-badge decision-${e.decision}">${e.decision}</span></td>
            </tr>`;
        }).join('');
    }

    /* === Poll Live Events === */
    async function pollLiveEvents() {
        try {
            const events = await API.liveEvents();
            renderLiveLogins(events);
        } catch (e) { /* silent */ }
    }

    /* === Main === */
    async function init() {
        try {
            const [dash, alerts] = await Promise.all([
                API.dashboard(),
                API.alerts()
            ]);

            renderKPIs(dash.kpis);
            renderTopUsers(dash.top_users);
            renderHeatmap(dash.heatmap);
            renderAlerts(alerts);

            // Charts
            const timelineCtx = document.getElementById('chart-timeline').getContext('2d');
            createTimelineChart(timelineCtx, dash.timeline);

            // For distribution, we need all scores — use alerts data as proxy
            const scores = alerts.map(a => a.anomaly_score);
            const isRed = alerts.map(a => a.is_red);
            const distCtx = document.getElementById('chart-distribution').getContext('2d');
            createDistributionChart(distCtx, scores, isRed);

            // Poll live events every 2s
            pollLiveEvents();
            setInterval(pollLiveEvents, 2000);

        } catch (err) {
            console.error('failed to load dashboard:', err);
            document.getElementById('nav-status-text').textContent = 'error loading data';
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
