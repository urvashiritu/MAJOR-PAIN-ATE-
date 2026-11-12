"""File tailer for live authentication events.

Reads the same comma-separated format the LANL dataset uses:

    time,src_user,dst_user,src_computer,dst_computer,auth_type,logon_type,orientation,result

Example (verified against lanl.auth_slice):

    1,U1137@DOM1,U1137@DOM1,C1065,C1065,?,Network,LogOff,Success

Only new lines are processed by default, so the tailer behaves like a sensor:
drop a line in the file and it is scored. Set LANL_INGEST_FROM_END=0 to backfill
an existing file from the start.

The parser is deliberately strict. A malformed line is skipped and counted; it
never reaches the scorer.
"""
import os
import threading
import time

FIELDS = ('time', 'src_user', 'dst_user', 'src_computer', 'dst_computer',
          'auth_type', 'logon_type', 'orientation', 'result')

# Counters for observability and for verification.
stats = {
    'lines': 0,
    'scored': 0,
    'skipped': 0,
    'last_error': None,
    'last_line_at': None,
}


def parse_line(line):
    """Parse one LANL-format line. Returns a dict, or None if malformed."""
    line = (line or '').strip()
    if not line or line.startswith('#'):
        return None
    parts = line.split(',')
    if len(parts) != len(FIELDS):
        return None
    event = dict(zip(FIELDS, parts))
    try:
        event['time'] = int(event['time'])
    except (TypeError, ValueError):
        return None
    if not event.get('src_user'):
        return None
    return event


def _read_new_lines(path, offset):
    """Read from `offset` to EOF. Returns (lines, new_offset).

    A partial trailing line is left in the file: we only advance past complete
    newline-terminated lines, so a half-written record is not parsed early.
    """
    with open(path, 'rb') as f:
        f.seek(offset)
        data = f.read()
    if not data:
        return [], offset
    end = data.rfind(b'\n')
    if end == -1:
        return [], offset
    complete = data[:end + 1]
    return complete.decode('utf-8', errors='replace').splitlines(), offset + len(complete)


def tail(path, on_event, poll_interval=0.5, from_end=True, stop=None):
    """Blocking loop: call on_event(parsed_event) for every new line.

    `stop` is an optional threading.Event used to end the loop.
    """
    path = os.path.abspath(path)
    offset = 0
    if from_end and os.path.exists(path):
        offset = os.path.getsize(path)

    warned = 0
    while stop is None or not stop.is_set():
        if not os.path.exists(path):
            time.sleep(poll_interval)
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            time.sleep(poll_interval)
            continue
        if size < offset:          # file rotated or truncated
            offset = 0
        lines, offset = _read_new_lines(path, offset)
        for line in lines:
            stats['lines'] += 1
            event = parse_line(line)
            if event is None:
                stats['skipped'] += 1
                if warned < 5:
                    print(f"  ingest: skipped malformed line: {line[:120]!r}")
                    warned += 1
                continue
            stats['last_line_at'] = time.time()
            try:
                on_event(event)
            except Exception as exc:          # one bad event must not kill the tail
                stats['last_error'] = f"{type(exc).__name__}: {exc}"
                print(f"  ingest: scoring failed: {stats['last_error']}")
                continue
            stats['scored'] += 1
        time.sleep(poll_interval)


def start(path, on_event, poll_interval=0.5, from_end=True):
    """Start the tailer on a daemon thread. Returns (thread, stop_event)."""
    stop = threading.Event()
    thread = threading.Thread(
        target=tail,
        args=(path, on_event),
        kwargs={'poll_interval': poll_interval, 'from_end': from_end, 'stop': stop},
        daemon=True,
        name='lanl-ingest',
    )
    thread.start()
    return thread, stop
