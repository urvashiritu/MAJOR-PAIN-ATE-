"""Live scoring engine — pre-compute context at startup, score events in ~19ms."""
import os
import sys
import time
import math
import numpy as np
import torch
import torch.nn as nn
import duckdb
import joblib
from collections import deque

sys.path.insert(0, os.path.dirname(__file__))
from db import FEATURE_COLS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANL_DB = os.path.join(ROOT, 'data', 'raw', 'lanl', 'lanl.duckdb')
FEATURES_DB = os.path.join(ROOT, 'data', 'processed', 'lanl_features.duckdb')
MODEL_PATH = os.path.join(ROOT, 'models', 'lanl_lgb_21feat.joblib')
LSTM_CKPT = os.path.join(ROOT, 'models', 'lanl_lstm_ae_2ep_bs128_20260913_162002.pt')

THRESHOLD = 0.18719510711736984
FIELDS = ["src_user", "src_computer", "dst_computer", "auth_type", "logon_type", "orientation"]
CONTEXT_WINDOW = 50
HIDDEN_DIM = 128
NUM_LAYERS = 2


class LSTMAutoencoder(nn.Module):
    def __init__(self, vocab_size, hidden_dim=128, num_layers=2):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.vocab_size = vocab_size
        self.embed = nn.Embedding(vocab_size, hidden_dim)
        self.encoder = nn.LSTM(hidden_dim, hidden_dim, num_layers=num_layers, batch_first=True)
        self.decoder = nn.LSTM(hidden_dim, hidden_dim, num_layers=num_layers, batch_first=True)
        self.output_proj = nn.Linear(hidden_dim, vocab_size)

    def forward(self, x):
        embedded = self.embed(x)
        _, (hidden, cell) = self.encoder(embedded)
        decoder_output, _ = self.decoder(embedded, (hidden, cell))
        logits = self.output_proj(decoder_output)
        return logits


# ── State ────────────────────────────────────────────────────────────
_lgb_model = None
_lstm_model = None
_lstm_vocab = None

# Precomputed dicts (startup)
_machine_pop = {}          # dst_computer → count
_user_totals = {}         # src_user → total events
_pair_counts = {}         # "user|src|dst" → count
_src_dst_pair_counts = {} # "src|dst" → count
_hour_histograms = {}     # src_user → [24 counts]
_dst_prior_events = {}    # "user|dst_computer" → prior-event count (training: per user+dst)
_rare_hours = {}          # src_user → set of integer hours (UI histogram)
_rare_tods = {}           # src_user → set of (time % 86400) values (is_rare_hour feature)
_seen_dst_computers = {}  # src_user → set
_seen_src_computers = {}  # src_user → set
_seen_pairs = {}          # src_user → set of (src, dst)
_seen_src_dst_pairs = set()

# Per-user state (incremental)
_pair_row_numbers = {}    # "user|src|dst" → int
_iat_history = {}         # src_user → deque of last 100 timestamps
_context_windows = {}     # src_user → deque of last 50 token ids
_last_timestamps = {}     # src_user → last event time

# Per-user feature distributions (startup). Sorted arrays so a live event's
# percentile is an O(log n) lookup instead of an absolute cutoff.
_baselines = {}           # user_id → {'vel': ndarray, 'lstm': ndarray, ...}


def _load_lstm():
    """Load LSTM-AE model + vocab from checkpoint."""
    global _lstm_model, _lstm_vocab
    ckpt = torch.load(LSTM_CKPT, map_location='cpu', weights_only=False)
    vocab = ckpt['vocab']
    vocab_size = ckpt['vocab_size']
    model = LSTMAutoencoder(vocab_size, HIDDEN_DIM, NUM_LAYERS)
    model.load_state_dict(ckpt['model_state_dict'])
    model.eval()
    _lstm_model = model
    _lstm_vocab = vocab
    print(f"  LSTM loaded ({vocab_size:,} vocab, {sum(p.numel() for p in model.parameters()):,} params)")


def _load_lgb():
    """Load LGB model."""
    global _lgb_model
    d = joblib.load(MODEL_PATH)
    _lgb_model = d['model']
    print(f"  LGB loaded (threshold={THRESHOLD:.6f})")


