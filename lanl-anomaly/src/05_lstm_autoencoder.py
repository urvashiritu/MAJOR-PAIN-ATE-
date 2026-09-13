"""LSTM Autoencoder scorer for LANL auth events.

Trains an LSTM Autoencoder on BENIGN auth sequences.
Computes per-event reconstruction error for ALL events.
Outputs scores to DuckDB as a new column on feat table.

Architecture (based on DabLog paper, arxiv 2012.13972):
  - Encoder: Embedding → 2-layer LSTM → latent vector
  - Decoder: RepeatVector → 2-layer LSTM → Linear → reconstructed logits
  - Anomaly score: cross-entropy loss per event (reconstruction error)

Tokenization: same as 04_lstm_surprisal.py (ENUM tokenization, 6 fields per event).

Usage:
  python src/05_lstm_autoencoder.py                          # train + score all events
  python src/05_lstm_autoencoder.py --model path/to/model.pt # load trained model, skip training
  python src/05_lstm_autoencoder.py --dry-run 10000          # run on first N events only
"""
import argparse
import datetime
import time
import os
import numpy as np
import duckdb
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

# Works in both terminal and Colab notebooks
try:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    ROOT = os.getcwd()

DB_PATH = os.path.join(ROOT, "data", "raw", "lanl", "lanl.duckdb")
if not os.path.exists(DB_PATH):
    DB_PATH = os.path.join(ROOT, "lanl.duckdb")  # Colab: /content/lanl.duckdb

FIELDS = ["src_user", "src_computer", "dst_computer", "auth_type", "logon_type", "orientation"]
CONTEXT_WINDOW = 50
HIDDEN_DIM = 128
NUM_LAYERS = 2
TRAIN_BATCH = 128
INFER_BATCH = 512
DEFAULT_EPOCHS = 2
LR = 0.001


class SeqDataset(Dataset):
    """Sliding window dataset for autoencoder training.
    
    Input and target are the SAME sequence (reconstruction, not prediction).
    """
    def __init__(self, ids, window):
        self.ids = ids
        self.window = window

    def __len__(self):
        return len(self.ids) - self.window

    def __getitem__(self, idx):
        x = self.ids[idx:idx + self.window].copy()
        return x, x.copy()  # input == target for autoencoder


class LSTMAutoencoder(nn.Module):
    """LSTM Autoencoder for sequence anomaly detection.
    
    Encoder compresses the sequence into a fixed-length latent vector.
    Decoder reconstructs the original sequence from the latent vector.
    Anomaly score = reconstruction error per event.
    """
    def __init__(self, vocab_size, hidden_dim=128, num_layers=2):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.vocab_size = vocab_size
        
        # Encoder
        self.embed = nn.Embedding(vocab_size, hidden_dim)
        self.encoder = nn.LSTM(hidden_dim, hidden_dim, num_layers=num_layers, 
                               batch_first=True)
        
        # Decoder
        self.decoder = nn.LSTM(hidden_dim, hidden_dim, num_layers=num_layers, 
                               batch_first=True)
        self.output_proj = nn.Linear(hidden_dim, vocab_size)

    def forward(self, x):
        """Forward pass: encode then reconstruct.
        
        Args:
            x: (batch, seq_len) token indices
        Returns:
            logits: (batch, seq_len, vocab_size) reconstructed logits
        """
        # Encode
        embedded = self.embed(x)  # (batch, seq_len, hidden_dim)
        _, (hidden, cell) = self.encoder(embedded)  # hidden: (num_layers, batch, hidden_dim)
        
        # Decode: use encoder's final hidden state to initialize decoder
        # Decoder input is the embedded sequence (teacher forcing during training)
        decoder_output, _ = self.decoder(embedded, (hidden, cell))
        logits = self.output_proj(decoder_output)  # (batch, seq_len, vocab_size)
        return logits

    def encode(self, x):
        """Get latent representation (for analysis/debugging)."""
        embedded = self.embed(x)
        _, (hidden, cell) = self.encoder(embedded)
        return hidden[-1]  # (batch, hidden_dim) — last layer's hidden state


def build_vocab_from_db(con, limit=None):
    vocab = {}
    offset = 0
    field_offsets = {}
    for field in FIELDS:
        field_offsets[field] = offset
        sql = f"SELECT DISTINCT {field} FROM feat ORDER BY {field}"
        if limit:
            sql += f" LIMIT {limit}"
        vals = [r[0] for r in con.execute(sql).fetchall()]
        for val in vals:
            vocab[f"{field}:{val}"] = offset
            offset += 1
    return vocab, field_offsets, offset


