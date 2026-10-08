"""Flask backend for LANL anomaly detection — live dashboard + dataset analysis."""
import json
import os
import queue
import secrets
import sys
import threading
import time
from collections import Counter, deque

import joblib
from flask import (Flask, Response, jsonify, send_from_directory, render_template,
                   request, redirect, url_for, session)
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from db import SCORES_PARQUET, FEATURE_COLS
from auth import authenticate, USERS, get_current_code, get_totp_secret, get_totp_remaining
from scorer import init as scorer_init, score_event, THRESHOLD, DEMO_USERS, MODEL_PATH
import scorer as _scorer
import replay as _replay

app = Flask(__name__,
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
            static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.secret_key = secrets.token_hex(32)

# ── Live session state ──────────────────────────────────────────
_live_events = deque(maxlen=500)
_live_alerts = deque(maxlen=200)
_live_users = {}  # user_id → {name, raw_id, persona, live_events, flags, max_score}
_event_id_counter = 0
_alert_id_counter = 0
_sse_subscribers = []

# ── Real replay state ───────────────────────────────────────────
# Replays genuine scored LANL events from the parquet. Independent of
# _live_events, which still holds events from the employee login simulation.
_replay_events = None
_replay_index = 0
_replay_running = False
_replay_speed = 20          # events pushed per second
_replay_thread = None
_replay_lock = threading.Lock()
# Acknowledged alert ids. _replay_alerts() rebuilds its dicts on every call, so
# acknowledgement cannot be stored on the alert itself; the mutation would be
# discarded before anyone read it back.
_replay_acked = set()

# ── Dataset state (precomputed parquet) ────────────────────────
_scores_df = None
_cached_dashboard = None
_cached_alerts = None
_scorer_ready = False


def _load_scores():
    global _scores_df
    if _scores_df is None:
        if not os.path.exists(SCORES_PARQUET):
            raise FileNotFoundError(f"Scores not found at {SCORES_PARQUET}. Run scoring first.")
        t0 = time.time()
        _scores_df = pd.read_parquet(SCORES_PARQUET)
        print(f"loaded scores in {time.time()-t0:.0f}s: {len(_scores_df):,} rows")
    return _scores_df


def _init_scorer():
    global _scorer_ready
    if not _scorer_ready:
        scorer_init(DEMO_USERS)
        _scorer_ready = True


# ── SSE ─────────────────────────────────────────────────────────
def _sse_push(event_data):
    """Push event to all SSE subscribers.

    A slow client must not lose the stream. If a subscriber queue is full we
    discard its oldest message and keep the newest, because the live view only
    cares about recent events. Dropping the whole subscriber instead made the
    dashboard silently miss most events at high replay speeds.
    """
    msg = f"event: score\ndata: {json.dumps(event_data)}\n\n"
    dead = []
    for q in _sse_subscribers:
        try:
            q.put_nowait(msg)
        except queue.Full:
            try:
                q.get_nowait()          # drop oldest
                q.put_nowait(msg)       # keep newest
            except queue.Empty:
                dead.append(q)
    for q in dead:
        _sse_subscribers.remove(q)


@app.route('/events/stream')
def events_stream():
    """SSE: one `score` message per scored event."""
    q = queue.Queue(maxsize=2000)
    _sse_subscribers.append(q)
    def gen():
        try:
            while True:
                try:
                    msg = q.get(timeout=15)
                    yield msg
                except queue.Empty:
                    yield ": keep-alive\n\n"
        except GeneratorExit:
            if q in _sse_subscribers:
                _sse_subscribers.remove(q)
    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Real event replay ───────────────────────────────────────────
def _replay_progress():
    """Counters for the events emitted so far."""
    global _replay_events, _replay_index
    if _replay_events is None:
        _replay_events = _replay.get_events()
    seen = _replay_events[:_replay_index]
    attacks = [e for e in seen if e['is_red']]
    return {
        'emitted': len(seen),
        'total': len(_replay_events),
        'attacksSeen': len(attacks),
        'attacksCaught': sum(1 for e in attacks if e['decision'] in ('block', 'flag')),
        'attacksMissed': sum(1 for e in attacks if e['decision'] == 'allow'),
        'flagged': sum(1 for e in seen if not e['is_red'] and e['decision'] in ('block', 'flag')),
        'index': _replay_index,
        'running': _replay_running,
        'speed': _replay_speed,
        'done': _replay_index >= len(_replay_events),
    }


def _replay_loop():
    """Worker thread. Pushes real events over SSE at _replay_speed per second."""
    global _replay_index, _replay_running, _replay_events, _replay_speed
    if _replay_events is None:
        _replay_events = _replay.get_events()
    while True:
        with _replay_lock:
            if not _replay_running:
                return
            if _replay_index >= len(_replay_events):
                _replay_running = False
                return
            event = _replay_events[_replay_index]
            _replay_index += 1
            speed = _replay_speed
        _sse_push(event)
        time.sleep(1.0 / max(1, speed))


@app.route('/api/replay/status')
def api_replay_status():
    """Progress + summary for the real replay window.

    Also returns the events already emitted. The dashboard reloads when the
    user visits Dataset Analysis, which wipes browser-side state, so the client
    rebuilds its table from here instead of trusting anything it held in memory.
    """
    limit = request.args.get('limit', type=int) or 2000
    limit = max(0, min(limit, 5000))
    with _replay_lock:
        sent = list(_replay_events[:_replay_index])[-limit:] if _replay_events else []
    return jsonify({'progress': _replay_progress(), 'meta': _replay.get_meta(),
                    'events': sent})


@app.route('/api/replay/start', methods=['POST'])
def api_replay_start():
    """Start streaming real events."""
    global _replay_running, _replay_thread, _replay_speed, _replay_events, _replay_index
    data = request.get_json() or {}
    speed = data.get('speed')
    with _replay_lock:
        if speed:
            _replay_speed = max(1, min(500, int(speed)))
        if _replay_events is None:
            _replay_events = _replay.get_events()
        if _replay_index >= len(_replay_events):
            _replay_index = 0
        _replay_running = True
        if _replay_thread is None or not _replay_thread.is_alive():
            _replay_thread = threading.Thread(target=_replay_loop, daemon=True)
            _replay_thread.start()
    return jsonify({'ok': True, 'progress': _replay_progress()})


@app.route('/api/replay/stop', methods=['POST'])
def api_replay_stop():
    """Pause the stream. The index is kept so playback resumes where it stopped."""
    global _replay_running
    with _replay_lock:
        _replay_running = False
    return jsonify({'ok': True, 'progress': _replay_progress()})


@app.route('/api/replay/reset', methods=['POST'])
def api_replay_reset():
    """Rewind to the first event and drop acknowledgements."""
    global _replay_index, _replay_running
    with _replay_lock:
        _replay_index = 0
        _replay_running = False
        _replay_acked.clear()
    return jsonify({'ok': True, 'progress': _replay_progress()})


@app.route('/api/replay/jump_attack', methods=['POST'])
def api_replay_jump_attack():
    """Skip ahead to the next confirmed attack and emit it immediately."""
    global _replay_events, _replay_index
    if _replay_events is None:
        _replay_events = _replay.get_events()
    with _replay_lock:
        idx = _replay.next_attack_index(_replay_events, _replay_index)
        if idx is None:
            return jsonify({'ok': False, 'error': 'no further attacks in window',
                            'progress': _replay_progress()})
        _replay_index = idx + 1
        event = _replay_events[idx]
    _sse_push(event)
    return jsonify({'ok': True, 'event': event, 'progress': _replay_progress()})


# ── Auth routes ─────────────────────────────────────────────────
@app.route('/')
def index():
    if 'user' in session:
        role = session.get('role', 'employee')
        return redirect(url_for('analyst_dashboard' if role == 'analyst' else 'employee_view'))
    session['user'] = 'soc_admin'
    session['role'] = 'analyst'
    session['display_name'] = 'SOC Analyst'
    return redirect(url_for('analyst_dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        totp_code = request.form.get('totp', '').strip()
        user = authenticate(username, password, totp_code)
        if user:
            session['user'] = username
            session['role'] = user['role']
            session['display_name'] = user['name']
            session['user_id'] = user.get('user_id')
            if user['role'] == 'analyst':
                return redirect(url_for('analyst_dashboard'))
            return redirect(url_for('employee_view'))
        error = 'Invalid credentials. Check password and TOTP code.'

    dev_codes = {}
    dev_roles = {}
    dev_passwords = {}
    if os.environ.get('LANL_DEV'):
        for username in USERS:
            dev_codes[username] = get_current_code(username)
            dev_roles[username] = USERS[username]['role']
            dev_passwords[username] = USERS[username]['password']
    return render_template('login.html', error=error, dev_codes=dev_codes, dev_roles=dev_roles, dev_passwords=dev_passwords)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/employee')
def employee_view():
    if 'user' not in session:
        return redirect(url_for('login'))
    if session.get('role') == 'analyst':
        return redirect(url_for('analyst_dashboard'))

    username = session['user']
    user_info = USERS.get(username, {})
    user_id = user_info.get('user_id')

    if not user_id:
        return render_template('employee.html',
                               name=session.get('display_name', username),
                               decision='ALLOW', score=0.0, simulated=True)

    _init_scorer()
    score, decision, features = simulate_login_burst(user_id, username)

    reasons = _derive_reasons(features)
    return render_template('employee.html',
                           name=session.get('display_name', username),
                           decision=decision, score=round(score, 4),
                           threshold=round(THRESHOLD, 4),
                           timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                           reasons=reasons,
                           simulated=True)


# ── Page routes ─────────────────────────────────────────────────
@app.route('/analyst')
def analyst_dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    role = session.get('role', 'employee')
    return render_template('index.html',
                           display_name=session.get('display_name', 'Analyst'),
                           username=session.get('user', 'analyst'),
                           role_label='Analyst' if role == 'analyst' else 'Employee')


@app.route('/analyst/dataset')
def dataset_analysis():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('dataset.html')


# ── Live event recording ────────────────────────────────────────
def _record_event(user_id, name, src, dst, auth_type, score, decision, features, time_val):
    """Record a SIMULATED event from the employee login path.

    These are synthetic. They are tagged simulated=True so the API and the
    Simulation Lab can label them, and they are kept out of the analyst
    dashboard, which reads real events via live/replay.py.
    """
    global _event_id_counter, _alert_id_counter
    _event_id_counter += 1
    event = {
        'id': _event_id_counter,
        'simulated': True,
        'user_id': user_id,
        'name': name,
        'src_computer': src,
        'dst_computer': dst,
        'auth_type': auth_type,
        'anomaly_score': round(score, 6),
        'combined_score': round(score, 6),
        'decision': decision.lower(),
        'is_red': None,
        'ts': time.strftime('%H:%M:%S'),
        'time': int(time_val),
        'features': {k: round(float(v), 6) for k, v in features.items()},
    }
    _live_events.append(event)

    # Update user stats
    u = _live_users.setdefault(user_id, {
        'user_id': user_id, 'name': name, 'raw_id': user_id,
        'persona': 'unknown', 'live_events': 0, 'flags': 0, 'max_score': 0.0
    })
    u['live_events'] += 1
    u['max_score'] = max(u['max_score'], score)
    if decision.lower() in ('flag', 'block'):
        u['flags'] += 1
        u['persona'] = 'attacker'
    elif u['persona'] == 'unknown':
        u['persona'] = 'normal'

    # Create alert for BLOCK/FLAG
    if decision.lower() in ('flag', 'block'):
        _alert_id_counter += 1
        severity = 'critical' if score > THRESHOLD else 'high'
        alert = {
            'id': _alert_id_counter,
            'eventId': event['id'],
            'user_id': user_id,
            'name': name,
            'severity': severity,
            'combined_score': round(score, 6),
            'reasons': _derive_reasons(features),
            'decision': decision.lower(),
            'timestamp': event['ts'],
            'status': 'new',
        }
        _live_alerts.append(alert)

    # Push to SSE
    _sse_push(event)


def _derive_reasons(features):
    """Derive plain-language reasons from feature values."""
    reasons = []
    if features.get('dst_first', 0) > 0:
        reasons.append('Accessing a machine never visited before in 6 months of history')
    if features.get('src_first', 0) > 0:
        reasons.append('Login from a machine this user has never used before')
    if features.get('vel_1h', 0) > 10:
        reasons.append(f"{int(features['vel_1h'])} login attempts in 1 hour (normal is 2-5/hr)")
    if features.get('fail_1h', 0) > 0:
        reasons.append(f"{int(features['fail_1h'])} failed authentication attempts in the last hour")
    if features.get('hour_ratio', 0) > 0.01:
        reasons.append('Activity at an unusual hour for this user')
    if features.get('iat_zscore', 0) > 2:
        reasons.append('Login timing does not match the user\'s typical pattern')
    if features.get('lstm_ae_recon_error', 0) > 0.5:
        reasons.append('Sequence of events does not match known behavior patterns')
    return '; '.join(reasons) if reasons else 'Multiple behavioral indicators deviate from baseline'


def simulate_login_burst(user_id, username):
    """Score a synthetic login burst for the Simulation Lab.

    SIMULATED DATA. Machine names, hours and auth types are drawn with
    random.choice and do not correspond to any LANL record. It exists only so
    the employee login path still has something to exercise; the analyst
    dashboard reads real events from live/replay.py instead.

    For attackers (ace): 8-12 events, 80% anomalous. For normal users:
    3-5 events, 30% anomalous.
    """
    import random

    is_attacker = (user_id == 'U293@DOM1')
    if is_attacker:
        n_events = random.randint(8, 12)
        anomalous_rate = 0.8
    else:
        n_events = random.randint(3, 5)
        anomalous_rate = 0.3

    known_dst = _scorer._seen_dst_computers.get(user_id, set()).copy()
    known_src = _scorer._seen_src_computers.get(user_id, set()).copy()
    pool_unknown_dst = [m for m in _scorer._machine_pop if m not in known_dst]
    all_src = set()
    for srcs in _scorer._seen_src_computers.values():
        all_src.update(srcs)
    pool_unknown_src = [m for m in all_src if m not in known_src]
    rare_hours = list(_scorer._rare_hours.get(user_id, set()))
    hour_hist = _scorer._hour_histograms.get(user_id, [0] * 24)
    low_hours = [h for h in range(24) if hour_hist[h] <= 1]
    common_hours = [h for h in range(24) if hour_hist[h] > 0] or list(range(24))

    results = []
    for i in range(n_events):
        is_anomalous = random.random() < anomalous_rate

        if is_anomalous and pool_unknown_dst and pool_unknown_src:
            dst = random.choice(pool_unknown_dst)
            pool_unknown_dst.remove(dst)
            src = random.choice(pool_unknown_src)
            pool_unknown_src.remove(src)
        elif is_anomalous and pool_unknown_dst:
            dst = random.choice(pool_unknown_dst)
            pool_unknown_dst.remove(dst)
            src = next(iter(known_src), 'C0')
        else:
            dst = next(iter(known_dst), 'C0')
            src = next(iter(known_src), 'C0')

        if is_anomalous and is_attacker:
            auth = 'Kerberos'
        elif is_anomalous and random.random() < 0.5:
            auth = 'Kerberos'
        else:
            auth = 'NTLM'

        if is_anomalous and rare_hours:
            hour = random.choice(rare_hours)
        elif is_anomalous and low_hours:
            hour = random.choice(low_hours)
        else:
            hour = random.choice(common_hours)

        time_val = _scorer._last_timestamps.get(user_id, 0) + 60

        score, decision, features = score_event(
            user_id=user_id, src_computer=src, dst_computer=dst,
            auth_type=auth, logon_type='Network', hour=hour, time_val=time_val,
        )

        _record_event(user_id, username, src, dst, auth, score, decision, features, time_val)
        results.append((score, decision, features))

    best = max(results, key=lambda r: r[0])

    # The forced-BLOCK branch that used to live here was removed. It set
    # score = THRESHOLD + 0.15 whenever the model failed to flag the burst,
    # which meant the employee page reported a detection the model never made.
    # reports/experiment_log.md records why live scoring is weak (training-
    # serving skew: incremental in-memory features against a model trained on
    # batch SQL features, live scores ~0.001 versus a 0.187 threshold), so the
    # honest result is now reported even when it is ALLOW.
    return best


# ── Live JSON API ───────────────────────────────────────────────
@app.route('/api/dashboard')
def api_dashboard():
    """Analyst dashboard — reads the real replay window, never the simulation."""
    global _replay_events
    if _replay_events is None:
        _replay_events = _replay.get_events()
    events = _replay_events[:_replay_index]
    alerts = _replay_alerts()
    total = len(events)
    anomalies = sum(1 for e in events if e['decision'] in ('flag', 'block'))
    risky_users = len(set(e['user_id'] for e in events if e['decision'] in ('flag', 'block')))
    users_monitored = len(set(e['user_id'] for e in events))

    # Risk distribution
    allow = sum(1 for e in events if e['decision'] == 'allow')
    flag = sum(1 for e in events if e['decision'] == 'flag')
    block = sum(1 for e in events if e['decision'] == 'block')
    risk_dist = [
        {'name': 'Allow', 'value': allow, 'color': '#57b06c'},
        {'name': 'Flag', 'value': flag, 'color': '#e8a33d'},
        {'name': 'Block', 'value': block, 'color': '#e5484d'},
    ]

    # Auth type breakdown
    auth_counts = Counter(e.get('auth_type', 'Unknown') for e in events)
    auth_dist = [{'name': k, 'value': v} for k, v in auth_counts.most_common()]

    # Top risky users (top 5 by max score), from the real replay window
    top_risky = _replay_user_stats()[:5]

    # KPI deltas (compare last 60 events vs previous 60)
    recent_60 = events[-60:] if len(events) > 60 else events
    prev_60 = events[-120:-60] if len(events) > 120 else []
    def _count_flags(evts): return sum(1 for e in evts if e['decision'] in ('flag', 'block'))
    delta_anomalies = _count_flags(recent_60) - _count_flags(prev_60) if prev_60 else 0
    delta_events = len(recent_60) - len(prev_60) if prev_60 else 0

    return jsonify({
        'kpis': {
            'totalEvents': total,
            'anomalies': anomalies,
            'highRiskUsers': risky_users,
            'usersMonitored': users_monitored,
            'deltaEvents': delta_events,
            'deltaAnomalies': delta_anomalies,
        },
        'recentEvents': events[-30:],
        'alerts': alerts[-20:],
        'riskDistribution': risk_dist,
        'authTypeBreakdown': auth_dist,
        'topRiskyUsers': top_risky,
    })


def _replay_alerts():
    """Alerts derived from the real replay window.

    An alert is raised for every replayed event the model blocked or flagged,
    tagged with its ground-truth label so an analyst can see at a glance
    whether the detection was correct.
    """
    global _replay_events, _replay_index
    if _replay_events is None:
        _replay_events = _replay.get_events()
    out = []
    for e in _replay_events[:_replay_index]:
        if e['decision'] not in ('block', 'flag'):
            continue
        correct = (e['decision'] != 'allow') == bool(e['is_red'])
        if e['is_red']:
            severity = 'critical' if correct else 'high'
            reasons = ('Confirmed red-team attack. '
                       + ('Model detection was correct.'
                          if correct else 'Model flagged this but it was not an attack.'))
        else:
            severity = 'medium'
            reasons = 'Normal traffic the model flagged. False positive.'
        out.append({
            'id': e['id'],
            'user_id': e['user_id'],
            'name': e['user_id'],
            'severity': severity,
            'combined_score': e['anomaly_score'],
            'decision': e['decision'],
            'reasons': reasons,
            'timestamp': 'T+%ds' % e['offset'],
            'is_red': e['is_red'],
            'correct': correct,
            'src_computer': e['src_computer'],
            'dst_computer': e['dst_computer'],
            'status': 'acknowledged' if e['id'] in _replay_acked else 'new',
        })
    out.sort(key=lambda a: -a['combined_score'])
    return out


def _replay_user_stats():
    """Per-user stats from the real replay window, grouped by ground truth."""
    global _replay_events, _replay_index
    if _replay_events is None:
        _replay_events = _replay.get_events()
    seen = _replay_events[:_replay_index]
    by_user = {}
    for e in seen:
        u = by_user.setdefault(e['user_id'], {
            'user_id': e['user_id'], 'name': e['user_id'], 'raw_id': e['user_id'],
            'persona': 'normal', 'live_events': 0, 'flags': 0, 'max_score': 0.0,
            'attacks': 0, 'attacks_caught': 0, 'false_positives': 0,
        })
        u['live_events'] += 1
        flagged = e['decision'] in ('flag', 'block')
        if flagged:
            u['flags'] += 1
        if e['is_red']:
            u['attacks'] += 1
            if flagged:
                u['attacks_caught'] += 1
        elif flagged:
            u['false_positives'] += 1
        u['max_score'] = max(u['max_score'], e['anomaly_score'])
    for u in by_user.values():
        if u['attacks_caught']:
            u['persona'] = 'attacker'
        elif u['attacks']:
            u['persona'] = 'attacker_missed'
        elif u['flags']:
            u['persona'] = 'flagged'
    return sorted(by_user.values(), key=lambda u: (-u['attacks_caught'], -u['max_score']))


@app.route('/api/alerts')
def api_alerts():
    """Alerts from the real replay window (source of truth, not simulation)."""
    return jsonify(_replay_alerts())


@app.route('/api/users')
def api_users():
    """User stats from the real replay window (source of truth, not simulation)."""
    return jsonify(_replay_user_stats())


@app.route('/api/known_users')
def api_known_users():
    """All users from training data (for behavior insights)."""
    _init_scorer()
    from scorer import _user_totals, DEMO_USERS
    from auth import USERS
    _id_to_name = {v['user_id']: v['name'] for v in USERS.values()}
    users = []
    for uid in DEMO_USERS:
        users.append({
            'user_id': uid,
            'name': _id_to_name.get(uid, uid.split('@')[0]),
            'totalEvents': _user_totals.get(uid, 0),
        })
    return jsonify(users)


@app.route('/api/stats')
def api_stats():
    """Counts for both data sources, clearly separated."""
    global _replay_events
    if _replay_events is None:
        _replay_events = _replay.get_events()
    return jsonify({
        'replay_events': _replay_index,
        'replay_total': len(_replay_events),
        'replay_alerts': len(_replay_alerts()),
        'replay_users': len(_replay_user_stats()),
        'simulated_events': len(_live_events),
        'simulated_alerts': len(_live_alerts),
        'history_events': 0,
    })


@app.route('/api/search')
def api_search():
    """Global search across the real replay window, its users and its alerts."""
    q = request.args.get('q', '').strip().lower()
    if not q:
        return jsonify({'events': [], 'users': [], 'alerts': []})

    global _replay_events
    if _replay_events is None:
        _replay_events = _replay.get_events()
    seen = _replay_events[:_replay_index]

    matched_events = [e for e in seen if any(
        q in (e.get('user_id') or '').lower() or
        q in (e.get('src_computer') or '').lower() or
        q in (e.get('dst_computer') or '').lower() or
        q in (e.get('auth_type') or '').lower() or
        q in (e.get('decision') or '').lower()
        for _ in [1]
    )][-20:]

    matched_users = [u for u in _replay_user_stats() if any(
        q in (u.get('user_id') or '').lower() or
        q in (u.get('persona') or '').lower()
        for _ in [1]
    )]

    matched_alerts = [a for a in _replay_alerts() if any(
        q in (a.get('user_id') or '').lower() or
        q in (a.get('reasons') or '').lower() or
        q in (a.get('severity') or '').lower()
        for _ in [1]
    )][-20:]

    return jsonify({
        'events': matched_events,
        'users': matched_users,
        'alerts': matched_alerts,
    })


@app.route('/api/investigation/<int:event_id>')
def api_investigation(event_id):
    """Investigation detail for a real replay event."""
    global _replay_events
    if _replay_events is None:
        _replay_events = _replay.get_events()
    event = None
    for e in _replay_events[:_replay_index]:
        if e['id'] == event_id:
            event = e
            break
    if event is None:
        return jsonify({'error': 'event not found'}), 404

    features = event.get('features', {})

    # Feature contributions
    feature_contributions = []
    if features.get('dst_first', 0) > 0:
        feature_contributions.append({'feature': 'First-time Destination', 'value': 1, 'color': '#e5484d',
                                      'detail': f"Never visited {event['dst_computer']}"})
    if features.get('src_first', 0) > 0:
        feature_contributions.append({'feature': 'First-time Source', 'value': 1, 'color': '#e5484d',
                                      'detail': f"Never used {event['src_computer']}"})
    if features.get('vel_1h', 0) > 10:
        feature_contributions.append({'feature': 'High Velocity', 'value': features['vel_1h'], 'color': '#ff9b9e',
                                      'detail': f"{int(features['vel_1h'])} events in last hour"})
    if features.get('fail_1h', 0) > 0:
        feature_contributions.append({'feature': 'Recent Failures', 'value': features['fail_1h'], 'color': '#ff9b9e',
                                      'detail': f"{int(features['fail_1h'])} failures in last hour"})
    if features.get('hour_ratio', 0) > 0.01:
        feature_contributions.append({'feature': 'Unusual Hour', 'value': features['hour_ratio'], 'color': '#e8a33d',
                                      'detail': f"hour_ratio={features['hour_ratio']:.4f}"})
    if features.get('iat_zscore', 0) > 2:
        feature_contributions.append({'feature': 'Anomalous Timing', 'value': features['iat_zscore'], 'color': '#e8a33d',
                                      'detail': f"iat_zscore={features['iat_zscore']:.2f}"})

    # Deviation points
    dev_points = len(feature_contributions)
    if features:
        dev_reasons = _derive_reasons(features)
    else:
        # Replay events carry no per-event feature vector, so _derive_reasons
        # would fall through to "Multiple behavioral indicators deviate from
        # baseline" for an event that scored 0.0000. Say what is actually known.
        if event['is_red']:
            dev_reasons = ('Confirmed red-team attack. The model '
                           + ('blocked it.' if event['decision'] == 'block'
                              else 'flagged it.' if event['decision'] == 'flag'
                              else 'allowed it, which is a miss.'))
        elif event['decision'] in ('block', 'flag'):
            dev_reasons = ('The model raised an alert on normal traffic. '
                           'This is a false positive.')
        else:
            dev_reasons = ('No deviation. The event matches this user\'s '
                           'normal pattern and was allowed.')

    # Timeline — recent events for same user
    user_events = [e for e in _replay_events[:_replay_index]
                   if e['user_id'] == event['user_id']]
    timeline = [{
        'event': f"{e['src_computer']} -> {e['dst_computer']}",
        'severity': 'critical' if e['decision'] == 'block' else ('high' if e['decision'] == 'flag' else None),
        'time': 'T+%ds' % e['offset'],
        'score': e['anomaly_score'],
    } for e in user_events[-10:]]

    # Baseline: how this user normally behaves, from the training baseline
    _init_scorer()
    known_src = len(_scorer._seen_src_computers.get(event['user_id'], ()))
    known_dst = len(_scorer._seen_dst_computers.get(event['user_id'], ()))
    total_events = _scorer._user_totals.get(event['user_id'], 0)
    u = {
        'totalEvents': total_events,
        'knownSrc': known_src,
        'knownDst': known_dst,
    }

    flagged = event['decision'] in ('block', 'flag')
    return jsonify({
        'id': event['id'],
        'displayName': event['user_id'],
        'rawId': event['user_id'],
        'user_id': event['user_id'],
        'severity': 'critical' if event['decision'] == 'block' else ('high' if event['decision'] == 'flag' else 'low'),
        'combinedScore': event['anomaly_score'],
        'devPoints': dev_points,
        'devReasons': dev_reasons,
        'hasFeatureDetail': bool(features),
        'type': event['decision'],
        'description': dev_reasons,
        'src_computer': event['src_computer'],
        'dst_computer': event['dst_computer'],
        'auth_type': event['auth_type'],
        'logon_type': event['logon_type'],
        'result': event['result'],
        'offsetSeconds': event['offset'],
        'groundTruth': 'RED (confirmed attack)' if event['is_red'] else 'Normal',
        'isRed': event['is_red'],
        'modelCorrect': flagged == bool(event['is_red']),
        'featureContributions': feature_contributions,
        'timeline': timeline,
        'features': features,
        'baseline': {
            'totalEvents': total_events,
            'knownSrcComputers': known_src,
            'knownDstComputers': known_dst,
            'srcIsNew': event['src_computer'] not in _scorer._seen_src_computers.get(event['user_id'], set()),
            'dstIsNew': event['dst_computer'] not in _scorer._seen_dst_computers.get(event['user_id'], set()),
        },
    })


@app.route('/api/alerts/<int:alert_id>/ack', methods=['POST'])
def api_ack_alert(alert_id):
    """Acknowledge an alert from the real replay window."""
    with _replay_lock:
        _replay_acked.add(alert_id)
    alert = next((a for a in _replay_alerts() if a['id'] == alert_id), None)
    if alert is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True, 'alert': alert})


@app.route('/api/model/metrics')
def api_model_metrics():
    """Feature importances read from the trained model, not hardcoded.

    The booster was trained on a numpy array, so feature_name() returns
    positional placeholders. The saved bundle carries the real feature names
    alongside the model, so read them from there rather than guessing an order.
    """
    _init_scorer()
    bundle = joblib.load(MODEL_PATH)
    booster = getattr(bundle['model'], 'booster_', None)
    if booster is None:
        return jsonify({'error': 'booster unavailable'}), 503

    gains = [float(g) for g in booster.feature_importance(importance_type='gain')]
    names = bundle.get('features') or list(FEATURE_COLS)
    if len(names) != len(gains):
        return jsonify({'error': f'feature name count {len(names)} != importance count {len(gains)}'}), 500

    pairs = sorted(zip(names, gains), key=lambda kv: -kv[1])
    return jsonify({
        'source': 'models/lanl_lgb_21feat.joblib',
        'importance_type': 'gain',
        'feature_count': len(pairs),
        'feature_importance': [{'feature': n, 'importance': v} for n, v in pairs],
    })


@app.route('/api/simulation')
def api_simulation():
    """Simulated events produced by the employee login path.

    Kept separate from /api/dashboard so synthetic data can never be mistaken
    for scored LANL records.
    """
    events = list(_live_events)
    anomalies = sum(1 for e in events if e['decision'] in ('flag', 'block'))
    return jsonify({
        'disclaimer': ('SIMULATED DATA - generated by the employee login demo. '
                       'These are not real LANL records.'),
        'total': len(events),
        'anomalies': anomalies,
        'users': list(_live_users.values()),
        'events': events[-200:],
        'alerts': list(_live_alerts)[-50:],
    })


@app.route('/api/reset', methods=['POST'])
def api_reset():
    """Clear simulated events and alerts (real replay state is untouched)."""
    global _event_id_counter, _alert_id_counter
    _live_events.clear()
    _live_alerts.clear()
    _live_users.clear()
    _event_id_counter = 0
    _alert_id_counter = 0
    return jsonify({'ok': True})


@app.route('/api/totp_status')
def api_totp_status():
    """Return current TOTP codes + seconds remaining for all demo users."""
    if not os.environ.get('LANL_DEV'):
        return jsonify({'error': 'not dev mode'}), 403
    remaining = get_totp_remaining()
    codes = {}
    for username in USERS:
        codes[username] = {
            'code': get_current_code(username),
            'remaining': remaining
        }
    return jsonify(codes)


# ── Health ──────────────────────────────────────────────────────
@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'scorer_ready': _scorer_ready, 'scores_loaded': _scores_df is not None})