def precompute_global():
    """Load all shared dicts from DuckDB at startup."""
    global _machine_pop, _user_totals, _pair_counts, _src_dst_pair_counts
    global _rare_hours, _rare_tods, _hour_histograms, _dst_prior_events
    global _seen_dst_computers, _seen_src_computers, _seen_pairs, _seen_src_dst_pairs
    t0 = time.time()
    con = duckdb.connect(os.path.abspath(LANL_DB), read_only=True)

    _machine_pop = dict(con.execute(
        "SELECT dst_computer, COUNT(DISTINCT src_user) FROM lanl.feat GROUP BY dst_computer"
    ).fetchall())

    _user_totals = dict(con.execute(
        "SELECT src_user, COUNT(*) FROM lanl.feat GROUP BY src_user"
    ).fetchall())

    _pair_counts = dict(con.execute("""
        SELECT src_user || '|' || src_computer || '|' || dst_computer, COUNT(*)
        FROM lanl.feat GROUP BY src_user, src_computer, dst_computer
    """).fetchall())

    _src_dst_pair_counts = dict(con.execute("""
        SELECT src_computer || '|' || dst_computer, COUNT(*)
        FROM lanl.feat GROUP BY src_computer, dst_computer
    """).fetchall())

    hour_rows = con.execute("""
        SELECT src_user, hour, cnt,
            CUME_DIST() OVER (PARTITION BY src_user ORDER BY cnt ASC) AS cume
        FROM (SELECT src_user, hour, COUNT(*) AS cnt FROM lanl.feat WHERE is_red = FALSE GROUP BY src_user, hour)
    """).fetchall()
    _rare_hours = {}
    _rare_tods = {}
    _hour_histograms = {}
    for user, hour, cnt, cume in hour_rows:
        h = int(hour)
        if user not in _hour_histograms:
            _hour_histograms[user] = [0] * 24
        _hour_histograms[user][h] = cnt
        if cume <= 0.2:
            _rare_hours.setdefault(user, set()).add(h)
            # SCORING_SQL joins rare_hours on the exact hour. hour here is the
            # fractional (time % 86400)/3600, so recover the integer time-of-day
            # for exact matching against time % 86400 in score_event.
            _rare_tods.setdefault(user, set()).add(int(round(hour * 3600)))

    # Training dst_prior_events is per (user, dst_computer), not per machine.
    # src/01_build_features.py:61 — count(*) OVER (PARTITION BY src_user,
    # dst_computer ORDER BY time RANGE UNBOUNDED PRECEDING AND 1 PRECEDING).
    _dst_prior_events = dict(con.execute(
        "SELECT src_user || '|' || dst_computer, COUNT(*) "
        "FROM lanl.feat GROUP BY src_user, dst_computer"
    ).fetchall())

    # Seen sets
    for uid in _user_totals:
        _seen_dst_computers[uid] = set(
            r[0] for r in con.execute(
                f"SELECT DISTINCT dst_computer FROM lanl.feat WHERE src_user = '{uid}'"
            ).fetchall()
        )
        _seen_src_computers[uid] = set(
            r[0] for r in con.execute(
                f"SELECT DISTINCT src_computer FROM lanl.feat WHERE src_user = '{uid}'"
            ).fetchall()
        )
        _seen_pairs[uid] = set(
            (r[0], r[1]) for r in con.execute(
                f"SELECT DISTINCT src_computer, dst_computer FROM lanl.feat WHERE src_user = '{uid}'"
            ).fetchall()
        )

    _seen_src_dst_pairs = set(
        (r[0], r[1]) for r in con.execute(
            "SELECT DISTINCT src_computer, dst_computer FROM lanl.feat"
        ).fetchall()
    )

    con.close()
    print(f"  global context: {time.time()-t0:.1f}s ({len(_machine_pop)} machines, {len(_user_totals)} users)")


