/* UI components — badges, KPI cards, rows, drawer, hold button */

const _displayNames = { ace: 'Ace', luffy: 'Luffy', igris: 'Igris', ashborn: 'Ashborn' };
function _fmtUser(name, userId) {
    const display = _displayNames[name] || name || 'unknown';
    const id = (userId || '').split('@')[0];
    return id ? display + ' (' + id + ')' : display;
}

/* Raw LANL ids for the four demo personas. Same names and same "Name (ShortId)"
   format as the _dn map on Dataset Analysis, so a viewer can cross-reference
   the two pages. Unknown ids fall back to the short id. */
const _personaNames = {
    'U293@DOM1': 'Ace (U293)',
    'U2097@DOM1': 'Igris (U2097)',
    'U2899@DOM1': 'Luffy (U2899)',
    'U66@DOM1': 'Ashborn (U66)',
};
function humanizeUser(id) {
    if (!id) return id;
    return _personaNames[id] || String(id).split('@')[0];
}

/* Normal scores are probabilities around 1e-8; six decimals rendered every one
   of them as 0.000000. Keep small values readable without inventing precision
   the model does not have. */
function formatScore(v) {
    if (v === null || v === undefined || v === '') return '—';
    const n = Number(v);
    if (!isFinite(n)) return '—';
    const a = Math.abs(n);
    if (a === 0) return '0.000';
    if (a >= 0.01) return n.toFixed(4);
    if (a >= 1e-6) return n.toFixed(6);
    return n.toExponential(2);
}

function formatFeatureValue(v) {
    const n = Number(v);
    if (!isFinite(n)) return String(v);
    if (n === 0) return '0';
    if (Math.abs(n) < 1e-4) return n.toExponential(2);
    if (Math.abs(n) < 1) return n.toFixed(4);
    return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/* `level` here encodes the detection OUTCOME, not the score. Colour follows the
   dashboard KPI semantics: caught = green, false positive = amber, high = red. */
function severityBadge(level) {
    const outcome = {
        critical: { label: 'CAUGHT', cls: 'low' },
        medium: { label: 'FALSE POS', cls: 'medium' },
        high: { label: 'HIGH', cls: 'critical' }
    };
    const hit = outcome[level];
    const cls = 'stamp stamp-' + (hit ? hit.cls : (level || 'info'));
    const label = hit ? hit.label : (level ? String(level).toUpperCase() : 'INFO');
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
        <div class="panel panel-hover p-3" data-kpi="${cfg.key}">
            <div class="kpi-card">
                <div class="kpi-icon" style="width:36px;height:36px;border-radius:6px;background:${bg};color:${c};display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0">${cfg.icon}</div>
                <div class="kpi-card-body">
                    <div class="kpi-label mb-1">${cfg.label}</div>
                    <div style="display:flex;align-items:baseline;gap:6px">
                        <div class="tape-num" style="color:${c}">${value != null ? value : '<span class="skeleton"></span>'}</div>
                        ${deltaHtml}
                    </div>
                </div>
                ${sparkId ? `<div class="kpi-card-spark" id="${sparkId}"></div>` : ''}
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
                    <span class="mono text-11">${formatScore(e.combined_score)}</span>
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
            <td class="font-semibold" title="${esc(a.name)}">${esc(humanizeUser(a.name))}</td>
            <td>${esc(a.reasons)}</td>
            <td class="mono text-11">${formatScore(a.combined_score)}</td>
            <td>${severityBadge(sev)}</td>
            <td>
                <div class="flex gap-1">
                    <button class="btn-ochre" onclick="event.stopPropagation();(${onInvestigate || 'function(){}'})(${a.id})">investigate</button>
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
    const display = humanizeUser(u.user_id);
    const missed = (u.attacks || 0) - (u.attacks_caught || 0);
    return `
        <tr class="clickable" data-uid="${uid}">
            <td class="font-semibold mono" title="${uid}">${esc(display)}</td>
            <td><span class="stamp ${personaCls}">${esc(personaLabel)}</span></td>
            <td class="mono">${u.live_events}</td>
            <td class="mono" style="color:${u.attacks ? 'var(--critical)' : 'inherit'}">${u.attacks || 0}</td>
            <td class="mono" style="color:var(--low)">${u.attacks_caught || 0}</td>
            <td class="mono" style="color:${missed ? 'var(--ochre)' : 'inherit'}">${missed}</td>
            <td class="mono" style="color:${u.false_positives ? 'var(--ochre)' : 'inherit'}">${u.false_positives || 0}</td>
            <td class="mono">${formatScore(u.max_score)}</td>
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

    // "Several behavioral indicators" is only true when there is at least one
    // to point at. Replay events carry no per-event feature vector, so
    // devPoints is 0 for them, and the old text asserted a deviation the panel
    // could not show. Say only what is actually known.
    const indicatorCount = data.devPoints || 0;
    const whatThisMeans = indicatorCount > 0
        ? (data.severity === 'critical'
            ? `This login was blocked on ${indicatorCount} behavioral indicator${indicatorCount === 1 ? '' : 's'} that deviate from the user's training baseline. The pattern is consistent with unauthorized access or a compromised account.`
            : `This login was flagged on ${indicatorCount} behavioral indicator${indicatorCount === 1 ? '' : 's'} that do not match the user's normal pattern. A security analyst should review this event.`)
        : data.isRed
        ? 'This is a confirmed red-team event from the LANL dataset. Every replayed event carries its ground-truth label, so the outcome badge above is the dataset label rather than a model confidence.'
        : data.severity === 'critical'
        ? 'The model blocked this login on its overall score. No per-feature breakdown is recorded for replayed events, so use the baseline and timeline to the right to judge it.'
        : 'This event scored above normal, but no per-feature breakdown is recorded for replayed events. Check the baseline and timeline to the right.';

    const overlay = document.createElement('div');
    overlay.className = 'drawer-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Event investigation details');
    overlay.innerHTML = `
        <div class="drawer">
            <div class="drawer-header">
                <div>
                    <div class="font-bold text-lg">${esc(data.displayName)}</div>
                    <div class="text-11 text-faint mt-05">${esc(data.rawId)} · ${esc(data.src_computer)} → ${esc(data.dst_computer)}</div>
                </div>
                <button class="drawer-close" id="drawer-close-btn" type="button" aria-label="Close investigation details">&times;</button>
            </div>

            <div class="flex gap-4">
                <div>
                    <div class="drawer-score" style="color:${barColor}">${formatScore(data.combinedScore)}</div>
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
                    Total events: ${data.baseline.totalEvents} · Machines used: ${data.baseline.knownSrcComputers} source / ${data.baseline.knownDstComputers} destination
                </div>
            </div>

            ${timelineHtml ? `
                <div>
                    <div class="drawer-section-title">Recent Timeline</div>
                    ${timelineHtml}
                </div>` : ''}
        </div>`;

    const lastFocused = document.activeElement;
    function closeDrawer() {
        overlay.classList.remove('open');
        document.removeEventListener('keydown', onKey);
        setTimeout(() => overlay.remove(), 250);
        if (lastFocused && lastFocused.focus) lastFocused.focus();
        if (onClose) onClose();
    }
    function onKey(event) {
        if (event.key === 'Escape') closeDrawer();
    }

    overlay.querySelector('#drawer-close-btn').addEventListener('click', closeDrawer);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeDrawer();
    });
    document.addEventListener('keydown', onKey);

    document.body.appendChild(overlay);
    requestAnimationFrame(() => {
        overlay.classList.add('open');
        overlay.querySelector('#drawer-close-btn').focus();
    });
}

