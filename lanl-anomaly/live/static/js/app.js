/* Main SPA controller — hash routing, SSE, live + dataset pages */

(function() {
    'use strict';

    const content = document.getElementById('main-content');
    const LIVE_KPI_DEFS = [
        { key: 'totalEvents', label: 'Events Scored', icon: '⚡', color: 'info' },
        { key: 'anomalies', label: 'Anomalies', icon: '🛡', color: 'critical' },
        { key: 'highRiskUsers', label: 'High-Risk Users', icon: '⚠', color: 'medium' },
        { key: 'usersMonitored', label: 'Users Monitored', icon: '👥', color: 'low' },
    ];

    let _liveEvents = [];
    let _liveSparkData = { totalEvents: [], anomalies: [], highRiskUsers: [], usersMonitored: [] };
    let _activeCharts = [];
    let _sse = null;

    /* ── Theme ──────────────────────────────────────────────────── */
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
                    document.documentElement.classList.contains('dark') ? 'dark' : 'light');
            });
        }
    }

    /* ── Helpers ────────────────────────────────────────────────── */
    function fmt(n) {
        if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
        if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
        return n.toLocaleString();
    }

    function destroyCharts() {
        _activeCharts.forEach(c => { try { c.destroy(); } catch(e){} });
        _activeCharts = [];
    }

    function setActiveNav(page) {
        document.querySelectorAll('.sidebar-item[data-page]').forEach(el => {
            el.classList.toggle('active', el.dataset.page === page);
        });
    }

    /* ── Hash Router ────────────────────────────────────────────── */
    function getPage() {
        const hash = location.hash || '#/dashboard';
        const page = hash.replace('#/', '');
        return page || 'dashboard';
    }

    function navigate(page) {
        location.hash = '#/' + page;
    }

    /* ── Dashboard (live) ───────────────────────────────────────── */
    async function renderDashboard() {
        destroyCharts();
        setActiveNav('dashboard');

        content.innerHTML = `
            <div class="grid-4 gap-4 mb-4" id="kpi-grid">
                ${LIVE_KPI_DEFS.map((k, i) => kpiCard(k, null, 'spark-' + k.key)).join('')}
            </div>

            <div class="grid-12 gap-4 mb-4">
                <div class="col-5">
                    <div class="panel p-4">
                        <div class="section-title mb-3">Threat Level</div>
                        <div id="gauge-container" class="text-center"></div>
                        <div class="section-title mb-2 mt-3">Risk Distribution</div>
                        <div id="donut-container" class="text-center mt-2"></div>
                    </div>
                </div>
                <div class="col-7">
                    <div class="panel overflow-hidden">
                        <div class="flex-between px-4 py-3 hairline">
                            <span class="section-title">Live Logins</span>
                            <span class="flex-center gap-1 text-10 text-faint uppercase tracking-widest">
                                <span class="live-dot"></span> live
                            </span>
                        </div>
                        <div class="overflow-auto max-h-300">
                            <table class="table-glass">
                                <thead><tr>
                                    <th>Time</th><th>User</th><th>Source</th><th>Destination</th><th>Auth</th><th>Score</th><th>Decision</th>
                                </tr></thead>
                                <tbody id="events-tbody">
                                    <tr><td colspan="7" class="text-center text-faint py-8">
                                        <span class="live-dot"></span>
                                        <span class="ml-2">Waiting for login events...</span>
                                    </td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

            <div class="panel overflow-hidden">
                <div class="flex-between px-4 py-3 hairline">
                    <span class="section-title">Recent Alerts</span>
                    <span class="text-10 text-faint uppercase tracking-widest" id="alert-count">0 alerts</span>
                </div>
                <div class="overflow-auto max-h-300">
                    <table class="table-glass">
                        <thead><tr>
                            <th>Time</th><th>User</th><th>Reason</th><th>Score</th><th>Severity</th><th>Actions</th>
                        </tr></thead>
                        <tbody id="dash-alerts-tbody"></tbody>
                    </table>
                </div>
            </div>`;

        await loadDashboard();
    }

    async function loadDashboard() {
        try {
            const dash = await API.dashboard();
            _liveEvents = dash.recentEvents || [];

            // KPIs
            const k = dash.kpis;
            const vals = { totalEvents: fmt(k.totalEvents), anomalies: fmt(k.anomalies),
                           highRiskUsers: fmt(k.highRiskUsers), usersMonitored: fmt(k.usersMonitored) };

            LIVE_KPI_DEFS.forEach(kpi => {
                const el = document.getElementById('kpi-grid');
                // just update text
            });

            LIVE_KPI_DEFS.forEach(kpi => {
                const card = document.querySelector(`[id="spark-${kpi.key}"]`)?.closest('.panel');
                if (card) {
                    const numEl = card.querySelector('.tape-num');
                    if (numEl) numEl.textContent = vals[kpi.key] || '0';
                }
            });

            // Update spark data
            _liveSparkData.totalEvents.push(k.totalEvents);
            _liveSparkData.anomalies.push(k.anomalies);
            _liveSparkData.highRiskUsers.push(k.highRiskUsers);
            _liveSparkData.usersMonitored.push(k.usersMonitored);

            LIVE_KPI_DEFS.forEach(kpi => {
                const sparkEl = document.getElementById('spark-' + kpi.key);
                if (sparkEl && _liveSparkData[kpi.key].length > 1) {
                    const color = kpi.color === 'info' ? '#6ea8e8' : kpi.color === 'critical' ? '#e5484d'
                                : kpi.color === 'medium' ? '#e8a33d' : '#57b06c';
                    renderSparkline(sparkEl, _liveSparkData[kpi.key], color);
                }
            });

            // Gauge
            const threatRatio = k.totalEvents > 0 ? k.anomalies / k.totalEvents : 0;
            const gaugeEl = document.getElementById('gauge-container');
            if (gaugeEl) renderGauge(gaugeEl, threatRatio);

            // Risk donut
            const donutEl = document.getElementById('donut-container');
            if (donutEl && dash.riskDistribution) renderRiskDonut(donutEl, dash.riskDistribution);

            // Events table
            const tbody = document.getElementById('events-tbody');
            if (tbody && _liveEvents.length) {
                tbody.innerHTML = _liveEvents.slice().reverse().map(e =>
                    eventRow(e, openInvestigate)
                ).join('');
            }

            // Alerts
            const alertsTbody = document.getElementById('dash-alerts-tbody');
            if (alertsTbody && dash.alerts && dash.alerts.length) {
                alertsTbody.innerHTML = dash.alerts.slice().reverse().map(a =>
                    alertRow(a, openInvestigate, ackAlert)
                ).join('');
                const cnt = document.getElementById('alert-count');
                if (cnt) cnt.textContent = dash.alerts.length + ' alerts';
            }

        } catch (err) {
            console.error('dashboard load failed:', err);
        }
    }

    /* ── Alerts Page ────────────────────────────────────────────── */
    async function renderAlerts() {
        destroyCharts();
        setActiveNav('alerts');

        content.innerHTML = `
            <div class="flex-between mb-4">
                <div class="flex gap-2" id="severity-filters">
                    <button class="filter-btn active" data-sev="all">All</button>
                    <button class="filter-btn" data-sev="critical">Critical</button>
                    <button class="filter-btn" data-sev="high">High</button>
                </div>
                <span class="text-10 text-faint uppercase tracking-widest" id="alerts-total">0 alerts</span>
            </div>

            <div class="panel overflow-hidden">
                <div class="overflow-auto" style="max-height: calc(100vh - 200px)">
                    <table class="table-glass">
                        <thead><tr>
                            <th>Time</th><th>User</th><th>Reason</th><th>Score</th><th>Severity</th><th>Actions</th>
                        </tr></thead>
                        <tbody id="alerts-page-tbody">
                            <tr><td colspan="6" class="text-center text-faint py-8">Loading alerts...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>`;

        // Filter buttons
        document.getElementById('severity-filters').addEventListener('click', (e) => {
            const btn = e.target.closest('.filter-btn');
            if (!btn) return;
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadAlertsPage(btn.dataset.sev);
        });

        await loadAlertsPage('all');
    }

    async function loadAlertsPage(severity) {
        try {
            const alerts = await API.alerts();
            let filtered = alerts;
            if (severity !== 'all') filtered = alerts.filter(a => a.severity === severity);

            const tbody = document.getElementById('alerts-page-tbody');
            const totalEl = document.getElementById('alerts-total');
            if (totalEl) totalEl.textContent = filtered.length + ' alerts';

            if (tbody) {
                if (filtered.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-faint py-8">No alerts yet. Login events will appear here.</td></tr>';
                } else {
                    tbody.innerHTML = filtered.slice().reverse().map(a =>
                        alertRow(a, openInvestigate, ackAlert)
                    ).join('');
                }
            }
        } catch (err) {
            console.error('alerts load failed:', err);
        }
    }

    /* ── Users Page ─────────────────────────────────────────────── */
    async function renderUsers() {
        destroyCharts();
        setActiveNav('users');

        content.innerHTML = `
            <div class="panel overflow-hidden">
                <div class="flex-between px-4 py-3 hairline">
                    <span class="section-title">Monitored Users</span>
                    <span class="text-10 text-faint uppercase tracking-widest" id="users-total">0 users</span>
                </div>
                <div class="overflow-auto" style="max-height: calc(100vh - 200px)">
                    <table class="table-glass">
                        <thead><tr>
                            <th>User</th><th>Persona</th><th>Events</th><th>Flags</th><th>Max Score</th>
                        </tr></thead>
                        <tbody id="users-tbody">
                            <tr><td colspan="5" class="text-center text-faint py-8">Loading users...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>`;

        try {
            const users = await API.users();
            const tbody = document.getElementById('users-tbody');
            const totalEl = document.getElementById('users-total');
            if (totalEl) totalEl.textContent = users.length + ' users';
            if (tbody) {
                if (users.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-faint py-8">No users yet. Events will populate this page.</td></tr>';
                } else {
                    tbody.innerHTML = users.sort((a, b) => b.max_score - a.max_score).map(u =>
                        userRow(u)
                    ).join('');
                    tbody.addEventListener('click', (e) => {
                        const row = e.target.closest('tr[data-uid]');
                        if (row) openUserProfile(row.dataset.uid);
                    });
                }
            }
        } catch (err) {
            console.error('users load failed:', err);
        }
    }

    /* ── User Profile Drawer ────────────────────────────────────── */
    async function openUserProfile(userId) {
        try {
            const data = await API.userProfile(userId);
            userProfileDrawer(data);
        } catch (err) {
            console.error('user profile failed:', err);
        }
    }

    function userProfileDrawer(data) {
        const existing = document.querySelector('.drawer-overlay');
        if (existing) existing.remove();

        const b = data.baseline || {};
        const s = data.session || {};

        // Hourly pattern bar chart (simple HTML bars)
        const maxHour = Math.max(...(b.hourlyPattern || []), 1);
        const hourlyBars = (b.hourlyPattern || []).map((v, i) => {
            const h = Math.max(2, (v / maxHour) * 100);
            const color = (b.rareHours || []).includes(i) ? 'var(--high)' : 'var(--ochre)';
            return `<div title="${i}:00 — ${v} events" style="width:100%;height:${h}px;background:${color};border-radius:1px"></div>`;
        }).join('');

        const overlay = document.createElement('div');
        overlay.className = 'drawer-overlay';
        overlay.innerHTML = `
            <div class="drawer">
                <div class="drawer-header">
                    <div>
                        <div class="font-bold text-lg">${esc(data.user_id)}</div>
                        <div class="text-11 text-faint mt-05">User Baseline Profile</div>
                    </div>
                    <button class="drawer-close" id="drawer-close-btn">&times;</button>
                </div>

                <!-- Training Baseline -->
                <div class="panel-inset p-3">
                    <div class="drawer-section-title">Training Dataset Baseline</div>
                    <div class="text-12 text-dim space-y-15">
                        <div class="flex-between">
                            <span>Total Events</span>
                            <span class="font-bold mono">${(b.totalEvents || 0).toLocaleString()}</span>
                        </div>
                        <div class="flex-between">
                            <span>Typical Pairs</span>
                            <span class="font-bold mono">${b.typicalPairs || 0}</span>
                        </div>
                        <div class="flex-between">
                            <span>Avg Inter-Arrival</span>
                            <span class="font-bold mono">${b.avgIAT ? b.avgIAT.toFixed(0) + 's' : 'N/A'}</span>
                        </div>
                    </div>
                </div>

                <!-- Known Machines -->
                <div>
                    <div class="drawer-section-title">Known Source Machines (${(b.knownSrcComputers || []).length})</div>
                    <div class="flex flex-wrap gap-1">
                        ${(b.knownSrcComputers || []).map(c => `<span class="badge-sm bg-low-20">${esc(c)}</span>`).join('')}
                        ${(b.knownSrcComputers || []).length === 0 ? '<span class="text-11 text-faint">none</span>' : ''}
                    </div>
                </div>
                <div>
                    <div class="drawer-section-title">Known Destinations (${(b.knownDstComputers || []).length})</div>
                    <div class="flex flex-wrap gap-1">
                        ${(b.knownDstComputers || []).slice(0, 20).map(c => `<span class="badge-sm bg-low-20">${esc(c)}</span>`).join('')}
                        ${(b.knownDstComputers || []).length > 20 ? `<span class="text-11 text-faint">+${b.knownDstComputers.length - 20} more</span>` : ''}
                        ${(b.knownDstComputers || []).length === 0 ? '<span class="text-11 text-faint">none</span>' : ''}
                    </div>
                </div>

                <!-- Hourly Pattern -->
                <div>
                    <div class="drawer-section-title">Hourly Activity Pattern <span class="text-faint">(red = rare hour)</span></div>
                    <div style="display:flex;align-items:flex-end;gap:1px;height:40px">
                        ${hourlyBars}
                    </div>
                    <div class="flex-between text-9 text-faint mt-05">
                        <span>0:00</span><span>6:00</span><span>12:00</span><span>18:00</span><span>23:00</span>
                    </div>
                </div>

                <!-- Live Session -->
                <div class="panel-inset p-3">
                    <div class="drawer-section-title">Live Session</div>
                    <div class="text-12 text-dim space-y-15">
                        <div class="flex-between">
                            <span>Events Scored</span>
                            <span class="font-bold mono">${s.totalEvents || 0}</span>
                        </div>
                        <div class="flex-between">
                            <span>Flags/Blocks</span>
                            <span class="font-bold mono ${s.flags > 0 ? 'text-critical' : ''}">${s.flags || 0}</span>
                        </div>
                        <div class="flex-between">
                            <span>Max Score</span>
                            <span class="font-bold mono">${s.maxScore || 0}</span>
                        </div>
                        <div class="flex-between">
                            <span>First Seen</span>
                            <span class="mono">${s.firstSeen || 'N/A'}</span>
                        </div>
                    </div>
                </div>

                ${s.events && s.events.length ? `
                    <div>
                        <div class="drawer-section-title">Recent Events</div>
                        <div class="max-h-300 overflow-auto">
                            <table class="table-glass">
                                <thead><tr><th>Time</th><th>Route</th><th>Score</th><th>Decision</th></tr></thead>
                                <tbody>
                                    ${s.events.slice().reverse().map(e => {
                                        const dec = e.decision || 'allow';
                                        const cls = 'stamp stamp-' + (dec === 'block' ? 'critical' : dec === 'flag' ? 'medium' : 'low');
                                        return `<tr>
                                            <td class="nowrap">${esc(e.ts)}</td>
                                            <td class="text-11">${esc(e.src_computer)} → ${esc(e.dst_computer)}</td>
                                            <td class="mono text-11">${e.combined_score.toFixed(4)}</td>
                                            <td><span class="${cls}">${esc(e.decision)}</span></td>
                                        </tr>`;
                                    }).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>` : ''}
            </div>`;

        overlay.querySelector('#drawer-close-btn').addEventListener('click', () => {
            overlay.classList.remove('open');
            setTimeout(() => overlay.remove(), 250);
        });
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.classList.remove('open');
                setTimeout(() => overlay.remove(), 250);
            }
        });

        document.body.appendChild(overlay);
        requestAnimationFrame(() => overlay.classList.add('open'));
    }

    /* ── Settings Page ──────────────────────────────────────────── */
    async function renderSettings() {
        destroyCharts();
        setActiveNav('settings');

        content.innerHTML = `
            <div class="grid-2 gap-4 mb-4">
                <div class="panel p-4">
                    <div class="section-title mb-3">Session Stats</div>
                    <div id="stats-content" class="text-12 text-dim">Loading...</div>
                </div>
                <div class="panel p-4">
                    <div class="section-title mb-3">Model Info</div>
                    <div class="text-12 text-dim space-y-15">
                        <div>LightGBM + LSTM-AE ensemble</div>
                        <div>21 features</div>
                        <div>Threshold: auto-calibrated</div>
                    </div>
                </div>
            </div>

            <div class="panel p-4">
                <div class="section-title mb-3">Danger Zone</div>
                <div class="text-12 text-dim mb-3">Clear all live events and alerts. This cannot be undone.</div>
                <div id="reset-btn-container"></div>
                <div id="reset-status" class="text-11 text-low mt-2"></div>
            </div>`;

        try {
            const stats = await API.stats();
            const el = document.getElementById('stats-content');
            if (el) {
                el.innerHTML = `
                    <div class="space-y-15">
                        <div>Live events: <strong>${stats.live_events}</strong></div>
                        <div>Alerts: <strong>${stats.alerts}</strong></div>
                        <div>Users tracked: <strong>${stats.users}</strong></div>
                    </div>`;
            }
        } catch (err) {
            console.error('stats load failed:', err);
        }

        const resetContainer = document.getElementById('reset-btn-container');
        if (resetContainer) {
            const btn = holdButton('Hold to Reset Dashboard', 1500, async () => {
                try {
                    await API.reset();
                    _liveEvents = [];
                    _liveSparkData = { totalEvents: [], anomalies: [], highRiskUsers: [], usersMonitored: [] };
                    const status = document.getElementById('reset-status');
                    if (status) status.textContent = 'Dashboard cleared.';
                } catch (err) {
                    const status = document.getElementById('reset-status');
                    if (status) status.textContent = 'Reset failed.';
                }
            });
            resetContainer.appendChild(btn);
        }
    }

    /* ── Investigate ────────────────────────────────────────────── */
    async function openInvestigate(eventId) {
        try {
            const data = await API.investigation(eventId);
            investigationDrawer(data);
        } catch (err) {
            console.error('investigation failed:', err);
        }
    }

    /* ── Ack Alert ──────────────────────────────────────────────── */
    async function ackAlert(alertId) {
        try {
            await API.ackAlert(alertId);
            // Re-render current page to update
            const page = getPage();
            if (page === 'alerts') renderAlerts();
            else if (page === 'dashboard') renderDashboard();
        } catch (err) {
            console.error('ack failed:', err);
        }
    }

    /* ── SSE ────────────────────────────────────────────────────── */
    function startSSE() {
        if (_sse) _sse.close();
        _sse = API.connectSSE({
            onScore(event) {
                _liveEvents.push(event);
                if (_liveEvents.length > 300) _liveEvents = _liveEvents.slice(-200);

                // Update KPI spark data
                const k = {
                    totalEvents: _liveEvents.length,
                    anomalies: _liveEvents.filter(e => e.decision === 'flag' || e.decision === 'block').length,
                    highRiskUsers: new Set(_liveEvents.filter(e => e.decision === 'flag' || e.decision === 'block').map(e => e.user_id)).size,
                    usersMonitored: new Set(_liveEvents.map(e => e.user_id)).size,
                };
                Object.keys(_liveSparkData).forEach(key => _liveSparkData[key].push(k[key] || 0));

                // Re-render if on dashboard
                const page = getPage();
                if (page === 'dashboard') {
                    // Update KPI values
                    const kpiEl = document.getElementById('kpi-grid');
                    if (kpiEl) {
                        const panels = kpiEl.querySelectorAll('.panel');
                        LIVE_KPI_DEFS.forEach((kpi, i) => {
                            if (panels[i]) {
                                const numEl = panels[i].querySelector('.tape-num');
                                if (numEl) numEl.textContent = fmt(k[kpi.key] || 0);
                            }
                        });
                    }
                    // Update sparklines
                    LIVE_KPI_DEFS.forEach(kpi => {
                        const sparkEl = document.getElementById('spark-' + kpi.key);
                        if (sparkEl) {
                            const color = kpi.color === 'info' ? '#6ea8e8' : kpi.color === 'critical' ? '#e5484d'
                                        : kpi.color === 'medium' ? '#e8a33d' : '#57b06c';
                            renderSparkline(sparkEl, _liveSparkData[kpi.key], color);
                        }
                    });
                    // Update gauge
                    const gaugeEl = document.getElementById('gauge-container');
                    if (gaugeEl) renderGauge(gaugeEl, k.totalEvents > 0 ? k.anomalies / k.totalEvents : 0);
                    // Update risk donut
                    const donutEl = document.getElementById('donut-container');
                    if (donutEl) {
                        const allow = _liveEvents.filter(e => e.decision === 'allow').length;
                        const flag = _liveEvents.filter(e => e.decision === 'flag').length;
                        const block = _liveEvents.filter(e => e.decision === 'block').length;
                        renderRiskDonut(donutEl, [
                            { name: 'Allow', value: allow, color: '#57b06c' },
                            { name: 'Flag', value: flag, color: '#e8a33d' },
                            { name: 'Block', value: block, color: '#e5484d' },
                        ]);
                    }
                    // Update events table
                    const tbody = document.getElementById('events-tbody');
                    if (tbody) {
                        const rows = _liveEvents.slice().reverse().slice(0, 30).map(e => eventRow(e, openInvestigate)).join('');
                        tbody.innerHTML = rows;
                    }
                }
            },
            onError() {
                const dot = document.getElementById('health-dot');
                if (dot) dot.classList.add('err');
            }
        });
    }

    /* ── Route dispatcher ───────────────────────────────────────── */
    function route() {
        const page = getPage();
        switch (page) {
            case 'dashboard': renderDashboard(); break;
            case 'alerts': renderAlerts(); break;
            case 'users': renderUsers(); break;
            case 'settings': renderSettings(); break;
            default: renderDashboard(); break;
        }
    }

    /* ── Init ───────────────────────────────────────────────────── */
    function init() {
        initTheme();
        window.addEventListener('hashchange', route);
        route();
        startSSE();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
