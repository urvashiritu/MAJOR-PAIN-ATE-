/* UI components — badges, KPI cards, rows, drawer, hold button */

const _displayNames = { ace: 'Ace', luffy: 'Luffy', igris: 'Igris', ashborn: 'Ashborn' };
function _fmtUser(name, userId) {
    const display = _displayNames[name] || name || 'unknown';
    const id = (userId || '').split('@')[0];
    return id ? display + ' (' + id + ')' : display;
}

function severityBadge(level) {
    const cls = 'stamp stamp-' + (level || 'info');
    const label = level ? level.toUpperCase() : 'INFO';
    return `<span class="${cls}">${label}</span>`;
}

function kpiCard(cfg, value, sparkId, delta) {
    const colorMap = { info: 'var(--info)', critical: 'var(--critical)', low: 'var(--low)', medium: 'var(--medium)', ochre: 'var(--ochre)' };
    const bgColorMap = { info: 'rgba(110,168,232,0.12)', critical: 'rgba(229,72,77,0.12)', low: 'rgba(87,176,108,0.12)', medium: 'rgba(232,163,61,0.12)', ochre: 'rgba(232,163,61,0.12)' };
    const c = colorMap[cfg.color] || cfg.color || 'var(--ink)';
    const bg = bgColorMap[cfg.color] || 'var(--surface-2)';
    let deltaHtml = '';
    if (delta !== undefined && delta !== null && delta !== 0) {
        const sign = delta > 0 ? '+' : '';
        const cls = delta > 0 ? 'up' : 'down';
        deltaHtml = `<span class="kpi-delta ${cls}">${sign}${delta}</span>`;
    } else if (delta === 0) {
        deltaHtml = `<span class="kpi-delta flat">0%</span>`;
    }
    return `
        <div class="panel panel-hover p-3">
            <div class="kpi-card">
                <div style="width:36px;height:36px;border-radius:6px;background:${bg};display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0">${cfg.icon}</div>
                <div class="kpi-card-body">
                    <div class="kpi-label mb-1">${cfg.label}</div>
                    <div style="display:flex;align-items:baseline;gap:6px">
                        <div class="tape-num" style="color:${c}">${value != null ? value : '<span class="skeleton"></span>'}</div>
                        ${deltaHtml}
                    </div>
                </div>
                <div class="kpi-card-spark" id="${sparkId || ''}"></div>
            </div>
        </div>`;
}

function eventRow(e, onClick) {
    const dec = (e.decision || 'allow').toLowerCase();
    const decCls = 'stamp stamp-' + (dec === 'block' ? 'critical' : dec === 'flag' ? 'medium' : 'low');
    const scorePct = Math.min(100, e.combined_score * 100);
    const barColor = dec === 'block' ? 'var(--critical)' : dec === 'flag' ? 'var(--medium)' : 'var(--low)';
    const rowCls = dec === 'block' ? 'style="background: rgba(229,72,77,0.04)"' : '';
    return `
        <tr class="clickable" ${rowCls} onclick="(${onClick || 'function(){}'})(${e.id})">
            <td class="nowrap">${esc(e.ts)}</td>
            <td class="font-semibold">${esc(e.name)}</td>
            <td>${esc(e.src_computer)}</td>
            <td>${esc(e.dst_computer)}</td>
            <td class="nowrap">${esc(e.auth_type)}</td>
            <td>
                <span class="score-inline">
                    <span class="score-inline-bar"><span class="score-inline-fill" style="width:${scorePct}%;background:${barColor}"></span></span>
                    <span class="mono text-11">${e.combined_score.toFixed(4)}</span>
                </span>
            </td>
            <td><span class="${decCls}">${esc(e.decision)}</span></td>
        </tr>`;
}

function alertRow(a, onInvestigate, onAck) {
    const sev = a.severity || 'medium';
    return `
        <tr>
            <td class="nowrap">${esc(a.timestamp)}</td>
            <td class="font-semibold">${esc(a.name)}</td>
            <td>${esc(a.reasons)}</td>
            <td class="mono text-11">${a.combined_score.toFixed(4)}</td>
            <td>${severityBadge(sev)}</td>
            <td>
                <div class="flex gap-1">
                    <button class="btn-ochre" onclick="event.stopPropagation();(${onInvestigate || 'function(){}'})(${a.eventId})">investigate</button>
                    ${a.status !== 'acknowledged'
                        ? `<button class="btn-muted" onclick="event.stopPropagation();(${onAck || 'function(){}'})(${a.id})">ack</button>`
                        : `<span class="text-10 text-faint uppercase">acked</span>`}
                </div>
            </td>
        </tr>`;
}