# ── Dataset precompute (separate from live) ─────────────────────
def _precompute_dashboard():
    global _cached_dashboard, _cached_alerts
    df = _load_scores()
    t0 = time.time()
    threshold = float(df['threshold'].iloc[0])
    total = len(df)
    red_mask = df['is_red'] == True
    normal_mask = df['is_red'] == False
    red_count = int(red_mask.sum())
    detections = int((df.loc[red_mask, 'anomaly_score'] > threshold).sum())
    fp = int(((df['anomaly_score'] > threshold) & normal_mask).sum())

    # Confusion matrix at two decision boundaries.
    # scorer.py raises BLOCK above THRESHOLD and FLAG above THRESHOLD * 0.7, so
    # "predicted attack" is ambiguous. Both are reported rather than silently
    # picking one: an analyst is notified on a FLAG just as on a BLOCK.
    def _matrix(cut):
        pos = df['anomaly_score'] > cut
        tp = int((pos & red_mask).sum())
        f_p = int((pos & normal_mask).sum())
        fn = int((~pos & red_mask).sum())
        tn = int((~pos & normal_mask).sum())
        prec = tp / (tp + f_p) if (tp + f_p) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        return {
            'cutoff': round(float(cut), 6),
            'tp': tp, 'fp': f_p, 'tn': tn, 'fn': fn,
            'precision': round(prec, 4),
            'recall': round(rec, 4),
            'f1': round(2 * prec * rec / (prec + rec), 4) if (prec + rec) else 0.0,
            'specificity': round(tn / (tn + f_p), 8) if (tn + f_p) else 0.0,
            'fpr': round(f_p / (f_p + tn), 8) if (f_p + tn) else 0.0,
            'accuracy': round((tp + tn) / total, 6) if total else 0.0,
        }

    block_only = _matrix(threshold)
    alert_level = _matrix(threshold * 0.7)

    three_class = []
    for dec in ('ALLOW', 'FLAG', 'BLOCK'):
        sel = df['decision'] == dec
        three_class.append({
            'decision': dec,
            'attack': int((sel & red_mask).sum()),
            'normal': int((sel & normal_mask).sum()),
        })

    confusion = {
        'population': 'full dataset, 29.9M events (includes training rows)',
        'threshold': threshold,
        'primary': 'block_only',
        'block_only': block_only,
        'alert_level': alert_level,
        'three_class': three_class,
        'caveat': ('Accuracy is near 1.0 because attacks are 0.0023% of the '
                   'dataset. A model that never alerts scores higher. Prefer '
                   'recall and false positive count.'),
    }

    df['_hour_bucket'] = (df['time'] // 3600).astype(int)
    hourly = df.groupby('_hour_bucket').agg(
        mean_score=('anomaly_score', 'mean'),
        max_score=('anomaly_score', 'max'),
        count=('anomaly_score', 'count'),
        red_count=('is_red', 'sum')
    ).reset_index()
    hourly.columns = ['hour_bucket', 'mean_score', 'max_score', 'count', 'red_count']
    hourly = hourly.sort_values('hour_bucket').tail(500)

    top_users = (df.groupby('src_user')
                 .agg(max_score=('anomaly_score', 'max'),
                      mean_score=('anomaly_score', 'mean'),
                      events=('anomaly_score', 'count'),
                      is_red=('is_red', 'first'))
                 .query('is_red == True')
                 .nlargest(10, 'max_score')
                 .reset_index())

    heatmap_users = top_users['src_user'].head(8).tolist()
    heatmap_df = df[df['src_user'].isin(heatmap_users)].copy()
    heatmap_df['hour'] = heatmap_df['hour'].astype(int)
    heatmap = (heatmap_df.groupby(['src_user', 'hour'])
               .agg(mean_score=('anomaly_score', 'mean'))
               .reset_index())
    heatmap_data = [{'user': r['src_user'], 'hour': int(r['hour']), 'score': float(r['mean_score'])}
                    for _, r in heatmap.iterrows()]

    _cached_dashboard = {
        'kpis': {
            'total_events': total, 'red_events': red_count,
            'detections': detections, 'false_positives': fp,
            'detection_rate': round(100 * detections / red_count, 1) if red_count > 0 else 0,
            'threshold': threshold
        },
        'timeline': hourly.to_dict('records'),
        'top_users': top_users.to_dict('records'),
        'confusion': confusion,
        'heatmap': heatmap_data
    }

    _cached_alerts = (df[df['anomaly_score'] > threshold]
                      .nlargest(200, 'anomaly_score')
                      [['time', 'src_user', 'dst_user', 'src_computer', 'dst_computer',
                        'anomaly_score', 'decision', 'is_red']]
                      .to_dict('records'))
    print(f"pre-aggregated dashboard in {time.time()-t0:.0f}s")


@app.route('/api/dataset/dashboard')
def api_dataset_dashboard():
    """Dataset analysis — precomputed parquet data."""
    if _cached_dashboard is None:
        _precompute_dashboard()
    return jsonify(_cached_dashboard)


@app.route('/api/dataset/alerts')
def api_dataset_alerts():
    if _cached_alerts is None:
        _precompute_dashboard()
    return jsonify(_cached_alerts)


# ── Dev login bypass (no TOTP) ──────────────────────────────────
@app.route('/dev/login', methods=['POST'])
def dev_login():
    """Dev-only: instant login without TOTP. Only when LANL_DEV=1."""
    if not os.environ.get('LANL_DEV'):
        return jsonify({'error': 'not dev mode'}), 403
    data = request.get_json() or {}
    username = data.get('username', '').strip().lower()
    user = USERS.get(username)
    if not user:
        return jsonify({'error': f'unknown user: {username}'}), 400
    session['user'] = username
    session['role'] = user['role']
    session['display_name'] = user['name']
    session['user_id'] = user.get('user_id')
    return jsonify({'ok': True, 'role': user['role'], 'name': user['name']})


# ── User profile (baseline + live session) ──────────────────────
@app.route('/api/user_profile/<user_id>')
def api_user_profile(user_id):
    """Combined training baseline + live session data for a user."""
    _init_scorer()

    # Training baseline from scorer
    import math
    known_dst = list(_scorer._seen_dst_computers.get(user_id, set()))
    known_src = list(_scorer._seen_src_computers.get(user_id, set()))
    hour_hist = _scorer._hour_histograms.get(user_id, [0] * 24)
    user_total = _scorer._user_totals.get(user_id, 0)
    rare_hours = list(_scorer._rare_hours.get(user_id, set()))
    iat_hist = list(_scorer._iat_history.get(user_id, []))

    # Compute avg IAT from history
    avg_iat = 0
    if len(iat_hist) > 1:
        diffs = [iat_hist[i+1] - iat_hist[i] for i in range(len(iat_hist)-1)]
        avg_iat = sum(diffs) / len(diffs) if diffs else 0

    # Typical pairs count
    pair_count = sum(1 for k in _scorer._pair_row_numbers if k.startswith(user_id + '|'))

    # Replay-window events for this user (real data, keeps baseline separate)
    global _replay_events
    if _replay_events is None:
        _replay_events = _replay.get_events()
    user_live = [e for e in _replay_events[:_replay_index] if e['user_id'] == user_id]
    session_flags = sum(1 for e in user_live if e['decision'] in ('flag', 'block'))
    session_max = max((e['anomaly_score'] for e in user_live), default=0.0)
    attacks = sum(1 for e in user_live if e['is_red'])

    from auth import USERS as _USERS
    _demo = next((v for v in _USERS.values() if v.get('user_id') == user_id), None)

    return jsonify({
        'user_id': user_id,
        # The drawer title is built from data.name; without this it renders
        # "unknown (U293)" instead of a readable label.
        'name': _demo['name'] if _demo else user_id.split('@')[0],
        'demo_user': _demo is not None,
        'baseline': {
            'totalEvents': user_total,
            'knownSrcComputers': sorted(known_src),
            'knownDstComputers': sorted(known_dst),
            'hourlyPattern': hour_hist,
            'rareHours': sorted(rare_hours),
            'avgIAT': round(avg_iat, 1),
            'typicalPairs': pair_count,
        },
        'replay': {
            'source': 'real scored LANL events',
            'events': user_live[-20:],
            'totalEvents': len(user_live),
            'flags': session_flags,
            'attacks': attacks,
            'maxScore': round(session_max, 6),
            'firstSeen': 'T+%ds' % user_live[0]['offset'] if user_live else None,
        }
    })


# ── Start ───────────────────────────────────────────────────────
if __name__ == '__main__':
    print("loading scores...")
    _load_scores()
    print("pre-aggregating dashboard...")
    _precompute_dashboard()
    print("initializing scorer...")
    _init_scorer()
    print("starting server on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
