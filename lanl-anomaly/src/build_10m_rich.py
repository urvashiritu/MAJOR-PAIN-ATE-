#!/usr/bin/env python3
"""Build ~10M rich slice from 29M feat.parquet — 104 bad + ~100 normal full-history, ~10M total.

Rich = per-user full history kept, not random rows, so dst_first/fail_1h etc. stay honest.
Strategy:
 - red_users = distinct src_user from redteam.txt (104) — keep all their events (19.5M in slice but we cap heavy hitters)
 - normal pool = distinct U###@DOM1 from feat.parquet excluding red_users — sample ~100 with seed 42
 - heavy hitter cap: per-user max 100k events (keeps 702 reds, avoids U66 11M blowing 5M budget)
  - output: data/raw/lanl/feat_10m.parquet (~10M rows), with original 18 cols
 - verbosity: psutil + df before/after, counts
"""
import argparse
import pathlib
import random
import shutil
import time

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
FEAT = ROOT / "data/raw/lanl/feat.parquet"
REDTEAM_TXT = ROOT / "data/raw/lanl/redteam.txt"
REDTEAM_PARQ = ROOT / "data/raw/lanl/redteam.parquet"
OUT = ROOT / "data/raw/lanl/feat_10m.parquet"

try:
    import psutil
    HAS = True
except ImportError:
    HAS = False
import os


def mem(tag):
    if not HAS:
        return tag
    vm = psutil.virtual_memory()
    rss = psutil.Process(os.getpid()).memory_info().rss / 1e9
    return f"[{tag}] RAM {vm.percent:.0f}% avail {vm.available/1e9:.1f}G rss {rss:.1f}G"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feat", type=pathlib.Path, default=FEAT)
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    ap.add_argument("--n-normal", type=int, default=100, help="normal users to sample")
    ap.add_argument("--cap", type=int, default=500_000, help="per-user max events (0 = no cap, default 500K)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    print(f"building 10M rich from {args.feat} {mem('init')}", flush=True)
    try:
        print(f" /tmp free {shutil.disk_usage('/tmp').free/1e9:.1f}G  df avail {shutil.disk_usage('/').free/1e9:.1f}G", flush=True)
    except Exception:
        pass
    t0 = time.time()

    con = duckdb.connect()
    con.execute("SET threads=4")
    con.execute("SET memory_limit='4GB'")
    con.execute("SET temp_directory='/tmp'")

    # Load red users from redteam.parquet if exists else redteam.txt
    if REDTEAM_PARQ.exists():
        red_users = [r[0] for r in con.execute(f"SELECT DISTINCT user FROM read_parquet('{REDTEAM_PARQ}') ORDER BY user").fetchall()]
    else:
        red_users = []
        with open(REDTEAM_TXT) as f:
            for line in f:
                _, u, _, _ = line.strip().split(",")
                red_users.append(u)
        red_users = sorted(set(red_users))
    print(f" red users: {len(red_users)} (104 expected) e.g. {red_users[:3]} {mem('red')}", flush=True)
    assert len(red_users) == 104, f"expected 104 red users got {len(red_users)}"

    # Normal pool: distinct U###@DOM1 from feat excluding red
    red_users_set = set(red_users)
    normal_all = [r[0] for r in con.execute(f"SELECT DISTINCT src_user FROM read_parquet('{args.feat}') WHERE src_user LIKE 'U%@DOM1' ORDER BY src_user").fetchall() if r[0] not in red_users_set]
    print(f" normal pool U@DOM1 excluding red: {len(normal_all)} {mem('normal-pool')}", flush=True)

    random.seed(args.seed)
    sampled = random.sample(normal_all, min(args.n_normal, len(normal_all)))
    sampled_set = set(sampled)
    keep = set(red_users) | sampled_set
    print(f" keeping {len(keep)} users: 104 red + {len(sampled)} normal (sampled e.g. {sampled[:3]}) {mem('keep')}", flush=True)

    # Build rich via DuckDB: filter by src_user IN keep, then cap per-user if needed
    keep_list = ",".join(f"'{u}'" for u in keep)
    # Write to temp then rename, to avoid partial
    tmp = str(args.out) + ".tmp"
    # If cap >0, use ROW_NUMBER per user to limit
    if args.cap and args.cap > 0:
        print(f" capping per-user to {args.cap} (keeps 702 reds, avoids U66 11M) {mem('cap')}", flush=True)
        con.execute(f"""
            COPY (
                WITH filtered AS (
                    SELECT * FROM read_parquet('{args.feat}') WHERE src_user IN ({keep_list})
                ),
                ranked AS (
                    SELECT *, ROW_NUMBER() OVER (PARTITION BY src_user ORDER BY time, src_computer, dst_computer) AS rn
                    FROM filtered
                )
                SELECT * EXCLUDE (rn) FROM ranked WHERE rn <= {args.cap}
            ) TO '{tmp}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
    else:
        con.execute(f"""
            COPY (SELECT * FROM read_parquet('{args.feat}') WHERE src_user IN ({keep_list}))
            TO '{tmp}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
    # Move
    pathlib.Path(tmp).replace(args.out)
    elapsed = time.time() - t0
    sz_mb = args.out.stat().st_size / 1e6
    print(f" wrote {args.out} {sz_mb:.0f} MB in {elapsed:.1f}s {mem('wrote')}", flush=True)

    # Quick count
    n = con.execute(f"SELECT count(*) FROM read_parquet('{args.out}')").fetchone()[0]
    reds = con.execute(f"SELECT sum(is_red::INT) FROM read_parquet('{args.out}')").fetchone()[0]
    users = con.execute(f"SELECT count(DISTINCT src_user) FROM read_parquet('{args.out}')").fetchone()[0]
    print(f" rich counts: rows={n:,} reds={reds} users={users} ({n/reds if reds else 0:.0f} rows/red) {mem('counts')}", flush=True)
    # Per-user breakdown top heavy
    top = con.execute(f"SELECT src_user, count(*) c FROM read_parquet('{args.out}') GROUP BY src_user ORDER BY c DESC LIMIT 5").fetchall()
    print(f" top users: {top} {mem('top')}", flush=True)


if __name__ == "__main__":
    main()
