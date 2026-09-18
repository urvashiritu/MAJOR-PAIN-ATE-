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
_dst_prior_events = {}    # dst_computer → count
_rare_hours = {}          # src_user → set of hours
_seen_dst_computers = {}  # src_user → set
_seen_src_computers = {}  # src_user → set
_seen_pairs = {}          # src_user → set of (src, dst)
_seen_src_dst_pairs = set()

# Per-user state (incremental)
_pair_row_numbers = {}    # "user|src|dst" → int
_iat_history = {}         # src_user → deque of last 100 timestamps
_context_windows = {}     # src_user → deque of last 50 token ids
_last_timestamps = {}     # src_user → last event time


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
    global _rare_hours, _hour_histograms, _dst_prior_events
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
    _hour_histograms = {}
    for user, hour, cnt, cume in hour_rows:
        h = int(hour)
        if user not in _hour_histograms:
            _hour_histograms[user] = [0] * 24
        _hour_histograms[user][h] = cnt
        if cume <= 0.2:
            _rare_hours.setdefault(user, set()).add(h)

    _dst_prior_events = dict(con.execute(
        "SELECT dst_computer, COUNT(*) FROM lanl.feat GROUP BY dst_computer"
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
    times = [r[0] for r in con.execute(f"""
        SELECT time FROM lanl.feat WHERE src_user = '{user_id}'
        ORDER BY time DESC LIMIT 101
    """).fetchall()]
    _iat_history[user_id] = deque(reversed(times), maxlen=101)

    # Context window: last ~34 events (34*6=204 tokens, we keep last 50)
    context_events = con.execute(f"""
        SELECT src_user, src_computer, dst_computer, auth_type, logon_type, orientation
        FROM lanl.feat WHERE src_user = '{user_id}'
        ORDER BY time DESC LIMIT 34
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
        hour: 0-23
        time_val: unix timestamp

    Returns:
        (score: float, decision: str, features: dict)
    """
    # ── 1. O(1) set lookups ──
    dst_first = 1.0 if dst_computer not in _seen_dst_computers.get(user_id, set()) else 0.0
    src_first = 1.0 if src_computer not in _seen_src_computers.get(user_id, set()) else 0.0

    # ── 2. O(1) dict lookups ──
    user_total = _user_totals.get(user_id, 1)
    hour_hist = _hour_histograms.get(user_id, [0] * 24)
    h = int(hour) % 24
    hour_ratio = hour_hist[h] / user_total if user_total > 0 else 0.0
    dst_prior = _dst_prior_events.get(dst_computer, 0)
    machine_pop = float(_machine_pop.get(dst_computer, 1))

    # ── 3. Pair features ──
    pair_key = f"{user_id}|{src_computer}|{dst_computer}"
    src_dst_key = f"{src_computer}|{dst_computer}"

    pair_count = _pair_counts.get(pair_key, 0)
    pair_freq_ratio = pair_count / user_total if user_total > 0 else 0.0

    row_num = _pair_row_numbers.get(pair_key, 0)
    pair_first = 1.0 if row_num == 0 else 0.0
    log_pair_rank = math.log(row_num + 1)

    src_dst_pair_first = 1.0 if src_dst_key not in _seen_src_dst_pairs else 0.0

    is_rare = 1.0 if h in _rare_hours.get(user_id, set()) else 0.0
    pairs_last_100 = 0.0  # always 0 in training

    # ── 4. Auth features ──
    is_ntlm = 1.0 if auth_type == 'NTLM' else 0.0

    # ── 5. DuckDB COUNT queries (~11ms) ──
    con = duckdb.connect(os.path.abspath(LANL_DB), read_only=True)

    vel_fail = con.execute(f"""
        SELECT COUNT(*),
               COUNT(CASE WHEN result = 'Failure' THEN 1 END)
        FROM lanl.feat
        WHERE src_user = '{user_id}'
        AND time > {time_val} - 3600 AND time <= {time_val}
    """).fetchone()
    vel_1h = vel_fail[0]
    fail_1h = vel_fail[1]

    vel_24h = con.execute(f"""
        SELECT COUNT(*) FROM lanl.feat
        WHERE src_user = '{user_id}'
        AND time > {time_val} - 86400 AND time <= {time_val}
    """).fetchone()[0]

    con.close()

    # ── 6. Derived features ──
    fail_rate = fail_1h / (vel_1h + 1.0)
    dst_first_x_ntlm = dst_first * is_ntlm
    velocity_ratio = vel_1h / (vel_24h + 1.0)

    # ── 7. IAT z-score (~3ms for query + compute) ──
    iat_hist = _iat_history.get(user_id, deque())
    if len(iat_hist) >= 2:
        iats = [iat_hist[i] - iat_hist[i-1] for i in range(1, len(iat_hist))]
        iat_arr = np.array(iats, dtype=float)
        iat_mean = float(np.mean(iat_arr))
        iat_std = float(np.std(iat_arr)) + 1e-6
        new_iat = time_val - (iat_hist[-1] if iat_hist else time_val)
        iat_zscore = (new_iat - iat_mean) / iat_std
    else:
        iat_zscore = 0.0

    # ── 8. LSTM-AE recon error (~4.5ms) ──
    event_tokens = _tokenize_event(user_id, src_computer, dst_computer, auth_type, logon_type)
    lstm_recon = _compute_lstm_recon(user_id, event_tokens)

    # ── 9. Hour encoding ──
    hour_sin = math.sin(h / 24.0 * 2.0 * math.pi)
    hour_cos = math.cos(h / 24.0 * 2.0 * math.pi)

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