function userRow(u, onClick) {
    const personaCls = u.persona === 'attacker' ? 'stamp-critical'
        : (u.persona === 'attacker_missed' ? 'stamp-info'
        : (u.persona === 'normal' ? 'stamp-low' : 'stamp-info'));
    const personaLabel = u.persona === 'attacker_missed' ? 'ATTACKER (MISSED)'
        : (u.persona === 'flagged' ? 'FLAGGED' : u.persona);
    const uid = esc(u.user_id);
    const missed = (u.attacks || 0) - (u.attacks_caught || 0);
    return `
        <tr class="clickable" data-uid="${uid}">
            <td class="font-semibold mono">${esc(u.name)}</td>
            <td><span class="stamp ${personaCls}">${esc(personaLabel)}</span></td>
            <td class="mono">${u.live_events}</td>
            <td class="mono" style="color:${u.attacks ? 'var(--critical)' : 'inherit'}">${u.attacks || 0}</td>
            <td class="mono" style="color:var(--low)">${u.attacks_caught || 0}</td>
            <td class="mono" style="color:${missed ? 'var(--ochre)' : 'inherit'}">${missed}</td>
            <td class="mono" style="color:${u.false_positives ? 'var(--ochre)' : 'inherit'}">${u.false_positives || 0}</td>
            <td class="mono">${Number(u.max_score).toFixed(6)}</td>
        </tr>`;
}

function investigationDrawer(data, onClose) {
    const existing = document.querySelector('.drawer-overlay');
    if (existing) existing.remove();

    const scorePct = Math.min(100, data.combinedScore * 100);
    const barColor = data.severity === 'critical' ? 'var(--critical)' : data.severity === 'high' ? 'var(--high)' : 'var(--ochre)';

    const featuresHtml = (data.featureContributions || []).map(f => `
        <div class="feature-row">
            <span class="feature-name">${esc(f.feature)}</span>
            <div class="feature-bar-bg">
                <div class="feature-bar" style="width:${Math.min(100, f.value * 50)}%;background:${f.color}"></div>
            </div>
            <span class="feature-value">${typeof f.value === 'number' ? f.value.toFixed(4) : esc(f.value)}</span>
        </div>
    `).join('');

    const timelineHtml = (data.timeline || []).map(t => {
        const dotColor = t.severity === 'critical' ? 'var(--critical)' : t.severity === 'high' ? 'var(--high)' : 'var(--low)';
        return `
            <div class="timeline-row">
                <span class="timeline-dot" style="background:${dotColor}"></span>
                <span class="flex-1">${esc(t.event)}</span>
                <span class="mono text-11">${t.score ? t.score.toFixed(4) : ''}</span>
                <span class="text-10 text-faint">${esc(t.time)}</span>
            </div>`;
    }).join('');

    const whatThisMeans = data.severity === 'critical'
        ? 'This login was blocked because the user\'s behavior deviated significantly from their training baseline. The model detected patterns consistent with potential unauthorized access or a compromised account.'
        : data.severity === 'high'
        ? 'This login was flagged because several behavioral indicators don\'t match the user\'s normal pattern. A security analyst should review this event.'
        : 'This event scored above normal but may be benign. The model flagged it for monitoring purposes.';

    const overlay = document.createElement('div');
    overlay.className = 'drawer-overlay';
    overlay.innerHTML = `
        <div class="drawer">
            <div class="drawer-header">
                <div>
                    <div class="font-bold text-lg">${esc(data.displayName)}</div>
                    <div class="text-11 text-faint mt-05">${esc(data.rawId)} · ${esc(data.src_computer)} → ${esc(data.dst_computer)}</div>
                </div>
                <button class="drawer-close" id="drawer-close-btn">&times;</button>
            </div>

            <div class="flex gap-4">
                <div>
                    <div class="drawer-score" style="color:${barColor}">${data.combinedScore.toFixed(4)}</div>
                    <div class="text-10 text-faint uppercase tracking-wider">combined score</div>
                </div>
                <div>
                    ${severityBadge(data.severity)}
                    <div class="text-10 text-faint mt-05">${data.devPoints} deviation points</div>
                </div>
            </div>

            <div class="panel-inset p-3">
                <div class="drawer-section-title">Deviation Reasons</div>
                <div class="text-12 text-dim">${esc(data.devReasons)}</div>
            </div>

            <div class="panel-inset p-3">
                <div class="drawer-section-title">What This Means</div>
                <div class="text-12 text-dim">${esc(whatThisMeans)}</div>
            </div>

            ${featuresHtml ? `
                <div>
                    <div class="drawer-section-title">Feature Contributions</div>
                    <div class="space-y-15">${featuresHtml}</div>
                </div>` : ''}

            <div class="panel-inset p-3">
                <div class="drawer-section-title">Baseline</div>
                <div class="text-11 text-dim">
                    Total events: ${data.baseline.totalEvents} · Failure rate: ${data.baseline.failureRate} · Avg events/hr: ${data.baseline.avgEventsPerHour}
                </div>
            </div>

            ${timelineHtml ? `
                <div>
                    <div class="drawer-section-title">Recent Timeline</div>
                    ${timelineHtml}
                </div>` : ''}
        </div>`;

    overlay.querySelector('#drawer-close-btn').addEventListener('click', () => {
        overlay.classList.remove('open');
        setTimeout(() => overlay.remove(), 250);
        if (onClose) onClose();
    });
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            overlay.classList.remove('open');
            setTimeout(() => overlay.remove(), 250);
            if (onClose) onClose();
        }
    });

    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('open'));
}

