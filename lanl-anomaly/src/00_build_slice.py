"""LANL cyber1 dataset tool: audit the full 1.05B stream, reduce it to the
604-user slice, and load the slice into DuckDB.

Recovered from git history (src/lanl_stream.py, last committed 2026-08-20,
deleted 2026-08-29 in 59bb082). The count/slice logic is verbatim; the load
mode scripts the DuckDB glue that was previously done inline in the session.

Usage (auth.txt is 73.4 GB inside the zip — always stream through the pipe,
never extract):
  unzip -p ~/Downloads/archive.zip auth.txt/auth.txt | python src/00_build_slice.py count
  unzip -p ~/Downloads/archive.zip auth.txt/auth.txt | python src/00_build_slice.py slice
  python src/00_build_slice.py load

count : Pass 1 — stream all events, tally totals/users/failures/red-matches,
        write the distinct src_user list (users.txt). RAM stays at a few MB.
slice : Pass 2 — second stream pass, keep rows of 104 red-team users +
        500 sampled human normals (seed 42) -> slice.csv.gz.
load  : Load slice.csv.gz into lanl.duckdb as auth_slice, export slice.parquet,
        and create the redteam table.
"""
import argparse
import gzip
import random
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "raw" / "lanl"

# auth.txt line layout (9 CSV fields, verified against LANL docs + head -5):
# time, src_user@domain, dst_user@domain, src_computer, dst_computer,
# auth_type, logon_type, auth_orientation, result
SLICE_COLUMNS = {
    "time": "BIGINT",
    "src_user": "VARCHAR",
    "dst_user": "VARCHAR",
    "src_computer": "VARCHAR",
    "dst_computer": "VARCHAR",
    "auth_type": "VARCHAR",
    "logon_type": "VARCHAR",
    "orientation": "VARCHAR",
    "result": "VARCHAR",
}


def load_redteam(path):
    red = set()
    users = set()
    with open(path) as f:
        for line in f:
            t, u, s, d = line.rstrip("\n").split(",")
            red.add((int(t), u, s, d))
            users.add(u)
    return red, users


def report(what, n, start):
    elapsed = time.time() - start
    rate = n / elapsed if elapsed else 0
    print(f"[{what}] {elapsed:6.0f}s  {n:>15,} events  ({rate:,.0f}/s)", flush=True)


def cmd_count(red_bytes, users_file):
    n = 0
    src_users = set()
    dst_users = set()
    src_computers = set()
    dst_computers = set()
    fails = 0
    red_matched = 0
    t_min = None
    t_max = None
    start = time.time()
    last = start
    for raw in sys.stdin.buffer:
        parts = raw.rstrip(b"\n").split(b",")
        if len(parts) < 9:
            continue
        t = int(parts[0])
        su, du, sc, dc, res = parts[1], parts[2], parts[3], parts[4], parts[8]
        n += 1
        src_users.add(su)
        dst_users.add(du)
        src_computers.add(sc)
        dst_computers.add(dc)
        if res == b"Fail":
            fails += 1
        if (t, su, sc, dc) in red_bytes:
            red_matched += 1
        if t_min is None or t < t_min:
            t_min = t
        if t_max is None or t > t_max:
            t_max = t
        if n & 0x7FFFF == 0 and time.time() - last >= 30:
            report("count", n, start)
            last = time.time()
    report("count", n, start)
    print("\n=== FULL SCAN DONE ===")
    print(f"events           : {n:,}")
    print(f"src_users        : {len(src_users):,}")
    print(f"dst_users        : {len(dst_users):,}")
    print(f"src_computers    : {len(src_computers):,}")
    print(f"dst_computers    : {len(dst_computers):,}")
    print(f"fails            : {fails:,}")
    print(f"time range       : {t_min} .. {t_max}")
    print(f"red-team matched : {red_matched:,} / 749")
    with open(users_file, "w") as f:
        for u in sorted(src_users):
            f.write(u.decode() + "\n")
    print(f"distinct src_users -> {users_file}")