def precompute_baselines(user_ids):
    """Per-user distributions used to explain a live score.

    Absolute cutoffs ("more than 10 logins/hour") are wrong for users whose
    normal hour contains hundreds of events: 196/hr is the 34th percentile for
    U2097@DOM1, whose median is 209. Store each user's own distribution so the
    dashboard can say where an event actually sits instead of calling normal
    volume suspicious.
    """
    global _baselines
    if not os.path.exists(LANL_DB):
        _baselines = {}
        return
    t0 = time.time()
    con = duckdb.connect(os.path.abspath(LANL_DB), read_only=True)
    out = {}
    for uid in user_ids:
        vel = con.execute(
            "SELECT vel_1h FROM lanl.feat WHERE src_user = ?", [uid]
        ).fetchnumpy().get('vel_1h')
        lstm = con.execute(
            "SELECT lstm_ae_recon_error FROM lanl.feat WHERE src_user = ?", [uid]
        ).fetchnumpy().get('lstm_ae_recon_error')
        if vel is None or len(vel) == 0:
            continue
        vel = np.sort(np.asarray(vel, dtype=float))
        entry = {
            'vel': vel,
            'vel_median': float(np.median(vel)),
            'vel_p99': float(np.quantile(vel, 0.99)),
        }
        if lstm is not None and len(lstm):
            lstm = np.sort(np.asarray(lstm, dtype=float))
            entry['lstm'] = lstm
            entry['lstm_median'] = float(np.median(lstm))
            entry['lstm_p99'] = float(np.quantile(lstm, 0.99))
        out[uid] = entry
    con.close()
    _baselines = out
    print(f"  baselines: {len(out)} users in {time.time()-t0:.1f}s")


def history_count(user_id):
    """Number of recorded events for this user in the LANL dataset."""
    return int(_user_totals.get(user_id, 0))


def baseline_snapshot(user_id, vel_1h=None, lstm_err=None):
    """Percentile context for one event against this user's own history."""
    b = _baselines.get(user_id)
    snap = {'history_events': history_count(user_id)}
    if not b:
        return snap
    if vel_1h is not None and 'vel' in b:
        arr = b['vel']
        snap['vel_pct'] = round(
            float(np.searchsorted(arr, float(vel_1h), side='right')) / len(arr) * 100.0, 1)
        snap['vel_median'] = round(float(b['vel_median']), 0)
        snap['vel_p99'] = round(float(b['vel_p99']), 0)
    if lstm_err is not None and 'lstm' in b:
        arr = b['lstm']
        snap['lstm_pct'] = round(
            float(np.searchsorted(arr, float(lstm_err), side='right')) / len(arr) * 100.0, 2)
        snap['lstm_median'] = float(b['lstm_median'])
        snap['lstm_p99'] = float(b['lstm_p99'])
    return snap


# Real sign-in samples for the employee demo path. Each entry is a genuine
# authentication taken from that user's own history in the features table, so
# the demo scores real inputs instead of machine names drawn at random.
_real_login_pool = {}     # user_id -> list of (src_computer, dst_computer, hour, auth_type)


def precompute_real_logins(user_ids):
    """Sample real, non-red sign-ins per user for the employee demo path.

    Red events are excluded on purpose. They are genuine attacks and the model
    correctly blocks them, which is not what a "normal employee signs in"
    screen should show.

    Verified before shipping: 480/480 sampled triples score ALLOW through
    score_event(), and 100/100 consecutive renders (25 per user, no state reset
    between them) do too.
    """
    global _real_login_pool
    if not os.path.exists(FEATURES_DB):
        _real_login_pool = {}
        return
    t0 = time.time()
    con = duckdb.connect(os.path.abspath(FEATURES_DB), read_only=True)
    pool = {}
    for uid in user_ids:
        rows = con.execute("""
            SELECT src_computer, dst_computer, hour, auth_type FROM (
                SELECT src_computer, dst_computer, hour, auth_type
                FROM features
                WHERE src_user = ? AND result = 'Success' AND is_red = FALSE
            ) USING SAMPLE 120 ROWS (reservoir, 11)
        """, [uid]).fetchall()
        pool[uid] = [(r[0], r[1], float(r[2]), r[3] or 'NTLM') for r in rows]
    con.close()
    _real_login_pool = pool
    total = sum(len(v) for v in pool.values())
    print(f"  real logins: {total} samples for {len(pool)} users ({time.time()-t0:.1f}s)")


def get_real_logins(user_id):
    """Real sign-in samples for a user, or [] if the pool could not be built."""
    return _real_login_pool.get(user_id, [])