def load_tokens_and_reds(con, field_offsets, limit=None):
    count_sql = "SELECT COUNT(*) FROM feat"
    if limit:
        count_sql = f"SELECT COUNT(*) FROM (SELECT 1 FROM feat ORDER BY time, rowid LIMIT {limit})"
    n = con.execute(count_sql).fetchone()[0]
    print(f"  Loading {n:,} events with ENUM tokenization...")

    for field in FIELDS:
        con.execute(f"""
            CREATE OR REPLACE TYPE {field}_enum AS ENUM (
                SELECT DISTINCT {field} FROM feat ORDER BY {field}
            )
        """)

    rank_exprs = []
    for field in FIELDS:
        rank_exprs.append(
            f"enum_code({field}::{field}_enum) + {field_offsets[field]} AS {field}_id"
        )
    rank_exprs.append("is_red")

    query = f"SELECT {', '.join(rank_exprs)} FROM feat ORDER BY time, rowid"
    if limit:
        query = f"SELECT * FROM ({query}) LIMIT {limit}"

    data = con.execute(query).fetchnumpy()
    tokens = np.column_stack([data[f"{f}_id"] for f in FIELDS]).astype(np.int32)
    is_red = data["is_red"].astype(bool)

    for field in FIELDS:
        con.execute(f"DROP TYPE IF EXISTS {field}_enum")

    return tokens.reshape(-1), is_red


def load_rowids(con, limit=None):
    sql = "SELECT rowid AS rid FROM feat ORDER BY time, rowid"
    if limit:
        sql += f" LIMIT {limit}"
    return con.execute(sql).fetchnumpy()['rid'].tolist()