function holdButton(label, duration, onDone) {
    const btn = document.createElement('button');
    btn.className = 'hold-btn';
    btn.innerHTML = `<span class="hold-btn-fill" id="hold-fill"></span><span style="position:relative">${esc(label)}</span>`;
    let timer = null;
    let start = 0;

    function startHold(e) {
        e.preventDefault();
        start = Date.now();
        const fill = btn.querySelector('.hold-btn-fill');
        fill.style.transition = `transform ${duration}ms linear`;
        requestAnimationFrame(() => { fill.style.transform = 'scaleX(1)'; });
        timer = setTimeout(() => {
            btn.innerHTML = `<span class="text-low font-semibold">done</span>`;
            if (onDone) onDone();
        }, duration);
    }

    function cancelHold() {
        if (timer) { clearTimeout(timer); timer = null; }
        const fill = btn.querySelector('.hold-btn-fill');
        if (fill) { fill.style.transition = 'none'; fill.style.transform = 'scaleX(0)'; }
    }

    btn.addEventListener('mousedown', startHold);
    btn.addEventListener('mouseup', cancelHold);
    btn.addEventListener('mouseleave', cancelHold);
    btn.addEventListener('touchstart', startHold, { passive: false });
    btn.addEventListener('touchend', cancelHold);
    btn.addEventListener('touchcancel', cancelHold);
    return btn;
}

function esc(s) {
    if (s == null) return '';
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
}

function topRiskyUserRow(u) {
    const score = u.max_score || 0;
    const pct = Math.min(100, score * 100);
    const severity = score > 0.5 ? 'High' : score > 0.2 ? 'Med' : 'Low';
    const sevColor = score > 0.5 ? 'var(--critical)' : score > 0.2 ? 'var(--ochre)' : 'var(--low)';
    const name = _fmtUser(u.name, u.user_id);
    const initials = name.slice(0, 2).toUpperCase();
    const avatarBg = score > 0.5 ? 'var(--critical)' : score > 0.2 ? 'var(--ochre)' : 'var(--info)';
    return `
        <div class="risky-user-item">
            <div class="risky-avatar" style="background:${avatarBg}">${initials}</div>
            <div class="risky-user-info">
                <div class="risky-user-name">${esc(u.name || name)}</div>
                <div class="risky-score-bar"><div class="risky-score-fill" style="width:${pct}%;background:${sevColor}"></div></div>
            </div>
            <div class="risky-user-score" style="color:${sevColor}">${score.toFixed(3)} <span style="color:var(--ink-faint);font-weight:400">(${severity})</span></div>
        </div>`;
}