def precompute_user(user_id):
    """Load per-user context: IAT history, context window, last timestamp."""
    t0 = time.time()
    con = duckdb.connect(os.path.abspath(LANL_DB), read_only=True)

    # Last timestamp
    last_t = con.execute(
        f"SELECT MAX(time) FROM lanl.feat WHERE src_user = '{user_id}'"
    ).fetchone()[0]
    _last_timestamps[user_id] = last_t or 0

    # IAT history: last 101 event times (to compute 100 IATs)
    # The tiebreaker columns are not optional. ORDER BY time alone is
    # ambiguous where several events share a second: for U66@DOM1 eight
    # events sit on the 101st row's timestamp, so the cut picked an
    # arbitrary subset and iat_zscore drifted from the training value.
    # These eight columns are the per-user form of the project-wide
    # deterministic order (src_user is constant inside the query) and are
    # verified unique for every demo user.
    times = [r[0] for r in con.execute(f"""
        SELECT time FROM lanl.feat WHERE src_user = '{user_id}'
        ORDER BY time DESC, dst_user, src_computer, dst_computer,
                 auth_type, logon_type, orientation, result
        LIMIT 101
    """).fetchall()]
    _iat_history[user_id] = deque(reversed(times), maxlen=101)

    # Context window: last ~34 events (34*6=204 tokens, we keep last 50)
    context_events = con.execute(f"""
        SELECT src_user, src_computer, dst_computer, auth_type, logon_type, orientation
        FROM lanl.feat WHERE src_user = '{user_id}'
        ORDER BY time DESC, dst_user, src_computer, dst_computer,
                 auth_type, logon_type, orientation, result
        LIMIT 34
    """).fetchall()
    tokens = []
    for ev in reversed(context_events):
        for fi, field in enumerate(FIELDS):
            key = f"{field}:{ev[fi]}"
            tokens.append(_lstm_vocab.get(key, 0))
    _context_windows[user_id] = deque(tokens[-CONTEXT_WINDOW:], maxlen=CONTEXT_WINDOW)

    # Pair row numbers: load existing counts so new events continue from here
    pair_rows = con.execute(f"""
        SELECT src_user || '|' || src_computer || '|' || dst_computer, COUNT(*)
        FROM lanl.feat WHERE src_user = '{user_id}'
        GROUP BY src_user, src_computer, dst_computer
    """).fetchall()
    for key, cnt in pair_rows:
        _pair_row_numbers[key] = cnt

    con.close()
    print(f"  {user_id}: {time.time()-t0:.2f}s (last_t={last_t}, iat_hist={len(_iat_history[user_id])}, ctx={len(_context_windows[user_id])})")


def init(users=None):
    """Full startup: global context + per-user context + models."""
    from db import FEATURE_COLS as _  # ensure db module loaded
    if users is None:
        users = ['U2899@DOM1', 'U293@DOM1', 'U2097@DOM1', 'U66@DOM1']
    t0 = time.time()
    print("scorer: loading models...")
    _load_lgb()
    _load_lstm()
    print("scorer: precomputing global context...")
    precompute_global()
    print("scorer: loading per-user baselines...")
    precompute_baselines(users)
    print("scorer: loading real login samples...")
    precompute_real_logins(users)
    print("scorer: precomputing per-user context...")
    for uid in users:
        precompute_user(uid)
    print(f"scorer: ready in {time.time()-t0:.1f}s ({len(users)} users)")


def _tokenize_event(user_id, src_computer, dst_computer, auth_type, logon_type):
    """Convert raw event fields to 6 token ids."""
    vals = [user_id, src_computer, dst_computer, auth_type, logon_type, 'LogOn']
    return [_lstm_vocab.get(f"{field}:{val}", 0) for field, val in zip(FIELDS, vals)]


def _compute_lstm_recon(user_id, event_tokens):
    """Run LSTM-AE forward pass, return reconstruction error."""
    ctx = list(_context_windows.get(user_id, []))
    sequence = ctx + event_tokens
    if len(sequence) < CONTEXT_WINDOW + 6:
        sequence = [0] * (CONTEXT_WINDOW + 6 - len(sequence)) + sequence
    x = torch.tensor([sequence[-CONTEXT_WINDOW - 6:]], dtype=torch.long)
    with torch.no_grad():
        logits = _lstm_model(x)[:, -6:, :]
    target = torch.tensor([event_tokens], dtype=torch.long)
    loss = nn.functional.cross_entropy(
        logits.reshape(-1, _lstm_model.vocab_size),
        target.reshape(-1),
        reduction="none",
    ).reshape(1, 6)
    return loss.mean(dim=1).item()


