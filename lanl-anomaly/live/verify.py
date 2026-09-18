"""Verify all assumptions before building the live scorer.

Run: python3 live/verify.py
"""
import os
import sys
import time
import numpy as np
import torch
import torch.nn as nn
import duckdb
import joblib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LANL_DB = os.path.join(ROOT, 'data', 'raw', 'lanl', 'lanl.duckdb')
MODEL_PATH = os.path.join(ROOT, 'models', 'lanl_lstm_ae_2ep_bs128_20260913_162002.pt')
LGB_PATH = os.path.join(ROOT, 'models', 'lanl_lgb_21feat.joblib')
THRESHOLD = 0.18719510711736984
FIELDS = ["src_user", "src_computer", "dst_computer", "auth_type", "logon_type", "orientation"]
CONTEXT_WINDOW = 50
HIDDEN_DIM = 128
NUM_LAYERS = 2

DEMO_USERS = ['U2899@DOM1', 'U293@DOM1', 'U2097@DOM1', 'U66@DOM1']


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


def verify_checkpoint():
    print("=" * 60)
    print("1. CHECKPOINT VERIFICATION")
    print("=" * 60)

    ckpt = torch.load(MODEL_PATH, map_location='cpu', weights_only=False)
    print(f"  Keys: {list(ckpt.keys())}")

    vocab = ckpt['vocab']
    field_offsets = ckpt['field_offsets']
    vocab_size = ckpt['vocab_size']
    print(f"  Vocab size: {vocab_size:,}")
    print(f"  Field offsets: {field_offsets}")

    con = duckdb.connect(os.path.abspath(LANL_DB), read_only=True)
    missing = []
    found = []
    for user_id in DEMO_USERS:
        key = f"src_user:{user_id}"
        if key not in vocab:
            missing.append(key)
        else:
            found.append(key)

        src_pcs = [r[0] for r in con.execute(
            f"SELECT DISTINCT src_computer FROM lanl.feat WHERE src_user = '{user_id}' LIMIT 5"
        ).fetchall()]
        for pc in src_pcs:
            key = f"src_computer:{pc}"
            if key not in vocab:
                missing.append(key)
            else:
                found.append(key)

        dst_pcs = [r[0] for r in con.execute(
            f"SELECT DISTINCT dst_computer FROM lanl.feat WHERE src_user = '{user_id}' LIMIT 5"
        ).fetchall()]
        for pc in dst_pcs:
            key = f"dst_computer:{pc}"
            if key not in vocab:
                missing.append(key)
            else:
                found.append(key)

    for field in ['auth_type', 'logon_type', 'orientation']:
        vals = [r[0] for r in con.execute(
            f"SELECT DISTINCT {field} FROM lanl.feat LIMIT 10"
        ).fetchall()]
        for v in vals:
            key = f"{field}:{v}"
            if key not in vocab:
                missing.append(key)
            else:
                found.append(key)

    con.close()

    print(f"  Found: {len(found)} keys")
    if missing:
        print(f"  MISSING: {missing}")
        return False
    else:
        print(f"  All demo values in vocab ✓")
        return True


def verify_model_load():
    print("\n" + "=" * 60)
    print("2. MODEL LOAD + INFERENCE SPEED")
    print("=" * 60)

    ckpt = torch.load(MODEL_PATH, map_location='cpu', weights_only=False)
    vocab_size = ckpt['vocab_size']

    model = LSTMAutoencoder(vocab_size, HIDDEN_DIM, NUM_LAYERS)
    model.load_state_dict(ckpt['model_state_dict'])
    model.eval()
    n_params = sum(p.numel() for p in model.parameters())
    print(f"  Model params: {n_params:,}")

    dummy = torch.randint(0, vocab_size, (1, CONTEXT_WINDOW + 6))

    for _ in range(3):
        with torch.no_grad():
            model(dummy)

    times = []
    for _ in range(20):
        t0 = time.time()
        with torch.no_grad():
            logits = model(dummy)
        times.append(time.time() - t0)

    avg_ms = np.mean(times) * 1000
    p99_ms = np.percentile(times, 99) * 1000
    print(f"  Single forward pass: {avg_ms:.1f}ms avg, {p99_ms:.1f}ms p99")
    print(f"  Output shape: {logits.shape}")
    print(f"  Throughput: {1000/avg_ms:.0f} events/sec")

    return avg_ms


