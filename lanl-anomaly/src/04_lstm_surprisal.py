"""LSTM surprisal scorer for LANL auth events.

Trains a small LSTM language model on BENIGN auth sequences.
Computes per-event surprisal (cross-entropy loss) for ALL events.
Outputs surprisal scores to DuckDB as a new column on feat table.

Tokenization: each event = 6 tokens (src_user, src_computer, dst_computer,
auth_type, logon_type, orientation). Each field gets its own ID range.

Usage:
  python src/04_lstm_surprisal.py              # train + score all events
  python src/04_lstm_surprisal.py --epochs 1   # quick test
  python src/04_lstm_surprisal.py --dry-run 10000  # run on first N events only
"""
import argparse
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
BATCH_SIZE = 64
DEFAULT_EPOCHS = 2
LR = 0.001


class SeqDataset(Dataset):
    def __init__(self, ids, window):
        self.ids = ids
        self.window = window

    def __len__(self):
        return len(self.ids) - self.window

    def __getitem__(self, idx):
        x = self.ids[idx:idx + self.window]
        y = self.ids[idx + 1:idx + self.window + 1]
        return x.copy(), y.copy()


class SurprisalLSTM(nn.Module):
    def __init__(self, vocab_size, hidden_dim=128, num_layers=2):
        super().__init__()
        self.embed = nn.Embedding(vocab_size, hidden_dim)
        self.lstm = nn.LSTM(hidden_dim, hidden_dim, num_layers=num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_dim, vocab_size)

    def forward(self, x):
        return self.fc(self.lstm(self.embed(x))[0])


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


