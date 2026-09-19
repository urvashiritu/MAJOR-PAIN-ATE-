"""Flask backend for LANL anomaly detection — live dashboard + dataset analysis."""
import json
import os
import queue
import secrets
import sys
import time
from collections import deque
from flask import (Flask, Response, jsonify, send_from_directory, render_template,
                   request, redirect, url_for, session)
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from db import SCORES_PARQUET
from auth import authenticate, USERS, get_current_code, get_totp_secret, get_totp_remaining
from scorer import init as scorer_init, score_event, THRESHOLD, DEMO_USERS
import scorer as _scorer

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
    """Push event to all SSE subscribers."""
    msg = f"event: score\ndata: {json.dumps(event_data)}\n\n"
    dead = []
    for q in _sse_subscribers:
        try:
            q.put_nowait(msg)
        except queue.Full:
            dead.append(q)
    for q in dead:
        _sse_subscribers.remove(q)


@app.route('/events/stream')
def events_stream():
    """SSE: one `score` message per scored event."""
    q = queue.Queue(maxsize=100)
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
                               decision='ALLOW', score=0.0)

    _init_scorer()
    score, decision, features = simulate_login_burst(user_id, username)

    reasons = _derive_reasons(features)
    return render_template('employee.html',
                           name=session.get('display_name', username),
                           decision=decision, score=round(score, 4),
                           threshold=round(THRESHOLD, 4),
                           timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                           reasons=reasons)


# ── Page routes ─────────────────────────────────────────────────
@app.route('/analyst')
def analyst_dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')


@app.route('/analyst/dataset')
def dataset_analysis():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('dataset.html')


# ── Live event recording ────────────────────────────────────────
def _record_event(user_id, name, src, dst, auth_type, score, decision, features, time_val):
    global _event_id_counter, _alert_id_counter
    _event_id_counter += 1
    event = {
        'id': _event_id_counter,
        'user_id': user_id,
        'name': name,
        'src_computer': src,
        'dst_computer': dst,
        'auth_type': auth_type,
        'combined_score': round(score, 6),
        'decision': decision.lower(),
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
    """Generate scored events per login with weighted anomaly injection.

    For attackers (ace): 8-12 events, 80% anomalous, always stack
    unknown dst + unknown src + Kerberos together.
    For normal users: 3-5 events, 30% anomalous, random injection.
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

    if is_attacker and best[0] <= THRESHOLD:
        forced_score = THRESHOLD + 0.15
        forced_decision = 'BLOCK'
        forced_features = dict(best[2])
        _record_event(user_id, username, 'C_ANOMALOUS', 'C_ANOMALOUS',
                      'Kerberos', forced_score, forced_decision,
                      forced_features, time_val + 60)
        return (forced_score, forced_decision, forced_features)

    return best


# ── Live JSON API ───────────────────────────────────────────────
@app.route('/api/dashboard')
def api_dashboard():
    """Live dashboard — only session-scored events."""
    events = list(_live_events)
    alerts = list(_live_alerts)
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

    return jsonify({
        'kpis': {
            'totalEvents': total,
            'anomalies': anomalies,
            'highRiskUsers': risky_users,
            'usersMonitored': users_monitored,
        },
        'recentEvents': events[-30:],
        'alerts': alerts[-20:],
        'riskDistribution': risk_dist,
    })


@app.route('/api/alerts')
def api_alerts():
    """Live alerts — BLOCK/FLAG events from this session."""
    return jsonify(list(_live_alerts))


@app.route('/api/users')
def api_users():
    """Live user stats."""
    return jsonify(list(_live_users.values()))


@app.route('/api/stats')
def api_stats():
    """Live session counts."""
    return jsonify({
        'live_events': len(_live_events),
        'alerts': len(_live_alerts),
        'users': len(_live_users),
        'history_events': 0,
    })


@app.route('/api/investigation/<int:event_id>')
def api_investigation(event_id):
    """Investigation detail for a scored event."""
    event = None
    for e in _live_events:
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
    dev_reasons = _derive_reasons(features)

    # Timeline — recent events for same user
    user_events = [e for e in _live_events if e['user_id'] == event['user_id']]
    timeline = [{
        'event': f"{e['src_computer']} -> {e['dst_computer']}",
        'severity': 'critical' if e['decision'] == 'block' else ('high' if e['decision'] == 'flag' else None),
        'time': e['ts'],
        'score': e['combined_score'],
    } for e in user_events[-10:]]

    # Baseline
    u = _live_users.get(event['user_id'], {})

    return jsonify({
        'id': event['id'],
        'displayName': event['name'],
        'rawId': event['user_id'],
        'user_id': event['user_id'],
        'severity': 'critical' if event['decision'] == 'block' else ('high' if event['decision'] == 'flag' else 'low'),
        'combinedScore': event['combined_score'],
        'devPoints': dev_points,
        'devReasons': dev_reasons,
        'type': event['decision'],
        'description': dev_reasons,
        'src_computer': event['src_computer'],
        'dst_computer': event['dst_computer'],
        'auth_type': event['auth_type'],
        'result': 'Success',
        'featureContributions': feature_contributions,
        'timeline': timeline,
        'features': features,
        'baseline': {
            'totalEvents': u.get('live_events', 0),
            'failureRate': features.get('fail_rate', 0),
            'avgEventsPerHour': features.get('vel_1h', 0),
            'typicalSrcComputers': [],
            'typicalDstComputers': [],
        },
    })


@app.route('/api/alerts/<int:alert_id>/ack', methods=['POST'])
def api_ack_alert(alert_id):
    """Acknowledge an alert."""
    for a in _live_alerts:
        if a['id'] == alert_id:
            a['status'] = 'acknowledged'
            return jsonify({'ok': True})
    return jsonify({'error': 'not found'}), 404


@app.route('/api/reset', methods=['POST'])
def api_reset():
    """Clear all live events and alerts."""
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

    # Live session events
    user_live = [e for e in _live_events if e['user_id'] == user_id]
    session_flags = sum(1 for e in user_live if e['decision'] in ('flag', 'block'))
    session_max = max((e['combined_score'] for e in user_live), default=0.0)

    return jsonify({
        'user_id': user_id,
        'baseline': {
            'totalEvents': user_total,
            'knownSrcComputers': sorted(known_src),
            'knownDstComputers': sorted(known_dst),
            'hourlyPattern': hour_hist,
            'rareHours': sorted(rare_hours),
            'avgIAT': round(avg_iat, 1),
            'typicalPairs': pair_count,
        },
        'session': {
            'events': user_live[-20:],
            'totalEvents': len(user_live),
            'flags': session_flags,
            'maxScore': round(session_max, 6),
            'firstSeen': user_live[0]['ts'] if user_live else None,
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
    app.run(host='0.0.0.0', port=5000, debug=False)
