"""Flask backend for LANL anomaly detection — login + dashboard."""
import os
import sys
import time
import secrets
import pandas as pd
from flask import (Flask, jsonify, send_from_directory, render_template,
                   request, redirect, url_for, session)

sys.path.insert(0, os.path.dirname(__file__))
from db import SCORES_PARQUET
from auth import authenticate, USERS, get_current_code, get_totp_secret, get_totp_remaining
from scorer import init as scorer_init, score_event, THRESHOLD, DEMO_USERS
import scorer as _scorer

app = Flask(__name__,
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
            static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.secret_key = secrets.token_hex(32)

_scores_df = None
_scorer_ready = False
_live_events = []
_cached_dashboard = None
_cached_alerts = None


def _load_scores():
    global _scores_df
    if _scores_df is None:
        if not os.path.exists(SCORES_PARQUET):
            raise FileNotFoundError(f"Scores not found at {SCORES_PARQUET}. Run: python3 -m live.scoring")
        t0 = time.time()
        _scores_df = pd.read_parquet(SCORES_PARQUET)
        print(f"loaded scores in {time.time()-t0:.0f}s: {len(_scores_df):,} rows")
    return _scores_df


def _init_scorer():
    global _scorer_ready
    if not _scorer_ready:
        scorer_init(DEMO_USERS)
        _scorer_ready = True


@app.route('/')
def index():
    if 'user' in session:
        role = session.get('role', 'employee')
        return redirect(url_for('analyst_dashboard' if role == 'analyst' else 'employee_view'))
    # Auto-login as soc_admin
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

    # Show current TOTP codes for demo users (dev mode)
    dev_codes = {}
    dev_roles = {}
    if os.environ.get('LANL_DEV'):
        for username in USERS:
            dev_codes[username] = get_current_code(username)
            dev_roles[username] = USERS[username]['role']

    return render_template('login.html', error=error, dev_codes=dev_codes, dev_roles=dev_roles)


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
                               decision='ALLOW',
                               score=0.0)

    _init_scorer()

    time_val = _scorer._last_timestamps.get(user_id, 0) + 60
    hour = int((time_val % 86400) // 3600)
    src_pc = next(iter(_scorer._seen_src_computers.get(user_id, {'C0'})), 'C0')
    dst_pc = next(iter(_scorer._seen_dst_computers.get(user_id, {'C0'})), 'C0')

    score, decision, _ = score_event(
        user_id=user_id,
        src_computer=src_pc,
        dst_computer=dst_pc,
        auth_type='NTLM',
        logon_type='Network',
        hour=hour,
        time_val=time_val,
    )

    _live_events.append({
        'time': int(time_val),
        'username': username,
        'user_id': user_id,
        'src_computer': src_pc,
        'dst_computer': dst_pc,
        'auth_type': 'NTLM',
        'score': round(score, 6),
        'decision': decision,
        'threshold': round(THRESHOLD, 6),
    })
    if len(_live_events) > 100:
        del _live_events[:50]

    return render_template('employee.html',
                           name=session.get('display_name', username),
                           decision=decision,
                           score=round(score, 4),
                           threshold=round(THRESHOLD, 4),
                           timestamp=time.strftime('%Y-%m-%d %H:%M:%S'))


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


def _precompute_dashboard():
    """Pre-aggregate dashboard data once on startup."""
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
            'total_events': total,
            'red_events': red_count,
            'detections': detections,
            'false_positives': fp,
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


@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'scorer_ready': _scorer_ready, 'scores_loaded': _scores_df is not None})


@app.route('/api/score', methods=['POST'])
def api_score():
    """Score a login event. Returns {score, decision}."""
    if 'user' not in session:
        return jsonify({'error': 'not authenticated'}), 401

    _init_scorer()
    data = request.get_json() or {}
    user_id = data.get('user_id', session.get('user_id'))
    if not user_id:
        return jsonify({'error': 'no user_id'}), 400

    import math
    now = int(time.time())
    hour = data.get('hour', int((now % 86400) // 3600))

    score, decision, features = score_event(
        user_id=user_id,
        src_computer=data.get('src_computer', 'DEMO_PC'),
        dst_computer=data.get('dst_computer', 'CORP_SERVER'),
        auth_type=data.get('auth_type', 'NTLM'),
        logon_type=data.get('logon_type', 'Network'),
        hour=hour,
        time_val=data.get('time', now),
    )

    return jsonify({
        'score': round(score, 6),
        'decision': decision,
        'threshold': THRESHOLD,
    })


@app.route('/api/dashboard')
def api_dashboard():
    if _cached_dashboard is None:
        _precompute_dashboard()
    return jsonify(_cached_dashboard)


@app.route('/api/alerts')
def api_alerts():
    if _cached_alerts is None:
        _precompute_dashboard()
    return jsonify(_cached_alerts)


@app.route('/api/live_events')
def api_live_events():
    """Return the most recent live login events."""
    return jsonify(list(reversed(_live_events[-50:])))


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


@app.route('/api/users')
def api_users():
    """Stub: user list — replace with real UEBA data later."""
    return jsonify([])


@app.route('/api/stats')
def api_stats():
    """Stub: system stats — replace with real counters later."""
    return jsonify({'live_events': 0, 'alerts': 0, 'users': 0})


@app.route('/api/investigation/<int:alert_id>')
def api_investigation(alert_id):
    """Stub: investigation detail — replace with real analysis later."""
    return jsonify({})


@app.route('/api/alerts/<int:alert_id>/ack', methods=['POST'])
def api_ack_alert(alert_id):
    """Stub: acknowledge alert."""
    return jsonify({'ok': True})


@app.route('/api/reset', methods=['POST'])
def api_reset():
    """Stub: reset dashboard state."""
    return jsonify({'ok': True})


if __name__ == '__main__':
    print("loading scores...")
    _load_scores()
    print("pre-aggregating dashboard...")
    _precompute_dashboard()
    print("initializing scorer...")
    _init_scorer()
    print("starting server on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