def compute_reconstruction_error(model, tokens, is_red, vocab_size, ctx, device, batch_size):
    """
    Compute reconstruction error (anomaly score) per event.
    
    For each event, we:
    1. Build a context window of length ctx ending before the event
    2. Append the event's 6 tokens
    3. Run through the autoencoder
    4. Compute cross-entropy loss on the event's 6 token positions
    5. Average the 6 losses → one score per event
    """
    n_events = len(is_red)
    scores = np.zeros(n_events, dtype=np.float32)

    model.eval()
    use_amp = device.type == "cuda"

    # We need ctx previous tokens + 6 event tokens
    seq_len = ctx + 6

    with torch.no_grad():
        for start in range(0, n_events, batch_size):
            end = min(start + batch_size, n_events)
            bs = end - start

            # Build context + event tokens (same as 04_lstm_surprisal.py)
            event_starts = (np.arange(start, end, dtype=np.int64) * 6)
            ctx_starts = np.maximum(0, event_starts - ctx)

            contexts = np.zeros((bs, ctx), dtype=np.int32)

            for k in range(ctx):
                src_idx = event_starts - ctx + k
                valid = src_idx >= 0
                if valid.any():
                    contexts[valid, k] = tokens[src_idx[valid]]

            event_tokens = tokens[event_starts[:, None] + np.arange(6)].astype(np.int32)
            sequence = np.concatenate([contexts, event_tokens], axis=1)

            x = torch.from_numpy(sequence).to(device=device, dtype=torch.long)

            # Target is the SAME sequence (autoencoder reconstructs input)
            target = x.clone()

            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_amp):
                logits = model(x)  # (batch, seq_len, vocab_size)

                # Cross entropy over all positions, but we only care about
                # the last 6 (the event tokens)
                event_logits = logits[:, -6:, :]  # (bs, 6, vocab_size)
                event_target = target[:, -6:]      # (bs, 6)

                loss = nn.functional.cross_entropy(
                    event_logits.reshape(-1, vocab_size),
                    event_target.reshape(-1),
                    reduction="none",
                ).reshape(bs, 6)

                event_losses = loss.mean(dim=1)

            scores[start:end] = event_losses.float().cpu().numpy()

            if (start // batch_size) % 50 == 0:
                elapsed_pct = end / n_events * 100
                print(f"    {elapsed_pct:5.1f}% ({end:,}/{n_events:,})")

    return scores


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    ap.add_argument("--dry-run", type=int, default=0)
    ap.add_argument("--lr", type=float, default=LR)
    ap.add_argument("--train-batch", type=int, default=TRAIN_BATCH)
    ap.add_argument("--batch-size", type=int, default=INFER_BATCH, help="Inference batch size")
    ap.add_argument("--max-train", type=int, default=500_000, help="Max benign events for training")
    ap.add_argument("--model", type=str, default=None, help="Load saved model .pt, skip training")
    args = ap.parse_args()

    if os.environ.get("FORCE_CPU"):
        device = torch.device("cpu")
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"VRAM: {vram:.1f} GB")

    t0 = time.time()
    timings = []
    limit = args.dry_run if args.dry_run > 0 else None
    use_amp = device.type == "cuda"

    if args.model:
        # Load from saved .pt — skip vocab build + training
        t_step = time.time()
        print(f"Loading model from {args.model}...")
        ckpt = torch.load(args.model, map_location=device, weights_only=False)
        vocab = ckpt["vocab"]
        field_offsets = ckpt["field_offsets"]
        vocab_size = ckpt["vocab_size"]
        model = LSTMAutoencoder(vocab_size, HIDDEN_DIM, NUM_LAYERS).to(device)
        model.load_state_dict(ckpt["model_state_dict"])
        n_params = sum(p.numel() for p in model.parameters())
        print(f"  Vocab size: {vocab_size:,}")
        print(f"  Model params: {n_params:,} ({n_params * 4 / 1024**2:.1f} MB)")
        timings.append(("Model load", time.time() - t_step))
    else:
        # Train from scratch
        con = duckdb.connect(args.db)

        t_step = time.time()
        print("Building vocabulary...")
        vocab, field_offsets, vocab_size = build_vocab_from_db(con, limit=None)
        print(f"  Vocab size: {vocab_size:,}")
        timings.append(("Vocab build", time.time() - t_step))
        con.close()

    t_step = time.time()
    con = duckdb.connect(args.db)
    print(f"Loading tokens{' (dry-run: ' + str(limit) + ')' if limit else ''}...")
    tokens, is_red = load_tokens_and_reds(con, field_offsets, limit)
    n_events = len(is_red)
    print(f"  {n_events:,} events, {is_red.sum():,} red")
    timings.append(("Token loading", time.time() - t_step))

    t_step = time.time()
    print("Loading rowids for DuckDB update...")
    rowids = load_rowids(con, limit)
    con.close()
    timings.append(("Rowid loading", time.time() - t_step))

    if not args.model:
        # Benign tokens for training (subsample to max_train events)
        t_step = time.time()
        benign_event_idx = np.where(~is_red)[0]
        if len(benign_event_idx) > args.max_train:
            rng = np.random.RandomState(42)
            benign_event_idx = rng.choice(benign_event_idx, size=args.max_train, replace=False)
        benign_flat = np.concatenate([np.arange(i*6, i*6+6) for i in benign_event_idx])
        benign_tokens = tokens[benign_flat]
        print(f"  Benign events for training: {len(benign_event_idx):,} ({len(benign_tokens):,} tokens)")
        timings.append(("Train prep", time.time() - t_step))

        # Train
        train_ds = SeqDataset(benign_tokens, CONTEXT_WINDOW)
        train_dl = DataLoader(train_ds, batch_size=args.train_batch, shuffle=True, num_workers=0, pin_memory=(device.type == 'cuda'))
        print(f"  Train samples: {len(train_ds):,} (batch={args.train_batch})")

        model = LSTMAutoencoder(vocab_size, HIDDEN_DIM, NUM_LAYERS).to(device)
        n_params = sum(p.numel() for p in model.parameters())
        print(f"  Model params: {n_params:,} ({n_params * 4 / 1024**2:.1f} MB)")

        optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
        criterion = nn.CrossEntropyLoss()

        print(f"\nTraining for {args.epochs} epochs...")
        t_train_total = 0.0
        model.train()
        for epoch in range(args.epochs):
            ep_loss = 0.0
            n_batches = 0
            t_ep = time.time()
            for x, y in train_dl:
                x = x.to(device, non_blocking=True)
                y = y.to(device, non_blocking=True)
                optimizer.zero_grad()
                with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_amp):
                    logits = model(x)
                    loss = criterion(logits.reshape(-1, vocab_size), y.reshape(-1).long())
                loss.backward()
                optimizer.step()
                ep_loss += loss.item()
                n_batches += 1
            ep_time = time.time() - t_ep
            t_train_total += ep_time
            print(f"  Epoch {epoch+1}/{args.epochs}: loss={ep_loss/n_batches:.4f} ({ep_time:.1f}s)")
        timings.append((f"Training ({args.epochs} epochs)", t_train_total))

        # Free training memory before scoring
        del train_dl, train_ds, benign_tokens, x, y
        if device.type == "cuda":
            torch.cuda.empty_cache()
    else:
        print(f"\n[Skipping training — loaded from {args.model}]")

    # Compute reconstruction error
    t_step = time.time()
    print("\nComputing reconstruction error scores...")
    recon_scores = compute_reconstruction_error(model, tokens, is_red, vocab_size, CONTEXT_WINDOW, device, args.batch_size)
    score_time = time.time() - t_step
    events_per_sec = n_events / score_time
    timings.append((f"Scoring ({n_events:,} events)", score_time))

    # Stats
    red_s = recon_scores[is_red]
    ben_s = recon_scores[~is_red]
    print(f"\nReconstruction error stats:")
    print(f"  Benign: mean={ben_s.mean():.4f}, p95={np.percentile(ben_s, 95):.4f}")
    if len(red_s) > 0:
        print(f"  Red:    mean={red_s.mean():.4f}, p95={np.percentile(red_s, 95):.4f}")
        thresh = np.percentile(ben_s, 95)
        print(f"  Red > benign p95: {(red_s > thresh).sum()}/{len(red_s)} ({(red_s > thresh).mean()*100:.1f}%)")
    else:
        print(f"  Red:    (none in this run)")

    if limit:
        print(f"\n[Dry-run] Skipping DuckDB write + verification.")
    else:
        t_step = time.time()
        print("\nSaving reconstruction error to DuckDB...")
        con = duckdb.connect(args.db)
        has_col = con.execute(
            "SELECT count(*) FROM information_schema.columns WHERE table_name='feat' AND column_name='lstm_ae_recon_error'"
        ).fetchone()[0]
        if not has_col:
            con.execute("ALTER TABLE feat ADD COLUMN lstm_ae_recon_error DOUBLE")

        rowids_arr = np.array(rowids, dtype=np.int32)
        con.execute("DROP TABLE IF EXISTS _map")
        con.execute("""
            CREATE TABLE _map AS
            SELECT unnest($1)::INTEGER AS rid, unnest($2)::DOUBLE AS score
        """, [rowids_arr, recon_scores.astype(np.float64)])

        con.execute("""
            UPDATE feat SET lstm_ae_recon_error = m.score
            FROM _map m WHERE feat.rowid = m.rid
        """)
        con.execute("DROP TABLE _map")
        con.close()
        timings.append(("DuckDB write", time.time() - t_step))

        t_step = time.time()
        con = duckdb.connect(args.db)
        n_null = con.execute("SELECT COUNT(*) FROM feat WHERE lstm_ae_recon_error IS NULL").fetchone()[0]
        n_red_null = con.execute("SELECT COUNT(*) FROM feat WHERE is_red AND lstm_ae_recon_error IS NULL").fetchone()[0]
        sample = con.execute("SELECT lstm_ae_recon_error FROM feat WHERE is_red LIMIT 5").fetchall()
        con.close()
        timings.append(("Verification", time.time() - t_step))

        print(f"\nVerification:")
        print(f"  NULL lstm_ae_recon_error: {n_null:,} (should be 0)")
        print(f"  NULL on red events:       {n_red_null:,} (should be 0)")
        print(f"  Sample red scores:        {[f'{s[0]:.4f}' for s in sample]}")

    t_step = time.time()
    model_dir = os.path.join(ROOT, "models") if os.path.isdir(os.path.join(ROOT, "models")) else ROOT
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    model_path = os.path.join(model_dir, f"lanl_lstm_ae_{args.epochs}ep_bs{args.train_batch}_{timestamp}.pt")
    if not args.model:
        torch.save({
            "model_state_dict": model.state_dict(),
            "vocab": vocab,
            "field_offsets": field_offsets,
            "vocab_size": vocab_size,
        }, model_path)
        print(f"  Model saved: {model_path}")
    timings.append(("Model save", time.time() - t_step))

    # Timing summary
    total = time.time() - t0
    print(f"\n{'=' * 50}")
    print(f"TIMING BREAKDOWN")
    print(f"{'=' * 50}")
    for label, dt in timings:
        print(f"  {label:<30} {dt:>7.1f}s")
    print(f"  {'─' * 38}")
    print(f"  {'Total':<30} {total:>7.1f}s")
    if "Scoring" in timings[0][0] or any("Scoring" in t[0] for t in timings):
        print(f"  {'Throughput':<30} {events_per_sec:>7.0f} events/s")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
