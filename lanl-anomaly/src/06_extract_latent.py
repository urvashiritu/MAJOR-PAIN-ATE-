"""Extract LSTM-AE latent features + PCA → DuckDB.

Loads trained LSTM-AE, runs encode() on all 29.9M events to get 128-dim
latent vectors, fits PCA 128→16 on a subsample, transforms all events,
writes 16 columns (latent_0..latent_15) to DuckDB feat table.

Memory strategy:
  - Fit PCA on 1M events (~512 MB latent vectors)
  - Transform all events in batches of 100k (~51 MB latent vectors)
  - Never hold more than ~600 MB of latent vectors at once

Usage:
  python src/06_extract_latent.py --model models/lanl_lstm_ae_2ep_bs128_20260913_162002.pt
  python src/06_extract_latent.py --model path/to/model.pt --dry-run 10000
"""
import argparse
import datetime
import time
import os
import numpy as np
import pandas as pd
import duckdb
import torch
import torch.nn as nn
from sklearn.decomposition import IncrementalPCA

try:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    ROOT = os.getcwd()

DB_PATH = os.path.join(ROOT, "data", "raw", "lanl", "lanl.duckdb")

FIELDS = ["src_user", "src_computer", "dst_computer", "auth_type", "logon_type", "orientation"]
CONTEXT_WINDOW = 50
HIDDEN_DIM = 128
NUM_LAYERS = 2
INFER_BATCH = 512
PCA_DIMS = 16
PCA_FIT_SAMPLES = 1_000_000


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

    def encode(self, x):
        embedded = self.embed(x)
        _, (hidden, cell) = self.encoder(embedded)
        return hidden[-1]


def build_vocab_from_db(con):
    vocab = {}
    offset = 0
    field_offsets = {}
    for field in FIELDS:
        field_offsets[field] = offset
        vals = [r[0] for r in con.execute(f"SELECT DISTINCT {field} FROM feat ORDER BY {field}").fetchall()]
        for val in vals:
            vocab[f"{field}:{val}"] = offset
            offset += 1
    return vocab, field_offsets, offset


def load_tokens_and_reds(con, field_offsets, limit=None):
    n = con.execute("SELECT COUNT(*) FROM feat").fetchone()[0]
    if limit:
        n = min(n, limit)
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