def cmd_slice(red_users, red_bytes, users_file, out_path, n_normal=500, normal_pattern=None):
    with open(users_file) as f:
        all_users = {line.strip() for line in f}
    if normal_pattern:
        re_normal = __import__("re").compile(normal_pattern)
        all_users = {u for u in all_users if re_normal.match(u)}
    normal = sorted(all_users - red_users)
    random.seed(42)
    sample = set(random.sample(normal, min(n_normal, len(normal))))
    keep = red_users | sample
    keep_b = {u.encode() for u in keep}
    print(f"red-team users : {len(red_users):,}")
    print(f"normal sample  : {len(sample):,}")
    print(f"keep total     : {len(keep):,}", flush=True)
    n = 0
    kept = 0
    red_matched = 0
    start = time.time()
    last = start
    with gzip.open(out_path, "wt") as out:
        for raw in sys.stdin.buffer:
            parts = raw.rstrip(b"\n").split(b",")
            if len(parts) < 9:
                continue
            n += 1
            if parts[1] not in keep_b:
                if n & 0x7FFFF == 0 and time.time() - last >= 30:
                    report("slice", n, start)
                    last = time.time()
                continue
            out.write(raw.decode().strip() + "\n")
            kept += 1
            if (int(parts[0]), parts[1], parts[3], parts[4]) in red_bytes:
                red_matched += 1
            if n & 0x7FFFF == 0 and time.time() - last >= 30:
                report("slice", n, start)
                last = time.time()
    report("slice", n, start)
    print("\n=== SLICE DONE ===")
    print(f"events scanned   : {n:,}")
    print(f"events kept      : {kept:,}")
    print(f"red-team matched : {red_matched:,} / 749")
    print(f"slice -> {out_path}")


def cmd_load(db_path, slice_gz, slice_parquet, redteam_txt):
    """Load slice.csv.gz into DuckDB as auth_slice, export slice.parquet,
    create the redteam table. (This glue was previously run inline.)"""
    cols = ", ".join(f"'{name}':'{typ}'" for name, typ in SLICE_COLUMNS.items())
    con = duckdb.connect(str(db_path))
    con.execute(f"""
        CREATE OR REPLACE TABLE auth_slice AS
        SELECT * FROM read_csv('{slice_gz}', delim=',', header=false,
                               columns={{{cols}}})
    """)
    n_slice = con.execute("SELECT count(*), count(DISTINCT src_user) FROM auth_slice").fetchone()
    con.execute(f"COPY auth_slice TO '{slice_parquet}' (FORMAT PARQUET)")
    con.execute(f"""
        CREATE OR REPLACE TABLE redteam AS
        SELECT * FROM read_csv('{redteam_txt}', delim=',', header=false,
            columns={{'time':'BIGINT','user':'VARCHAR',
                      'src_computer':'VARCHAR','dst_computer':'VARCHAR'}})
    """)
    n_red = con.execute("SELECT count(*) FROM redteam").fetchone()[0]
    con.close()
    print("\n=== LOAD DONE ===")
    print(f"auth_slice   : {n_slice[0]:,} rows / {n_slice[1]:,} users")
    print(f"slice.parquet + redteam ({n_red} lines) written; db = {db_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=["count", "slice", "load"])
    ap.add_argument("--redteam", default=str(DATA / "redteam.txt"))
    ap.add_argument("--users", default=str(DATA / "users.txt"))
    ap.add_argument("--out", default=str(DATA / "slice.csv.gz"))
    ap.add_argument("--db", default=str(DATA / "lanl.duckdb"))
    ap.add_argument("--slice-parquet", default=str(DATA / "slice.parquet"))
    ap.add_argument("--n-normal", type=int, default=500)
    ap.add_argument("--normal-pattern", default="^U\\d+@DOM1$")
    args = ap.parse_args()

    if args.mode == "load":
        cmd_load(args.db, args.out, args.slice_parquet, args.redteam)
        return

    red, red_users = load_redteam(args.redteam)
    red_bytes = {(t, u.encode(), s.encode(), d.encode()) for t, u, s, d in red}
    print(f"redteam loaded: {len(red)} events, {len(red_users)} users")

    if args.mode == "count":
        cmd_count(red_bytes, args.users)
    else:
        cmd_slice(red_users, red_bytes, args.users, args.out, args.n_normal, args.normal_pattern)


if __name__ == "__main__":
    main()