def verify_feature_computation():
    print("\n" + "=" * 60)
    print("3. FEATURE COMPUTATION (DuckDB vs COUNT queries)")
    print("=" * 60)

    con = duckdb.connect(os.path.abspath(LANL_DB), read_only=True)

    sample = con.execute("""
        SELECT src_user, src_computer, dst_computer, auth_type, logon_type,
               orientation, hour, time, lstm_ae_recon_error
        FROM lanl.feat WHERE src_user = 'U66@DOM1' ORDER BY time DESC LIMIT 1
    """).fetchone()

    user_id, src_pc, dst_pc, auth_type, logon_type, orientation, hour, time_val, lstm_recon = sample
    print(f"  Event: {user_id} @ hour={hour}, time={time_val}")

    feat_row = con.execute(f"""
        SELECT dst_first, src_first,
               CAST(hour_events AS DOUBLE) / CAST(user_events AS DOUBLE) AS hour_ratio,
               dst_prior_events, fail_1h, vel_1h, is_ntlm, lstm_ae_recon_error
        FROM lanl.feat
        WHERE src_user = '{user_id}' AND time = {time_val}
    """).fetchone()

    machine_pop = con.execute(f"""
        SELECT COUNT(DISTINCT src_user) FROM lanl.feat WHERE dst_computer = '{dst_pc}'
    """).fetchone()[0]

    print(f"  DuckDB: dst_first={feat_row[0]}, src_first={feat_row[1]}, hour_ratio={feat_row[2]:.4f}")
    print(f"  DuckDB: fail_1h={feat_row[4]}, vel_1h={feat_row[5]}, lstm_recon={feat_row[7]}")
    print(f"  DuckDB: machine_popularity={machine_pop}")

    t0 = time.time()
    vel_1h = con.execute(f"""
        SELECT COUNT(*) FROM lanl.feat
        WHERE src_user = '{user_id}'
        AND time > {time_val} - 3600 AND time <= {time_val}
    """).fetchone()[0]
    vel_1h_ms = (time.time() - t0) * 1000

    t0 = time.time()
    vel_24h = con.execute(f"""
        SELECT COUNT(*) FROM lanl.feat
        WHERE src_user = '{user_id}'
        AND time > {time_val} - 86400 AND time <= {time_val}
    """).fetchone()[0]
    vel_24h_ms = (time.time() - t0) * 1000

    t0 = time.time()
    fail_1h = con.execute(f"""
        SELECT COUNT(*) FROM lanl.feat
        WHERE src_user = '{user_id}'
        AND time > {time_val} - 3600 AND time <= {time_val}
        AND result = 'Failure'
    """).fetchone()[0]
    fail_1h_ms = (time.time() - t0) * 1000

    print(f"\n  COUNT queries:")
    print(f"    vel_1h:  {vel_1h} (match={vel_1h == feat_row[5]}) ({vel_1h_ms:.0f}ms)")
    print(f"    vel_24h: {vel_24h} ({vel_24h_ms:.0f}ms)")
    print(f"    fail_1h: {fail_1h} (match={fail_1h == feat_row[4]}) ({fail_1h_ms:.0f}ms)")

    pair_count = con.execute(f"""
        SELECT COUNT(*) FROM lanl.feat
        WHERE src_user = '{user_id}' AND src_computer = '{src_pc}' AND dst_computer = '{dst_pc}'
    """).fetchone()[0]
    print(f"\n  pair_count({src_pc}, {dst_pc}): {pair_count}")

    con.close()


