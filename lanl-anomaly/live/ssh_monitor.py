"""Read live SSH authentication records from Linux Audit without scoring LANL data."""
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from datetime import datetime, timezone


_lock = threading.Lock()
_events = deque(maxlen=500)
_failures = deque(maxlen=500)
_started = False
_status = {
    'available': False,
    'state': 'stopped',
    'message': 'SSH audit collector has not started.',
}
_auditctl_state = 'not checked'
_event_number = 0
_THREAD = None
_STARTED_AT = 0.0
_CHECKPOINT = os.path.join(
    tempfile.gettempdir(), f'lanl-ssh-audit-{os.getpid()}.checkpoint')
_RECORD_RE = re.compile(
    r'type=USER_AUTH\s+msg=audit\((\d+(?:\.\d+)?):(\d+)\):\s*(.*)')
_FIELD_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)=("(?:\\.|[^"])*"|\S+)')


def _fields(raw):
    result = {}
    for key, value in _FIELD_RE.findall(raw):
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1].replace('\\"', '"').replace('\\\\', '\\')
        result[key] = value
    return result


def _set_status(state, message, available=False):
    with _lock:
        _status.update(available=available, state=state, message=message)


def _record(line):
    global _event_number
    match = _RECORD_RE.search(line)
    if not match:
        return
    raw_ts, serial, payload = match.groups()
    kind = 'USER_AUTH'
    fields = _fields(payload)
    # PAM audit messages are the source of authentication outcomes. Ignore
    # unrelated USER_AUTH records from other services.
    if fields.get('terminal') not in ('ssh', 'ssh:', 'ssh-session') and 'sshd' not in fields.get('exe', ''):
        return
    try:
        stamp = float(raw_ts)
    except ValueError:
        return
    if stamp < _STARTED_AT:
        return

    result = fields.get('res', '').lower()
    success = result in ('success', 'yes', '1')
    source = fields.get('addr', '')
    if source in ('', '?', 'unset'):
        source = 'Unknown'
    username = fields.get('acct', 'Unknown')
    now = time.time()
    with _lock:
        while _failures and now - _failures[0][0] > 300:
            _failures.popleft()
        if not success:
            _failures.append((now, source))
            count = sum(1 for _, ip in _failures if ip == source)
        else:
            count = 0
        _event_number += 1
        brute_force = not success and count >= 5
        event = {
            'id': f'{serial}-{kind}-{_event_number}',
            'ts': datetime.fromtimestamp(stamp, timezone.utc).astimezone().isoformat(timespec='seconds'),
            'source_ip': source,
            'username': username,
            'audit_type': kind,
            'result': 'SUCCESS' if success else 'FAILED',
            'classification': 'BRUTE FORCE' if brute_force else ('ACCEPTED' if success else 'FAILED LOGIN'),
            'failure_count_5m': count,
            'message': (f'{count} failed attempts from this IP in 5 minutes'
                        if brute_force else ('SSH authentication succeeded' if success
                                             else 'SSH authentication failed')),
        }
        _events.append(event)


def _collect():
    global _auditctl_state
    if not shutil.which('ausearch'):
        _set_status('unavailable', 'ausearch is not installed. Install the Linux audit tools.')
        return
    if not shutil.which('auditctl'):
        _set_status('unavailable', 'auditctl is not installed. Install the Linux audit tools.')
        return

    # auditctl reports whether kernel auditing is enabled. Reading audit
    # records still happens through ausearch; the Flask app never changes
    # host-wide audit rules.
    try:
        audit_state = subprocess.run(['auditctl', '-s'], capture_output=True,
                                     text=True, timeout=5)
        if audit_state.returncode == 0:
            enabled = re.search(r'^enabled\s+(\d+)', audit_state.stdout, re.M)
            _auditctl_state = ('enabled' if enabled and int(enabled.group(1)) >= 1
                               else 'disabled')
        else:
            _auditctl_state = 'permission unavailable'
    except (OSError, subprocess.TimeoutExpired):
        _auditctl_state = 'unavailable'
    if _auditctl_state == 'disabled':
        _set_status('audit_disabled', 'Kernel auditing is disabled. Enable it with auditctl before collecting SSH events.')
        return

    first = True
    while True:
        cmd = ['ausearch', '--input-logs', '--message', 'USER_AUTH',
               '--checkpoint', _CHECKPOINT, '--format', 'raw']
        if first:
            cmd += ['--start', 'recent']
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as exc:
            _set_status('error', f'Could not read Linux Audit events: {exc}')
            time.sleep(3)
            continue
        first = False
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or 'audit log read failed').strip()
            _set_status('needs_privilege', detail[:240])
            time.sleep(3)
            continue
        for line in proc.stdout.splitlines():
            _record(line)
        note = 'Reading SSH authentication records from Linux Audit.'
        if _auditctl_state == 'permission unavailable':
            note += ' auditctl status needs elevated audit access; log reading is available.'
        _set_status('connected', note, True)
        time.sleep(1)


def start():
    """Start the dedicated audit reader once; it never touches LANL events."""
    global _started, _STARTED_AT, _THREAD
    with _lock:
        if _started:
            return
        _started = True
        _STARTED_AT = time.time()
    _THREAD = threading.Thread(target=_collect, name='ssh-audit-reader', daemon=True)
    _THREAD.start()


def snapshot():
    with _lock:
        return {
            **_status,
            'auditctl': _auditctl_state,
            'events': list(_events),
            'brute_force_threshold': 5,
            'window_seconds': 300,
        }