def extract_latent_batch(model, tokens, event_indices, ctx, device, batch_size):
    """Extract latent vectors for a set of event indices."""
    n = len(event_indices)
    latent = np.zeros((n, HIDDEN_DIM), dtype=np.float32)
    seq_len = ctx + 6

    model.eval()
    use_amp = device.type == "cuda"

    with torch.no_grad():
        for start in range(0, n, batch_size):
            end = min(start + batch_size, n)
            bs = end - start

            event_starts = (event_indices[start:end].astype(np.int64) * 6)
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

            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_amp):
                z = model.encode(x)

            latent[start:end] = z.float().cpu().numpy()

    return latent


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True, help="Path to trained LSTM-AE .pt file")
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--batch-size", type=int, default=INFER_BATCH)
    ap.add_argument("--dry-run", type=int, default=0)
    ap.add_argument("--pca-dims", type=int, default=PCA_DIMS)
    ap.add_argument("--pca-fit-samples", type=int, default=PCA_FIT_SAMPLES)
    args = ap.parse_args()

    if os.environ.get("FORCE_CPU"):
        device = torch.device("cpu")
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    t0 = time.time()
    timings = []
    limit = args.dry_run if args.dry_run > 0 else None

    # Load model
    t_step = time.time()
    print(f"Loading model from {args.model}...")
    ckpt = torch.load(args.model, map_location=device, weights_only=False)
    vocab_size = ckpt["vocab_size"]
    field_offsets = ckpt["field_offsets"]
    model = LSTMAutoencoder(vocab_size, HIDDEN_DIM, NUM_LAYERS).to(device)
    model.load_state_dict(ckpt["model_state_dict"])
    n_params = sum(p.numel() for p in model.parameters())
    print(f"  Vocab size: {vocab_size:,}")
    print(f"  Model params: {n_params:,}")
    del ckpt
    timings.append(("Model load", time.time() - t_step))

    # Load tokens
    t_step = time.time()
    con = duckdb.connect(args.db)
    tokens, is_red = load_tokens_and_reds(con, field_offsets, limit)
    n_events = len(is_red)
    print(f"  {n_events:,} events, {is_red.sum():,} red")
    timings.append(("Token loading", time.time() - t_step))

    # Load rowids
    t_step = time.time()
    rowids = load_rowids(con, limit)
    con.close()
    timings.append(("Rowid loading", time.time() - t_step))

    # Determine PCA fit subset
    n_pca_fit = min(args.pca_fit_samples, n_events)
    pca_rng = np.random.RandomState(42)
    pca_indices = np.sort(pca_rng.choice(n_events, size=n_pca_fit, replace=False))
    print(f"  PCA fit subset: {n_pca_fit:,} events")

    # Extract latent vectors for PCA fit
    t_step = time.time()
    print(f"\nExtracting latent vectors for PCA fitting ({n_pca_fit:,} events)...")
    pca_latent = extract_latent_batch(model, tokens, pca_indices, CONTEXT_WINDOW, device, args.batch_size)
    print(f"  Latent shape: {pca_latent.shape}")
    timings.append(("Latent extraction (PCA fit)", time.time() - t_step))

    # Fit PCA
    t_step = time.time()
    print(f"\nFitting PCA {HIDDEN_DIM} → {args.pca_dims}...")
    pca = IncrementalPCA(n_components=args.pca_dims, batch_size=10_000)
    pca.fit(pca_latent)
    explained = pca.explained_variance_ratio_.sum()
    print(f"  Explained variance: {explained:.4f} ({explained*100:.1f}%)")
    del pca_latent
    import gc; gc.collect()
    timings.append(("PCA fit", time.time() - t_step))

    # Extract ALL latent vectors and transform through PCA in batches
    t_step = time.time()
    print(f"\nExtracting latent vectors for all {n_events:,} events...")
    all_pca = np.zeros((n_events, args.pca_dims), dtype=np.float32)
    all_indices = np.arange(n_events)

    for batch_start in range(0, n_events, 100_000):
        batch_end = min(batch_start + 100_000, n_events)
        batch_idx = all_indices[batch_start:batch_end]

        latent_batch = extract_latent_batch(model, tokens, batch_idx, CONTEXT_WINDOW, device, args.batch_size)
        pca_batch = pca.transform(latent_batch)
        all_pca[batch_start:batch_end] = pca_batch

        elapsed_pct = batch_end / n_events * 100
        print(f"    {elapsed_pct:5.1f}% ({batch_end:,}/{n_events:,})")

    timings.append(("Latent extraction + PCA transform", time.time() - t_step))

    # Free GPU memory
    del tokens
    if device.type == "cuda":
        torch.cuda.empty_cache()
    import gc; gc.collect()

    if limit:
        print(f"\n[Dry-run] Skipping DuckDB write — results in all_pca array only.")
    else:
        # Write to DuckDB
        t_step = time.time()
        print(f"\nWriting {args.pca_dims} latent features to DuckDB...")
        con = duckdb.connect(args.db)

        # Add columns if they don't exist
        for i in range(args.pca_dims):
            col_name = f"latent_{i}"
            has_col = con.execute(
                f"SELECT count(*) FROM information_schema.columns WHERE table_name='feat' AND column_name='{col_name}'"
            ).fetchone()[0]
            if not has_col:
                con.execute(f"ALTER TABLE feat ADD COLUMN {col_name} DOUBLE")

        # Write via pandas batched UPDATE (no temp table needed)
        rowids_arr = np.array(rowids, dtype=np.int64)
        set_clause = ', '.join(f'{c} = _batch.{c}' for c in [f'latent_{i}' for i in range(args.pca_dims)])

        write_batch = 1_000_000
        for start in range(0, n_events, write_batch):
            end = min(start + write_batch, n_events)
            df = pd.DataFrame({
                'rid': rowids_arr[start:end],
                **{f'latent_{i}': all_pca[start:end, i] for i in range(args.pca_dims)}
            })
            con.execute(f"""
                UPDATE feat SET {set_clause}
                FROM df _batch WHERE feat.rowid = _batch.rid
            """)
            elapsed_pct = end / n_events * 100
            print(f"    {elapsed_pct:5.1f}% ({end:,}/{n_events:,})")
        con.close()
        timings.append(("DuckDB write", time.time() - t_step))

        # Verify
        t_step = time.time()
        con = duckdb.connect(args.db)
        n_null = con.execute(
            f"SELECT COUNT(*) FROM feat WHERE latent_0 IS NULL"
        ).fetchone()[0]
        sample = con.execute(
            f"SELECT {', '.join(f'latent_{i}' for i in range(args.pca_dims))} FROM feat WHERE is_red LIMIT 3"
        ).fetchall()
        con.close()
        timings.append(("Verification", time.time() - t_step))

        print(f"\nVerification:")
        print(f"  NULL latent_0: {n_null:,} (should be 0)")
        print(f"  Sample red rows:")
        if sample:
            for row in sample:
                print(f"    {[f'{v:.4f}' if v is not None else 'NULL' for v in row]}")
        else:
            print(f"    (no red rows found)")

    # Timing summary
    total = time.time() - t0
    print(f"\n{'=' * 50}")
    print(f"TIMING BREAKDOWN")
    print(f"{'=' * 50}")
    for label, dt in timings:
        print(f"  {label:<40} {dt:>7.1f}s")
    print(f"  {'─' * 48}")
    print(f"  {'Total':<40} {total:>7.1f}s")
    print(f"  PCA explained variance: {explained:.4f} ({explained*100:.1f}%)")
    print(f"  Output columns: latent_0..latent_{args.pca_dims-1}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