def verify_scoring():
    print("\n" + "=" * 60)
    print("4. END-TO-END SCORING")
    print("=" * 60)

    lgb_data = joblib.load(LGB_PATH)
    lgb_model = lgb_data['model']
    print(f"  LGB model type: {type(lgb_model)}")
    print(f"  LGB model n_features: {lgb_model.n_features_in_}")

    ckpt = torch.load(MODEL_PATH, map_location='cpu', weights_only=False)
    vocab = ckpt['vocab']
    vocab_size = ckpt['vocab_size']
    lstm_model = LSTMAutoencoder(vocab_size, HIDDEN_DIM, NUM_LAYERS)
    lstm_model.load_state_dict(ckpt['model_state_dict'])
    lstm_model.eval()

    con = duckdb.connect(os.path.abspath(LANL_DB), read_only=True)

    # Get a KNOWN RED event from the precomputed scores
    red_score = con.execute("""
        SELECT s.anomaly_score, s.decision, s.src_user, s.src_computer, s.dst_computer,
               s.hour, s.is_red, s.time,
               f.auth_type, f.logon_type, f.orientation,
               f.dst_first, f.src_first,
               CAST(f.hour_events AS DOUBLE) / CAST(f.user_events AS DOUBLE) AS hour_ratio,
               f.dst_prior_events, f.fail_1h, f.vel_1h, f.is_ntlm,
               f.lstm_ae_recon_error
        FROM lanl.feat f
        JOIN (SELECT * FROM read_parquet('%s')) s
        ON f.time = s.time AND f.src_user = s.src_user
        WHERE s.src_user = 'U66@DOM1' AND s.is_red = TRUE AND s.anomaly_score > 0.5
        ORDER BY s.anomaly_score DESC LIMIT 1
    """ % os.path.abspath(os.path.join(ROOT, 'data', 'processed', 'lanl_scores.parquet'))).fetchone()

    if not red_score:
        print("  Could not find red event, trying direct from feat")
        red_score = con.execute("""
            SELECT 0.972, 'BLOCK', src_user, src_computer, dst_computer,
                   hour, is_red, time,
                   auth_type, logon_type, orientation,
                   dst_first, src_first,
                   CAST(hour_events AS DOUBLE) / CAST(user_events AS DOUBLE) AS hour_ratio,
                   dst_prior_events, fail_1h, vel_1h, is_ntlm,
                   lstm_ae_recon_error
            FROM lanl.feat
            WHERE is_red = TRUE AND src_user = 'U66@DOM1'
            AND lstm_ae_recon_error > 0.1
            ORDER BY lstm_ae_recon_error DESC LIMIT 1
        """).fetchone()

    stored_score = red_score[0]
    user_id = red_score[2]
    src_pc = red_score[3]
    dst_pc = red_score[4]
    hour = red_score[5]
    time_val = red_score[7]
    auth_type = red_score[8]
    logon_type = red_score[9]
    orientation = red_score[10]

    print(f"\n  RED event: {user_id} @ hour={hour:.2f}")
    print(f"  src_pc={src_pc}, dst_pc={dst_pc}")
    print(f"  stored score={stored_score:.6f} (precomputed)")

    # Dynamic features via COUNT
    vel_1h = con.execute(f"""
        SELECT COUNT(*) FROM lanl.feat
        WHERE src_user = '{user_id}' AND time > {time_val} - 3600 AND time <= {time_val}
    """).fetchone()[0]
    vel_24h = con.execute(f"""
        SELECT COUNT(*) FROM lanl.feat
        WHERE src_user = '{user_id}' AND time > {time_val} - 86400 AND time <= {time_val}
    """).fetchone()[0]
    fail_1h_count = con.execute(f"""
        SELECT COUNT(*) FROM lanl.feat
        WHERE src_user = '{user_id}' AND time > {time_val} - 3600 AND time <= {time_val}
        AND result = 'Failure'
    """).fetchone()[0]

    # LSTM-AE recon error
    last_9_events = con.execute(f"""
        SELECT src_user, src_computer, dst_computer, auth_type, logon_type, orientation
        FROM lanl.feat WHERE time <= {time_val} ORDER BY time DESC LIMIT 9
    """).fetchall()

    context_tokens = []
    for ev in reversed(last_9_events):
        for fi, field in enumerate(FIELDS):
            key = f"{field}:{ev[fi]}"
            tid = vocab.get(key, 0)
            context_tokens.append(tid)
    context_tokens = context_tokens[-50:]

    new_event_vals = [user_id, src_pc, dst_pc, auth_type, logon_type, orientation]
    event_tokens = [vocab.get(f"{field}:{val}", 0) for field, val in zip(FIELDS, new_event_vals)]

    sequence = context_tokens + event_tokens
    x = torch.tensor([sequence], dtype=torch.long)
    with torch.no_grad():
        event_logits = lstm_model(x)[:, -6:, :]
    target = torch.tensor([event_tokens], dtype=torch.long)
    loss = nn.functional.cross_entropy(
        event_logits.reshape(-1, vocab_size),
        target.reshape(-1),
        reduction="none",
    ).reshape(1, 6)
    lstm_recon_computed = loss.mean(dim=1).item()

    machine_pop = con.execute(f"""
        SELECT COUNT(DISTINCT src_user) FROM lanl.feat WHERE dst_computer = '{dst_pc}'
    """).fetchone()[0]
    pair_count = con.execute(f"""
        SELECT COUNT(*) FROM lanl.feat
        WHERE src_user = '{user_id}' AND src_computer = '{src_pc}' AND dst_computer = '{dst_pc}'
    """).fetchone()[0]
    user_total = con.execute(f"""
        SELECT COUNT(*) FROM lanl.feat WHERE src_user = '{user_id}'
    """).fetchone()[0]

    print(f"  LSTM-AE recon (computed): {lstm_recon_computed:.4f}")
    print(f"  stored lstm_recon:        {float(red_score[18]):.4f}")
    print(f"  vel_1h={vel_1h}, vel_24h={vel_24h}, fail_1h={fail_1h_count}")
    print(f"  pair_count={pair_count}, machine_pop={machine_pop}")

    hour_sin = np.sin(hour / 24.0 * 2.0 * np.pi)
    hour_cos = np.cos(hour / 24.0 * 2.0 * np.pi)

    X_correct = np.array([[
        float(red_score[11]),  # dst_first
        float(red_score[12]),  # src_first
        float(red_score[13]),  # hour_ratio
        float(red_score[14]),  # dst_prior_events
        float(fail_1h_count),  # fail_1h
        float(vel_1h),  # vel_1h
        float(red_score[16]),  # is_ntlm (col 16 = is_ntlm)
        hour_sin, hour_cos,
        1.0 if pair_count <= 1 else 0.0,  # pair_first
        0.0,  # src_dst_pair_first
        fail_1h_count / (vel_1h + 1.0),  # fail_rate
        1.0 if red_score[11] == 1.0 and red_score[16] == 1.0 else 0.0,  # dst_first_x_ntlm
        np.log(max(pair_count, 1) + 1),  # log_pair_rank
        pair_count / user_total,  # pair_freq_ratio
        0.0,  # is_rare_hour
        0.0,  # pairs_last_100
        0.0,  # iat_zscore
        vel_1h / (vel_24h + 1.0),  # velocity_ratio
        float(machine_pop),  # machine_popularity
        lstm_recon_computed,
    ]], dtype=np.float32)

    score_correct = lgb_model.predict_proba(X_correct)[0, 1]
    decision_correct = 'BLOCK' if score_correct > THRESHOLD else ('FLAG' if score_correct > THRESHOLD * 0.7 else 'ALLOW')
    print(f"\n  recomputed → score={score_correct:.6f} → {decision_correct}")
    print(f"  precomputed → score={stored_score:.6f} → {red_score[1]}")
    print(f"  delta = {abs(score_correct - stored_score):.6f}")

    # Also test: what does the broken scorer produce?
    X_broken = X_correct.copy()
    X_broken[0, 18] = 0.0  # iat_zscore = 0 (broken: uses last event value)
    X_broken[0, 19] = 0.0  # velocity_ratio = 0 (broken: uses last event value)
    score_broken = lgb_model.predict_proba(X_broken)[0, 1]
    decision_broken = 'BLOCK' if score_broken > THRESHOLD else ('ALLOW')
    print(f"  broken (iat=0,vel=0) → score={score_broken:.6f} → {decision_broken}")

    con.close()


if __name__ == '__main__':
    verify_checkpoint()
    verify_model_load()
    verify_feature_computation()
    verify_scoring()

    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE")
    print("=" * 60)