def compute_surprisal(model, tokens, is_red, vocab_size, ctx, device, batch_size):
    n_events = len(is_red)
    scores = np.zeros(n_events, dtype=np.float32)
    model.eval()
    criterion = nn.CrossEntropyLoss()

    with torch.no_grad():
        for start in range(0, n_events, batch_size):
            end = min(start + batch_size, n_events)
            bs = end - start

            contexts = np.zeros((bs, ctx), dtype=np.int32)
            targets = np.zeros((bs, 6), dtype=np.int32)
            for i in range(bs):
                tok_start = (start + i) * 6
                ctx_start = max(0, tok_start - ctx)
                c = tokens[ctx_start:tok_start]
                if len(c) < ctx:
                    c = np.concatenate([np.zeros(ctx - len(c), dtype=np.int32), c])
                contexts[i] = c
                targets[i] = tokens[tok_start:tok_start + 6]

            x = torch.from_numpy(contexts).to(device)
            t = torch.from_numpy(targets).to(device).long()

            logits = model(x)[:, -1, :]  # (bs, vocab_size)

            # Per-event loss: mean cross-entropy over 6 target tokens
            event_losses = torch.zeros(bs, device=device)
            for j in range(6):
                pe = nn.functional.cross_entropy(logits, t[:, j], reduction='none')
                event_losses += pe
            event_losses /= 6.0
            scores[start:end] = event_losses.cpu().numpy()

            if (start // batch_size) % 50 == 0:
                print(f"    {end/n_events*100:5.1f}% ({end:,}/{n_events:,})")

    return scores


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    ap.add_argument("--dry-run", type=int, default=0)
    ap.add_argument("--lr", type=float, default=LR)
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    ap.add_argument("--max-train", type=int, default=500_000, help="Max benign events for training")
    args = ap.parse_args()

    if os.environ.get("FORCE_CPU"):
        device = torch.device("cpu")
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    t0 = time.time()
    limit = args.dry_run if args.dry_run > 0 else None
    con = duckdb.connect(args.db)

    print("Building vocabulary...")
    vocab, field_offsets, vocab_size = build_vocab_from_db(con, limit=None)  # always full vocab
    print(f"  Vocab size: {vocab_size:,}")

    print(f"Loading tokens{' (dry-run: ' + str(limit) + ')' if limit else ''}...")
    tokens, is_red = load_tokens_and_reds(con, field_offsets, limit)
    n_events = len(is_red)
    print(f"  {n_events:,} events, {is_red.sum():,} red")
    print(f"  Loaded in {time.time()-t0:.1f}s")

    print("Loading rowids for DuckDB update...")
    rowids = load_rowids(con, limit)
    con.close()

    # Benign tokens for training (subsample to max_train events)
    benign_event_idx = np.where(~is_red)[0]
    if len(benign_event_idx) > args.max_train:
        rng = np.random.RandomState(42)
        benign_event_idx = rng.choice(benign_event_idx, size=args.max_train, replace=False)
    benign_flat = np.concatenate([np.arange(i*6, i*6+6) for i in benign_event_idx])
    benign_tokens = tokens[benign_flat]
    print(f"  Benign events for training: {len(benign_event_idx):,} ({len(benign_tokens):,} tokens)")

    # Train
    train_ds = SeqDataset(benign_tokens, CONTEXT_WINDOW)
    train_dl = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=0, pin_memory=True)
    print(f"  Train samples: {len(train_ds):,}")

    model = SurprisalLSTM(vocab_size, HIDDEN_DIM, NUM_LAYERS).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"  Model params: {n_params:,} ({n_params * 4 / 1024**2:.1f} MB)")

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    criterion = nn.CrossEntropyLoss()

    print(f"\nTraining for {args.epochs} epochs...")
    model.train()
    for epoch in range(args.epochs):
        ep_loss = 0.0
        n_batches = 0
        t_ep = time.time()
        for x, y in train_dl:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            logits = model(x)
            loss = criterion(logits.reshape(-1, vocab_size), y.reshape(-1).long())
            loss.backward()
            optimizer.step()
            ep_loss += loss.item()
            n_batches += 1
        print(f"  Epoch {epoch+1}/{args.epochs}: loss={ep_loss/n_batches:.4f} ({time.time()-t_ep:.1f}s)")

    # Compute surprisal
    print("\nComputing surprisal scores...")
    surprisal_scores = compute_surprisal(model, tokens, is_red, vocab_size, CONTEXT_WINDOW, device, args.batch_size)

    # Stats
    red_s = surprisal_scores[is_red]
    ben_s = surprisal_scores[~is_red]
    print(f"\nSurprisal stats:")
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
        print("\nSaving surprisal to DuckDB...")
        con = duckdb.connect(args.db)
        has_col = con.execute(
            "SELECT count(*) FROM information_schema.columns WHERE table_name='feat' AND column_name='lstm_surprisal'"
        ).fetchone()[0]
        if not has_col:
            con.execute("ALTER TABLE feat ADD COLUMN lstm_surprisal DOUBLE")

        con.execute("CREATE TABLE _map(rid INTEGER, score DOUBLE)")
        INSERT_BATCH = 500_000
        for i in range(0, len(rowids), INSERT_BATCH):
            chunk_r = rowids[i:i + INSERT_BATCH]
            chunk_s = surprisal_scores[i:i + INSERT_BATCH]
            con.executemany("INSERT INTO _map VALUES (?, ?)", list(zip(chunk_r, chunk_s.tolist())))

        con.execute("""
            UPDATE feat SET lstm_surprisal = m.score
            FROM _map m WHERE feat.rowid = m.rid
        """)
        con.execute("DROP TABLE _map")
        con.close()

        con = duckdb.connect(args.db)
        n_null = con.execute("SELECT COUNT(*) FROM feat WHERE lstm_surprisal IS NULL").fetchone()[0]
        n_red_null = con.execute("SELECT COUNT(*) FROM feat WHERE is_red AND lstm_surprisal IS NULL").fetchone()[0]
        sample = con.execute("SELECT lstm_surprisal FROM feat WHERE is_red LIMIT 5").fetchall()
        con.close()

        print(f"\nVerification:")
        print(f"  NULL lstm_surprisal: {n_null:,} (should be 0)")
        print(f"  NULL on red events:  {n_red_null:,} (should be 0)")
        print(f"  Sample red scores: {[f'{s[0]:.4f}' for s in sample]}")

    # Save model
    model_dir = os.path.join(ROOT, "models") if os.path.isdir(os.path.join(ROOT, "models")) else ROOT
    model_path = os.path.join(model_dir, "lanl_lstm_surprisal.pt")
    torch.save({
        "model_state_dict": model.state_dict(),
        "vocab": vocab,
        "field_offsets": field_offsets,
        "vocab_size": vocab_size,
    }, model_path)
    print(f"  Model saved: {model_path}")
    print(f"\nTotal time: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