function liveEventDrawer(e) {
    const existing = document.querySelector('.drawer-overlay');
    if (existing) existing.remove();

    const dec = String(e.decision || 'allow').toLowerCase();
    const col = dec === 'block' ? 'var(--critical)' : dec === 'flag' ? 'var(--medium)' : 'var(--low)';
    const decCls = dec === 'block' ? 'stamp-critical' : dec === 'flag' ? 'stamp-medium' : 'stamp-low';
    const b = e.baseline || {};
    const f = e.features || {};
    const coldMin = Number(b.cold_start_min || 20);
    const isNew = b.history_events !== undefined && Number(b.history_events) < coldMin;
    const pctNum = (v) => (v === undefined || v === null || !isFinite(Number(v)))
        ? null : Math.max(0, Math.min(100, Number(v)));
    const velPct = pctNum(b.vel_pct);
    const lstmPct = pctNum(b.lstm_pct);
    const maybe = (v) => (v === undefined || v === null) ? '—' : formatFeatureValue(v);

    const pctBar = (label, pct, detail) => pct === null ? '' : `
        <div class="pct-block">
            <div class="pct-head"><span>${esc(label)}</span><span class="mono">p${pct.toFixed(1)}</span></div>
            <div class="pct-track"><div class="pct-fill" style="width:${pct}%;background:${
                pct >= 99 ? 'var(--critical)' : pct >= 95 ? 'var(--ochre)' : 'var(--info)'}"></div></div>
            ${detail ? `<div class="pct-detail">${esc(detail)}</div>` : ''}
        </div>`;

    const velDetail = (b.vel_median !== undefined && b.vel_median !== null)
        ? `this event ${maybe(f.vel_1h)}/hr · median ${Math.round(b.vel_median)} · p99 ${Math.round(b.vel_p99)}`
        : '';
    const lstmDetail = (b.lstm_p99 !== undefined && b.lstm_p99 !== null)
        ? `this event ${maybe(f.lstm_ae_recon_error)} · p99 ${Number(b.lstm_p99).toExponential(2)}`
        : '';

    const featureRows = Object.keys(f).map(k => {
        const tail = (k === 'vel_1h' && velPct !== null && velPct >= 99)
            || (k === 'lstm_ae_recon_error' && lstmPct !== null && lstmPct >= 99)
            || ((k === 'dst_first' || k === 'src_first' || k === 'is_rare_hour' || k === 'fail_1h')
                && Number(f[k]) > 0);
        return `<div class="live-feature${tail ? ' tail' : ''}"><span class="k">${esc(k)}</span><span class="v">${esc(formatFeatureValue(f[k]))}</span></div>`;
    }).join('');

    const baselineSummary = (b.history_events !== undefined && b.history_events !== null)
        ? `${Number(b.history_events).toLocaleString()} prior events in the dataset`
        : 'No baseline available';

    const overlay = document.createElement('div');
    overlay.className = 'drawer-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Live event details');
    overlay.innerHTML = `
        <div class="drawer">
            <div class="drawer-header">
                <div>
                    <div class="font-bold text-lg">${esc(humanizeUser(e.user_id))}</div>
                    <div class="text-11 text-faint mt-05">${esc(e.user_id)} · ${esc(e.src_computer)} → ${esc(e.dst_computer)} · ${esc((!e.auth_type || e.auth_type === '?') ? 'Unknown' : e.auth_type)}</div>
                </div>
                <button class="drawer-close" id="live-drawer-close" type="button" aria-label="Close live event details">&times;</button>
            </div>

            <div class="flex gap-4">
                <div>
                    <div class="drawer-score" style="color:${col}">${formatScore(e.combined_score)}</div>
                    <div class="text-10 text-faint uppercase tracking-wider">model score</div>
                </div>
                <div>
                    <span class="stamp ${decCls}">${esc(dec.toUpperCase())}</span>
                    <div class="text-10 text-faint mt-05">${e.simulated ? 'Live employee sign-in' : 'Live event'}</div>
                </div>
            </div>

            ${isNew ? `
            <div class="panel-inset p-3" style="border-color:rgba(232,163,61,.45)">
                <div class="drawer-section-title">Cold start</div>
                <div class="text-12 text-dim">This user has ${Number(b.history_events).toLocaleString()} prior events, below the ${coldMin}-event baseline floor. A user-relative explanation is not trustworthy yet.</div>
            </div>` : ''}

            <div class="panel-inset p-3">
                <div class="drawer-section-title">Why this decision</div>
                <div class="text-12 text-dim">${esc(e.reasons || 'No explanation recorded.')}</div>
            </div>

            <div class="panel-inset p-3">
                <div class="drawer-section-title">Baseline</div>
                <div class="text-11 text-dim" style="margin-bottom:10px">${esc(baselineSummary)}</div>
                ${pctBar('Hourly volume percentile', velPct, velDetail)}
                ${pctBar('Sequence-error percentile', lstmPct, lstmDetail)}
            </div>

            <div>
                <div class="drawer-section-title">Feature values</div>
                <div class="live-feature-grid">${featureRows}</div>
            </div>

            <div class="text-10 text-faint">Scored ${esc(e.ts)}. Feature values come from this user's LANL history; only the clock is synthetic.</div>
        </div>`;

    const lastFocused = document.activeElement;
    function closeDrawer() {
        overlay.classList.remove('open');
        document.removeEventListener('keydown', onKey);
        setTimeout(() => overlay.remove(), 250);
        if (lastFocused && lastFocused.focus) lastFocused.focus();
    }
    function onKey(event) {
        if (event.key === 'Escape') closeDrawer();
    }

    overlay.querySelector('#live-drawer-close').addEventListener('click', closeDrawer);
    overlay.addEventListener('click', (ev) => {
        if (ev.target === overlay) closeDrawer();
    });
    document.addEventListener('keydown', onKey);

    document.body.appendChild(overlay);
    requestAnimationFrame(() => {
        overlay.classList.add('open');
        overlay.querySelector('#live-drawer-close').focus();
    });
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
            <div class="risky-user-score" style="color:${sevColor}">${formatScore(score)} <span style="color:var(--ink-faint);font-weight:400">(${severity})</span></div>
        </div>`;
}
