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
    const GREETINGS = ['Good morning', 'Good afternoon', 'Good evening'];

    let _liveEvents = [];
    let _liveSparkData = { totalEvents: [], anomalies: [], highRiskUsers: [], usersMonitored: [] };
    let _activeCharts = [];
    let _sse = null;
    let _echartsInstances = [];
    let _echartsInitialized = false;
    let _liveTimelineChart = null;
    let _liveScoresChart = null;
    let _liveUsersChart = null;
    let _liveAuthDonut = null;
    let _liveScoreHist = null;
    let _ssePaused = false;
    let _prevKpis = { totalEvents: 0, anomalies: 0, highRiskUsers: 0, usersMonitored: 0 };
    let _searchOverlay = null;

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
        _echartsInstances.forEach(c => { try { c.dispose(); } catch(e){} });
        _echartsInstances = [];
        _echartsInitialized = false;
        _liveAuthDonut = null;
        _liveScoreHist = null;
    }

    function getThemeColors() {
        const isDark = document.documentElement.classList.contains('dark');
        return {
            critical: isDark ? '#e5484d' : '#d13438',
            ochre: '#e8a33d',
            low: isDark ? '#57b06c' : '#2e7d51',
            info: isDark ? '#6ea8e8' : '#3a6cb5',
            ink: isDark ? '#e8ecf4' : '#232a38',
            inkDim: isDark ? '#8b93a5' : '#59617a',
            inkFaint: isDark ? '#5a6274' : '#939aad',
            gridLine: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(35,42,56,0.06)',
            tooltipBg: isDark ? '#1e2736' : '#fffdf6'
        };
    }

    function initEChart(id) {
        const el = document.getElementById(id);
        if (!el) return null;
        const theme = document.documentElement.classList.contains('dark') ? 'dark' : 'default';
        const ch = echarts.init(el, theme);
        _echartsInstances.push(ch);
        return ch;
    }

    function updateNarrative() {
        const el = document.getElementById('live-narrative');
        if (!el) return;
        const C = getThemeColors();
        if (_liveEvents.length === 0) {
            el.innerHTML = '<div style="font-weight:700;color:' + C.inkDim + ';font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">System Status</div>Waiting for login events. Users will appear here as they authenticate against the LANL network.';
            return;
        }
        const anomalies = _liveEvents.filter(e => e.decision === 'flag' || e.decision === 'block').length;
        const users = new Set(_liveEvents.map(e => e.user_id)).size;
        const blocks = _liveEvents.filter(e => e.decision === 'block').length;
        const highRisk = _liveEvents.filter(e => e.decision === 'flag' || e.decision === 'block');
        const topUser = highRisk.length > 0 ? highRisk.reduce((acc, e) => { acc[e.user_id] = (acc[e.user_id] || 0) + 1; return acc; }, {}) : {};
        const topEntry = Object.entries(topUser).sort((a, b) => b[1] - a[1])[0];
        let html = '<div style="font-weight:700;color:' + C.critical + ';font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">Live Analysis</div>';
        html += 'Scored <b>' + _liveEvents.length + '</b> events from <b>' + users + '</b> users. ';
        html += '<span style="color:' + C.low + '">' + (_liveEvents.length - anomalies) + '</span> allowed, ';
        html += '<span style="color:' + C.ochre + '">' + (anomalies - blocks) + '</span> flagged, ';
        html += '<span style="color:' + C.critical + '">' + blocks + '</span> blocked. ';
        if (topEntry) {
            html += '<b style="color:' + C.critical + '">' + topEntry[0].split('@')[0] + '</b> has ' + topEntry[1] + ' anomaly events.';
        }
        el.innerHTML = html;
    }

    function initLiveCharts() {
        if (_echartsInitialized) return;
        _echartsInitialized = true;
        const C = getThemeColors();

        _liveTimelineChart = initEChart('live-chart-timeline');
        if (_liveTimelineChart) {
            _liveTimelineChart.setOption({
                tooltip: { trigger: 'axis', backgroundColor: C.tooltipBg, textStyle: { color: C.ink, fontFamily: 'JetBrains Mono', fontSize: 11 } },
                grid: { left: 50, right: 16, top: 30, bottom: 24 },
                legend: { data: ['Total', 'Anomalies'], textStyle: { color: C.inkDim, fontSize: 10, fontFamily: 'JetBrains Mono' }, top: 0, right: 16 },
                xAxis: { type: 'category', data: [], axisLabel: { color: C.inkFaint, fontSize: 9 }, axisLine: { lineStyle: { color: C.gridLine } } },
                yAxis: { type: 'value', name: 'Events', nameTextStyle: { color: C.inkFaint, fontSize: 9 }, axisLabel: { color: C.inkFaint, fontSize: 9 }, splitLine: { lineStyle: { color: C.gridLine } } },
                series: [
                    { name: 'Total', type: 'bar', data: [], itemStyle: { color: C.info }, barWidth: '60%' },
                    { name: 'Anomalies', type: 'bar', data: [], itemStyle: { color: C.critical }, barWidth: '60%' }
                ]
            });
        }

        _liveScoresChart = initEChart('live-chart-scores');
        if (_liveScoresChart) {
            _liveScoresChart.setOption({
                tooltip: { trigger: 'axis', backgroundColor: C.tooltipBg, textStyle: { color: C.ink, fontFamily: 'JetBrains Mono', fontSize: 11 } },
                grid: { left: 50, right: 16, top: 30, bottom: 30 },
                legend: { data: ['Normal', 'Attack'], textStyle: { color: C.inkDim, fontSize: 10, fontFamily: 'JetBrains Mono' }, top: 0, right: 16 },
                xAxis: { type: 'category', data: [], axisLabel: { color: C.inkFaint, fontSize: 9, rotate: 30 }, axisLine: { lineStyle: { color: C.gridLine } } },
                yAxis: { type: 'value', axisLabel: { color: C.inkFaint, fontSize: 9 }, splitLine: { lineStyle: { color: C.gridLine } } },
                series: [
                    { name: 'Normal', type: 'bar', stack: 's', data: [], itemStyle: { color: 'rgba(139,147,165,0.4)' }, barWidth: '80%' },
                    { name: 'Attack', type: 'bar', stack: 's', data: [], itemStyle: { color: C.critical }, barWidth: '80%' }
                ]
            });
        }

        _liveUsersChart = initEChart('live-chart-users');
        if (_liveUsersChart) {
            _liveUsersChart.setOption({
                tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: C.tooltipBg, textStyle: { color: C.ink, fontFamily: 'JetBrains Mono', fontSize: 11 } },
                grid: { left: 100, right: 40, top: 8, bottom: 8 },
                xAxis: { type: 'value', axisLabel: { color: C.inkFaint, fontSize: 9 }, splitLine: { lineStyle: { color: C.gridLine } } },
                yAxis: { type: 'category', data: [], axisLabel: { color: C.inkDim, fontSize: 10, fontFamily: 'JetBrains Mono' } },
                series: [{ type: 'bar', data: [], barWidth: '60%', itemStyle: { color: C.ochre }, label: { show: true, position: 'right', color: C.inkDim, fontSize: 10, fontFamily: 'JetBrains Mono' } }]
            });
        }

        _liveAuthDonut = initEChart('live-chart-auth');
        if (_liveAuthDonut) {
            _liveAuthDonut.setOption({
                tooltip: { trigger: 'item', backgroundColor: C.tooltipBg, textStyle: { color: C.ink, fontFamily: 'JetBrains Mono', fontSize: 11 } },
                legend: { orient: 'vertical', right: 10, top: 'center', textStyle: { color: C.inkDim, fontSize: 11, fontFamily: 'JetBrains Mono' } },
                series: [{
                    type: 'pie', radius: ['45%', '70%'], center: ['35%', '50%'],
                    label: { show: false },
                    data: []
                }]
            });
        }
    }

    function updateLiveCharts() {
        if (!_echartsInitialized) initLiveCharts();
        if (!_liveEvents.length) return;

        if (_liveTimelineChart) {
            const buckets = {};
            _liveEvents.forEach(e => {
                const t = e.ts || '';
                const key = t.length > 8 ? t.slice(0, 8) : t.slice(0, 5);
                if (!buckets[key]) buckets[key] = { total: 0, anomalies: 0 };
                buckets[key].total++;
                if (e.decision === 'flag' || e.decision === 'block') buckets[key].anomalies++;
            });
            const keys = Object.keys(buckets).slice(-30);
            _liveTimelineChart.setOption({
                xAxis: { data: keys },
                series: [
                    { name: 'Total', data: keys.map(k => buckets[k].total) },
                    { name: 'Anomalies', data: keys.map(k => buckets[k].anomalies) }
                ]
            });
        }

        if (_liveScoresChart) {
            const bins = 15;
            const scores = _liveEvents.map(e => e.combined_score || 0);
            const maxS = Math.max(...scores, 0.001);
            const binSize = maxS / bins;
            const normal = new Array(bins).fill(0);
            const attack = new Array(bins).fill(0);
            _liveEvents.forEach(e => {
                const bin = Math.min(Math.floor((e.combined_score || 0) / binSize), bins - 1);
                if (e.decision === 'flag' || e.decision === 'block') attack[bin]++;
                else normal[bin]++;
            });
            const labels = Array.from({ length: bins }, (_, i) => (i * binSize).toFixed(3));
            _liveScoresChart.setOption({
                xAxis: { data: labels },
                series: [
                    { name: 'Normal', data: normal },
                    { name: 'Attack', data: attack }
                ]
            });
        }

        if (_liveUsersChart) {
            const userCounts = {};
            _liveEvents.forEach(e => {
                const name = (e.user_id || 'unknown').split('@')[0];
                userCounts[name] = (userCounts[name] || 0) + 1;
            });
            const sorted = Object.entries(userCounts).sort((a, b) => b[1] - a[1]).slice(0, 8).reverse();
            _liveUsersChart.setOption({
                yAxis: { data: sorted.map(s => s[0]) },
                series: [{ data: sorted.map(s => s[1]) }]
            });
        }

        if (_liveAuthDonut) {
            const authCounts = {};
            _liveEvents.forEach(e => {
                const t = e.auth_type || 'Unknown';
                authCounts[t] = (authCounts[t] || 0) + 1;
            });
            const C = getThemeColors();
            const colors = { 'NTLM': C.info, 'Kerberos': C.ochre };
            const authData = Object.entries(authCounts).map(([name, value]) => ({
                name, value,
                itemStyle: { color: colors[name] || C.inkDim }
            }));
            _liveAuthDonut.setOption({ series: [{ data: authData }] });
        }
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

            <div class="insight-box mb-4" id="live-narrative">
                <div style="font-weight:700;color:var(--ink-dim);font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">Live Analysis</div>
                Waiting for login events...
            </div>

            <div class="grid-12 gap-4 mb-4">
                <div class="col-5">
                    <div class="panel p-4">
                        <div class="section-title mb-3">Activity Timeline</div>
                        <div id="live-chart-timeline" style="width:100%;height:240px"></div>
                    </div>
                </div>
                <div class="col-3">
                    <div class="panel p-4">
                        <div class="section-title mb-3">Threat Level</div>
                        <div id="gauge-container" class="text-center"></div>
                        <div class="section-title mb-2 mt-3">Risk Distribution</div>
                        <div id="risk-dist-legend" class="text-12 text-dim" style="margin-top:8px"></div>
                    </div>
                </div>
                <div class="col-4">
                    <div class="panel p-4">
                        <div class="section-header">
                            <div class="section-title">Top Risky Users</div>
                            <a class="view-all" href="#/users">View All &#8594;</a>
                        </div>
                        <div id="top-risky-users"></div>
                    </div>
                </div>
            </div>

            <div class="grid-12 gap-4 mb-4">
                <div class="col-7">
                    <div class="panel overflow-hidden">
                        <div class="flex-between px-4 py-3 hairline">
                            <div class="flex-center gap-2">
                                <span class="section-title">Live Authentication Events</span>
                                <div class="table-controls">
                                    <button class="filter-btn active" id="evt-filter-all" onclick="window._evtFilter='all';window._renderEventsTable()">All</button>
                                    <button class="filter-btn" id="evt-filter-block" onclick="window._evtFilter='block';window._renderEventsTable()">Block</button>
                                    <button class="filter-btn" id="evt-filter-flag" onclick="window._evtFilter='flag';window._renderEventsTable()">Flag</button>
                                </div>
                            </div>
                            <span class="flex-center gap-1 text-10 text-faint uppercase tracking-widest">
                                <span class="live-dot" id="live-indicator"></span>
                                <span id="live-status-text">live</span>
                                <button class="filter-btn" id="pause-btn" onclick="window._togglePause()" style="margin-left:4px;font-size:9px;padding:2px 6px">⏸ Pause</button>
                            </span>
                        </div>
                        <div class="overflow-auto" style="max-height: 360px">
                            <table class="table-glass">
                                <thead><tr>
                                    <th>Time</th><th>User</th><th>Source</th><th>Destination</th><th>Type</th><th>Score</th><th>Decision</th>
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
                <div class="col-5">
                    <div class="panel p-4">
                        <div class="section-title mb-3">Anomaly Score Distribution</div>
                        <div id="live-chart-scores" style="width:100%;height:340px"></div>
                    </div>
                </div>
            </div>

            <div class="grid-12 gap-4 mb-4">
                <div class="col-7">
                    <div class="panel overflow-hidden">
                        <div class="flex-between px-4 py-3 hairline">
                            <span class="section-title">Recent Alerts</span>
                            <div>
                                <span class="text-10 text-faint uppercase tracking-widest" id="alert-count">0 alerts</span>
                                <a class="view-all" href="#/alerts" style="margin-left:12px">View All &#8594;</a>
                            </div>
                        </div>
                        <div class="overflow-auto" style="max-height: 280px">
                            <table class="table-glass">
                                <thead><tr>
                                    <th>Time</th><th>User</th><th>Reason</th><th>Score</th><th>Severity</th>
                                </tr></thead>
                                <tbody id="dash-alerts-tbody"></tbody>
                            </table>
                        </div>
                    </div>
                </div>
                <div class="col-5">
                    <div class="panel p-4">
                        <div class="section-title mb-3">Authentication Methods</div>
                        <div id="live-chart-auth" style="width:100%;height:240px"></div>
                    </div>
                </div>
            </div>`;

        await loadDashboard();
        initLiveCharts();
        updateLiveCharts();
        updateNarrative();
        // Force ECharts to recalculate after layout settles
        requestAnimationFrame(() => {
            _echartsInstances.forEach(c => { try { c.resize(); } catch(e){} });
        });
        setTimeout(() => {
            _echartsInstances.forEach(c => { try { c.resize(); } catch(e){} });
        }, 300);
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

            // Risk distribution legend
            const legendEl = document.getElementById('risk-dist-legend');
            if (legendEl && dash.riskDistribution) {
                const total = dash.riskDistribution.reduce((s, d) => s + d.value, 0) || 1;
                legendEl.innerHTML = dash.riskDistribution.map(d => {
                    const pct = ((d.value / total) * 100).toFixed(1);
                    return '<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">' +
                        '<span style="width:8px;height:8px;border-radius:2px;background:' + d.color + ';flex-shrink:0"></span>' +
                        '<span style="flex:1">' + d.name + '</span>' +
                        '<span class="mono" style="font-weight:600">' + d.value + '</span>' +
                        '<span class="mono text-faint" style="font-size:10px">(' + pct + '%)</span></div>';
                }).join('');
            }

            // Top risky users
            const riskyEl = document.getElementById('top-risky-users');
            if (riskyEl && dash.topRiskyUsers) {
                riskyEl.innerHTML = dash.topRiskyUsers.length
                    ? dash.topRiskyUsers.map(u => topRiskyUserRow(u)).join('')
                    : '<div class="text-12 text-faint py-4 text-center">No risky users yet</div>';
            }

            // Events table
            if (_liveEvents.length) {
                window._renderEventsTable();
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

    /* ── Event table filter + pause ────────────────────────────── */
    window._evtFilter = 'all';
    window._renderEventsTable = function() {
        const tbody = document.getElementById('events-tbody');
        if (!tbody) return;
        let evts = _liveEvents.slice().reverse();
        if (window._evtFilter !== 'all') evts = evts.filter(e => e.decision === window._evtFilter);
        tbody.innerHTML = evts.slice(0, 30).map(e => eventRow(e, openInvestigate)).join('');
        ['all', 'block', 'flag'].forEach(f => {
            const btn = document.getElementById('evt-filter-' + f);
            if (btn) btn.classList.toggle('active', window._evtFilter === f);
        });
    };
    window._togglePause = function() {
        _ssePaused = !_ssePaused;
        const btn = document.getElementById('pause-btn');
        const dot = document.getElementById('live-indicator');
        const txt = document.getElementById('live-status-text');
        if (btn) btn.textContent = _ssePaused ? '▶ Resume' : '⏸ Pause';
        if (dot) dot.style.background = _ssePaused ? 'var(--ochre)' : '';
        if (txt) txt.textContent = _ssePaused ? 'paused' : 'live';
    };

    /* ── DateTime updater ──────────────────────────────────────── */
    function updateDateTime() {
        const el = document.getElementById('topbar-datetime');
        if (el) {
            const now = new Date();
            el.textContent = now.toLocaleTimeString('en-US', { hour12: false }) + '  ' +
                now.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        }
    }

    function updateGreeting() {
        const el = document.getElementById('topbar-greeting');
        if (!el) return;
        const h = new Date().getHours();
        const name = el.textContent.replace(/^(Good morning|Good afternoon|Good evening),?\s*/i, '').replace(/\.$/, '').trim() || 'Analyst';
        const g = h < 12 ? GREETINGS[0] : h < 18 ? GREETINGS[1] : GREETINGS[2];
        el.textContent = g + ', ' + name + '.';
    }

    /* ── Search ─────────────────────────────────────────────────── */
    function initSearch() {
        const input = document.getElementById('global-search');
        const overlay = document.getElementById('search-overlay');
        const modalInput = document.getElementById('search-modal-input');
        const results = document.getElementById('search-results');
        if (!input || !overlay) return;

        function openSearch() {
            overlay.classList.add('open');
            setTimeout(() => modalInput.focus(), 100);
        }
        function closeSearch() {
            overlay.classList.remove('open');
            if (modalInput) modalInput.value = '';
            if (results) results.innerHTML = '<div class="search-result-group">Type to search</div>';
        }

        input.addEventListener('focus', openSearch);
        input.addEventListener('blur', (e) => { if (!overlay.contains(e.relatedTarget)) closeSearch(); });
        overlay.addEventListener('click', (e) => { if (e.target === overlay) closeSearch(); });

        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); openSearch(); }
            if (e.key === 'Escape') closeSearch();
        });

        let searchTimeout;
        if (modalInput) {
            modalInput.addEventListener('input', () => {
                clearTimeout(searchTimeout);
                const q = modalInput.value.trim();
                if (!q) { results.innerHTML = '<div class="search-result-group">Type to search</div>'; return; }
                searchTimeout = setTimeout(async () => {
                    try {
                        const data = await API.search(q);
                        let html = '';
                        if (data.users && data.users.length) {
                            html += '<div class="search-result-group">Users (' + data.users.length + ')</div>';
                            data.users.forEach(u => {
                                html += '<div class="search-result-item" onclick="location.hash=\'#/users\';document.getElementById(\'search-overlay\').classList.remove(\'open\')">' +
                                    '<span class="mono">' + esc(u.name || u.user_id) + '</span> — ' + esc(u.persona) +
                                    ' <span class="text-faint">(' + u.live_events + ' events, max ' + u.max_score.toFixed(3) + ')</span></div>';
                            });
                        }
                        if (data.events && data.events.length) {
                            html += '<div class="search-result-group">Events (' + data.events.length + ')</div>';
                            data.events.slice(0, 10).forEach(ev => {
                                html += '<div class="search-result-item">' +
                                    '<span class="mono">' + esc(ev.ts) + '</span> ' + esc(ev.name || ev.user_id) +
                                    ' <span class="text-faint">' + esc(ev.src_computer) + ' → ' + esc(ev.dst_computer) + '</span> ' +
                                    '<span class="mono">' + ev.combined_score.toFixed(4) + '</span> ' +
                                    '<span class="stamp stamp-' + (ev.decision === 'block' ? 'critical' : ev.decision === 'flag' ? 'medium' : 'low') + '">' + esc(ev.decision) + '</span></div>';
                            });
                        }
                        if (data.alerts && data.alerts.length) {
                            html += '<div class="search-result-group">Alerts (' + data.alerts.length + ')</div>';
                            data.alerts.slice(0, 10).forEach(a => {
                                html += '<div class="search-result-item">' +
                                    '<span class="mono">' + esc(a.timestamp) + '</span> ' + esc(a.name || a.user_id) +
                                    ' <span class="stamp stamp-' + a.severity + '">' + esc(a.severity) + '</span></div>';
                            });
                        }
                        if (!html) html = '<div class="search-result-group">No results for "' + esc(q) + '"</div>';
                        results.innerHTML = html;
                    } catch (err) { results.innerHTML = '<div class="search-result-group">Search failed</div>'; }
                }, 200);
            });
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
                    // Update narrative
                    updateNarrative();
                    updateGreeting();
                    // Update ECharts
                    updateLiveCharts();
                    // Update events table
                    window._renderEventsTable();
                }
            },
            onError() {
                const dot = document.getElementById('health-dot');
                if (dot) dot.classList.add('err');
            }
        });
    }


    /* Behavior Insights page */
    async function renderBehaviorInsights() {
        destroyCharts();
        setActiveNav('behavior');
        content.innerHTML = '<div class="text-12 text-dim py-8">Loading behavior insights...</div>';
        try {
            const users = await API.knownUsers();
            const profiles = [];
            for (const u of users.slice(0, 8)) {
                try { profiles.push(await API.userProfile(u.user_id)); } catch(e) { profiles.push({ user_id: u.user_id, baseline: {}, session: {} }); }
            }
            let html = '<div class="dash-greeting"><h2>Behavior Insights</h2><p>Per-user behavioral baselines derived from 6 months of LANL training data.</p></div>';
            profiles.forEach(p => {
                const b = p.baseline || {};
                const s = p.session || {};
                const name = (p.user_id || 'unknown').split('@')[0];
                const maxHour = Math.max(...(b.hourlyPattern || []), 1);
                const hourlyBars = (b.hourlyPattern || []).map((v, i) => {
                    const h = Math.max(2, (v / maxHour) * 40);
                    const color = (b.rareHours || []).includes(i) ? 'var(--critical)' : 'var(--info)';
                    return '<div title="' + i + ':00" style="width:100%;height:' + h + 'px;background:' + color + ';border-radius:1px"></div>';
                }).join('');
                html += '<div class="panel p-4 mb-4"><div class="section-header"><div class="section-title">' + esc(name) + '</div>' +
                    '<span class="mono text-11 text-faint">' + esc(p.user_id) + '</span></div>' +
                    '<div class="grid-3 gap-4">' +
                    '<div><div class="text-12 text-dim">Events: <strong>' + (b.totalEvents || 0).toLocaleString() + '</strong></div>' +
                    '<div class="text-12 text-dim">Typical Pairs: <strong>' + (b.typicalPairs || 0) + '</strong></div>' +
                    '<div class="text-12 text-dim">Avg IAT: <strong>' + (b.avgIAT ? b.avgIAT.toFixed(0) + 's' : 'N/A') + '</strong></div></div>' +
                    '<div><div class="text-12 text-dim">Sources: <strong>' + (b.knownSrcComputers || []).length + '</strong></div>' +
                    '<div class="text-12 text-dim">Destinations: <strong>' + (b.knownDstComputers || []).length + '</strong></div>' +
                    '<div class="text-12 text-dim">Rare Hours: <strong style="color:var(--critical)">' + (b.rareHours || []).length + '</strong></div></div>' +
                    '<div><div class="text-12 text-dim">Events: <strong>' + (s.totalEvents || 0) + '</strong></div>' +
                    '<div class="text-12 text-dim">Flags: <strong style="color:' + (s.flags > 0 ? 'var(--critical)' : 'inherit') + '">' + (s.flags || 0) + '</strong></div>' +
                    '<div class="text-12 text-dim">Max Score: <strong>' + (s.maxScore || 0).toFixed(4) + '</strong></div></div>' +
                    '</div>' +
                    '<div style="margin-top:12px"><div class="text-10 text-dim" style="margin-bottom:4px">Hourly Activity</div>' +
                    '<div style="display:flex;align-items:flex-end;gap:1px;height:44px">' + hourlyBars + '</div>' +
                    '<div class="flex-between text-9 text-faint" style="margin-top:2px"><span>0:00</span><span>6:00</span><span>12:00</span><span>18:00</span><span>23:00</span></div></div>' +
                    '</div>';
            });
            content.innerHTML = html;
        } catch (err) { content.innerHTML = '<div class="text-12 text-critical py-8">Failed to load behavior insights</div>'; }
    }

    /* Model Performance page */
    function renderModelPerformance() {
        destroyCharts();
        setActiveNav('model');
        const fi = [
            { n: 'vel_1h', v: 6133 }, { n: 'hour_ratio', v: 5994 }, { n: 'hour_cos', v: 5811 },
            { n: 'hour_sin', v: 5500 }, { n: 'dst_prior_events', v: 4339 }, { n: 'iat_zscore', v: 3114 },
            { n: 'machine_popularity', v: 3000 }, { n: 'velocity_ratio', v: 2998 },
            { n: 'pairs_last_100', v: 2572 }, { n: 'pair_freq_ratio', v: 1414 },
            { n: 'fail_rate', v: 1090 }, { n: 'fail_1h', v: 632 },
            { n: 'lstm_ae_recon_error', v: 350 }, { n: 'log_pair_rank', v: 475 },
            { n: 'pair_first', v: 179 }, { n: 'is_ntlm', v: 171 },
            { n: 'src_first', v: 64 }, { n: 'src_dst_pair_first', v: 48 },
            { n: 'dst_first', v: 44 }, { n: 'is_rare_hour', v: 13 },
            { n: 'dst_first_x_ntlm', v: 6 }
        ];
        const mx = Math.max(...fi.map(f => f.v));
        const bars = fi.sort((a,b) => b.v - a.v).map(f =>
            '<div class="feature-bar-row"><div class="feature-bar-label">' + f.n + '</div>' +
            '<div class="feature-bar-track"><div class="feature-bar-fill" style="width:' + ((f.v/mx)*100) + '%"></div></div>' +
            '<div class="feature-bar-val">' + f.v.toLocaleString() + '</div></div>'
        ).join('');
        content.innerHTML = '<div class="dash-greeting"><h2>Model Performance</h2><p>LGB-21 ensemble \u2014 LightGBM + LSTM Autoencoder.</p></div>' +
            '<div class="grid-3 gap-4 mb-4">'+
            '<div class="insight-card"><h4>ROC-AUC</h4><div class="tape-num" style="color:var(--low)">0.9999</div></div>'+
            '<div class="insight-card"><h4>F1 Score</h4><div class="tape-num" style="color:var(--info)">0.4866</div></div>'+
            '<div class="insight-card"><h4>Threshold</h4><div class="tape-num" style="color:var(--ochre)">0.1872</div></div></div>'+
            '<div class="grid-2 gap-4 mb-4">'+
            '<div class="insight-card"><h4>Detection Performance</h4>'+
            '<div class="grid-2 gap-4" style="margin-top:8px">'+
            '<div><div class="text-12 text-dim">True Positives</div><div class="tape-num" style="font-size:1.4rem;color:var(--low)">136 <span class="text-11 text-faint">/ 240</span></div><div class="text-10 text-faint">56.7% recall</div></div>'+
            '<div><div class="text-12 text-dim">False Positives</div><div class="tape-num" style="font-size:1.4rem;color:var(--ochre)">183 <span class="text-11 text-faint">/ 5.4M</span></div><div class="text-10 text-faint">0.003% FPR</div></div></div></div>'+
            '<div class="insight-card"><h4>Architecture</h4>'+
            '<div class="text-12 text-dim" style="margin-top:8px">LightGBM (21 features) + LSTM-AE recon error<br>GroupShuffleSplit, spw=3<br>29.9M total events scored</div></div></div>'+
            '<div class="grid-2 gap-4 mb-4">'+
            '<div class="insight-card"><h4>Feature Importance</h4>' + bars + '</div>'+
            '<div class="insight-card"><h4>Run Comparison</h4>'+
            '<table class="table-glass" style="margin-top:8px"><thead><tr><th>Run</th><th>Config</th><th>F1</th><th>TP</th><th>FP</th></tr></thead><tbody>'+
            '<tr><td>7</td><td>LGB-20feat</td><td>0.4817</td><td>145</td><td>217</td></tr>'+
            '<tr><td>8</td><td>LSTM-AE solo</td><td>0.0095</td><td>118</td><td>24,482</td></tr>'+
            '<tr style="background:var(--surface-2)"><td><strong>9</strong></td><td><strong>LGB-21feat</strong></td><td><strong>0.4866</strong></td><td><strong>136</strong></td><td><strong>183</strong></td></tr>'+
            '<tr><td>10</td><td>LGB-37feat</td><td>0.4772</td><td>157</td><td>261</td></tr>'+
            '<tr><td>11</td><td>LGB-23feat v2</td><td>0.4735</td><td>143</td><td>221</td></tr>'+
            '</tbody></table></div></div>';
    }
    /* ── Route dispatcher ───────────────────────────────────────── */
    function route() {
        const page = getPage();
        switch (page) {
            case 'dashboard': renderDashboard(); break;
            case 'alerts': renderAlerts(); break;
            case 'users': renderUsers(); break;
            case 'settings': renderSettings(); break;
            case 'behavior': renderBehaviorInsights(); break;
            case 'model': renderModelPerformance(); break;
            default: renderDashboard(); break;
        }
    }

    /* ── Init ───────────────────────────────────────────────────── */
    function init() {
        initTheme();
        initSearch();
        updateDateTime();
        setInterval(updateDateTime, 1000);
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