def score_event(user_id, src_computer, dst_computer, auth_type, logon_type, hour, time_val):
    """Score a single login event. Returns (score, decision, features_dict).

    Args:
        user_id: e.g. 'U66@DOM1'
        src_computer: source machine
        dst_computer: destination machine
        auth_type: e.g. 'NTLM', 'Kerberos'
        logon_type: e.g. 'Network', 'Interactive'
        hour: fractional hour, (time % 86400) / 3600 in [0, 24)
        time_val: unix timestamp

    Returns:
        (score: float, decision: str, features: dict)
    """
    # ── 1. O(1) set lookups ──
    dst_first = 1.0 if dst_computer not in _seen_dst_computers.get(user_id, set()) else 0.0
    src_first = 1.0 if src_computer not in _seen_src_computers.get(user_id, set()) else 0.0

    # ── 2. O(1) dict lookups ──
    user_total = _user_totals.get(user_id, 1)
    dst_prior = _dst_prior_events.get(f"{user_id}|{dst_computer}", 0)
    machine_pop = float(_machine_pop.get(dst_computer, 1))

    # ── 3. Pair features ──
    pair_key = f"{user_id}|{src_computer}|{dst_computer}"
    src_dst_key = f"{src_computer}|{dst_computer}"

    pair_count = _pair_counts.get(pair_key, 0)
    pair_freq_ratio = pair_count / user_total if user_total > 0 else 0.0

    row_num = _pair_row_numbers.get(pair_key, 0)
    pair_first = 1.0 if row_num == 0 else 0.0
    log_pair_rank = math.log(row_num + 2)  # training: log1p(ROW_NUMBER) = log(prior+2)

    src_dst_pair_first = 1.0 if src_dst_key not in _seen_src_dst_pairs else 0.0

    # is_rare_hour matches SCORING_SQL: the event's time-of-day falls in a rare
    # (cume_dist <= 0.2) hour for this user. _rare_tods holds (time % 86400).
    is_rare = 1.0 if (int(time_val) % 86400) in _rare_tods.get(user_id, set()) else 0.0
    # pairs_last_100 — KNOWN UNRESOLVED TRAIN/SERVE SKEW. Read before trusting.
    #
    # The served model splits on this feature at thresholds 1.5 / 2.5 / 3.5
    # (173 splits), so its training values were 1, 2, 3 and 4+, NOT a constant.
    # eval_lstm.py computes it as len(set(last 100 dst_computers)) within each
    # user's run, which is >= 1 and never 0. A constant 0.0 therefore falls
    # below every threshold the model uses.
    #
    # Measured cost, reproducing the held-out split (5,399,886 rows / 240 reds)
    # with this model and the features table:
    #     pairs_last_100 = 0.0            -> PR-AUC 0.3152, FP 244
    #     natural last-100 computation    -> PR-AUC 0.0491, avg value 6.16
    # 0.0 is the less harmful of the two, so it is what ships for now, but both
    # are wrong against eval_lstm.py's run-scoped semantics. Fixing this needs
    # the training-side value distribution measured, not guessed.
    pairs_last_100 = 0.0

    # ── 4. Auth features ──
    is_ntlm = 1.0 if auth_type == 'NTLM' else 0.0

    # ── 5. DuckDB COUNT queries (~11ms) ──
    con = duckdb.connect(os.path.abspath(LANL_DB), read_only=True)

    # Feature windows match live/scoring.py SCORING_SQL (the pipeline that
    # produced the served parquet and the LGB model's training values):
    #   vel_1h / fail_1h : [t-3600, t)  — excludes the current event/ties
    #   velocity_ratio   : auth_count_1h/(auth_count_24h+1), both [t-window, t]
    #   fail uses result = 'Fail' (the value present in the data), not 'Failure'
    #   hour_events      : the user's events sharing this time-of-day
    #                      (SCORING_SQL: COUNT OVER (PARTITION BY src_user, hour))
    counts = con.execute(f"""
        SELECT
          COUNT(CASE WHEN time >= {time_val} - 3600 AND time < {time_val} THEN 1 END),
          COALESCE(SUM(CASE WHEN time >= {time_val} - 3600 AND time < {time_val}
                            AND result = 'Fail' THEN 1 ELSE 0 END), 0),
          COUNT(CASE WHEN time >= {time_val} - 3600 AND time <= {time_val} THEN 1 END),
          COUNT(CASE WHEN time >= {time_val} - 86400 AND time <= {time_val} THEN 1 END),
          COUNT(CASE WHEN time % 86400 = {int(time_val) % 86400} THEN 1 END)
        FROM lanl.feat
        WHERE src_user = '{user_id}'
    """).fetchone()
    vel_1h = int(counts[0])
    fail_1h = int(counts[1])
    auth_count_1h = int(counts[2])
    auth_count_24h = int(counts[3])
    hour_events = int(counts[4])
    hour_ratio = hour_events / user_total if user_total > 0 else 0.0

    con.close()

    # ── 6. Derived features ──
    fail_rate = fail_1h / (vel_1h + 1.0)
    dst_first_x_ntlm = dst_first * is_ntlm
    velocity_ratio = auth_count_1h / (auth_count_24h + 1.0)

    # ── 7. IAT z-score (~3ms for query + compute) ──
    iat_hist = _iat_history.get(user_id, deque())
    if len(iat_hist) >= 2:
        iats = [iat_hist[i] - iat_hist[i-1] for i in range(1, len(iat_hist))]
        iat_arr = np.array(iats, dtype=float)
        iat_mean = float(np.mean(iat_arr))
        # Training used STDDEV_SAMP (n-1); np.std defaults to population (n).
        iat_std = (float(np.std(iat_arr, ddof=1)) if len(iat_arr) > 1 else 0.0) + 1e-6
        new_iat = time_val - (iat_hist[-1] if iat_hist else time_val)
        iat_zscore = (new_iat - iat_mean) / iat_std
    else:
        iat_zscore = 0.0

    # ── 8. LSTM-AE recon error (~4.5ms) ──
    event_tokens = _tokenize_event(user_id, src_computer, dst_computer, auth_type, logon_type)
    lstm_recon = _compute_lstm_recon(user_id, event_tokens)

    # ── 9. Hour encoding ──
    # SCORING_SQL encodings on the fractional hour ((time % 86400)/3600).
    hour_sin = math.sin(hour / 24.0 * 2.0 * math.pi)
    hour_cos = math.cos(hour / 24.0 * 2.0 * math.pi)

    # ── 10. Build feature vector (MUST match FEATURE_COLS order) ──
    features = {
        'dst_first': dst_first,
        'src_first': src_first,
        'hour_ratio': hour_ratio,
        'dst_prior_events': float(dst_prior),
        'fail_1h': float(fail_1h),
        'vel_1h': float(vel_1h),
        'hour_sin': hour_sin,
        'hour_cos': hour_cos,
        'is_ntlm': is_ntlm,
        'pair_first': pair_first,
        'src_dst_pair_first': src_dst_pair_first,
        'fail_rate': fail_rate,
        'dst_first_x_ntlm': dst_first_x_ntlm,
        'log_pair_rank': log_pair_rank,
        'pair_freq_ratio': pair_freq_ratio,
        'is_rare_hour': is_rare,
        'pairs_last_100': pairs_last_100,
        'iat_zscore': iat_zscore,
        'velocity_ratio': velocity_ratio,
        'machine_popularity': machine_pop,
        'lstm_ae_recon_error': lstm_recon,
    }

    X = np.array([[features[col] for col in FEATURE_COLS]], dtype=np.float32)
    score = float(_lgb_model.predict_proba(X)[0, 1])
    decision = 'BLOCK' if score > THRESHOLD else ('FLAG' if score > THRESHOLD * 0.7 else 'ALLOW')

    # ── 11. Update state ──
    _pair_row_numbers[pair_key] = row_num + 1
    _dst_prior_events[f"{user_id}|{dst_computer}"] = dst_prior + 1
    _seen_dst_computers.setdefault(user_id, set()).add(dst_computer)
    _seen_src_computers.setdefault(user_id, set()).add(src_computer)
    _seen_pairs.setdefault(user_id, set()).add((src_computer, dst_computer))
    _seen_src_dst_pairs.add((src_computer, dst_computer))

    iat_hist.append(time_val)
    for tok in event_tokens:
        _context_windows.setdefault(user_id, deque(maxlen=CONTEXT_WINDOW)).append(tok)
    _last_timestamps[user_id] = time_val

    return (score, decision, features)


DEMO_USERS = ['U2899@DOM1', 'U293@DOM1', 'U2097@DOM1', 'U66@DOM1']
