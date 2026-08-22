#!/usr/bin/env python3
"""LANL event generator — runs on Laptop 2, sends events to Laptop 1 backend.

Usage:
    python generate.py [--url http://LAPTOP1:5000] [--rate 2] [--attacker-rate 10]

Reads events from slice.parquet and POSTs them to the Flask backend.
Normal users are sent at --rate events/sec, attacker at --attacker-rate.
Injects attack bursts every --burst-interval seconds.
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

import duckdb
import requests

ROOT = Path(__file__).resolve().parents[1]
SLICE = ROOT / "data" / "raw" / "lanl" / "slice.parquet"

NORMAL_USERS = [
    {"raw_id": "U10059@DOM1", "user_id": 1},
    {"raw_id": "U10158@DOM1", "user_id": 2},
    {"raw_id": "U10500@DOM1", "user_id": 3},
]
ATTACKER = {"raw_id": "U748@DOM1", "user_id": -1, "src_computer": "C17693"}


def load_events(con):
    rows = con.execute(f"""
        SELECT src_user, dst_user, src_computer, dst_computer,
               auth_type, logon_type, orientation, result
        FROM read_parquet('{SLICE}')
        ORDER BY time
    """).fetchall()
    normal_by_user = {}
    attacker_events = []
    for r in rows:
        src_user = r[0]
        ev = {
            "src_computer": r[2], "dst_computer": r[3],
            "auth_type": r[4], "logon_type": r[5],
            "orientation": r[6], "result": r[7],
        }
        if src_user == ATTACKER["raw_id"]:
            attacker_events.append(ev)
        for u in NORMAL_USERS:
            if src_user == u["raw_id"]:
                normal_by_user.setdefault(u["user_id"], []).append(ev)
    return normal_by_user, attacker_events


def send_event(url, user_id, ev):
    payload = {"user_id": user_id, **ev}
    try:
        r = requests.post(f"{url}/events", json=payload, timeout=5)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="LANL event generator for Laptop 2")
    parser.add_argument("--url", default="http://127.0.0.1:5000", help="Backend URL (Laptop 1)")
    parser.add_argument("--rate", type=float, default=2.0, help="Events/sec for normal users")
    parser.add_argument("--attacker-rate", type=float, default=10.0, help="Events/sec for attacker")
    parser.add_argument("--burst-interval", type=int, default=60, help="Seconds between attack bursts")
    parser.add_argument("--burst-size", type=int, default=20, help="Events per burst")
    args = parser.parse_args()

    con = duckdb.connect(read_only=True)
    print("loading events from slice.parquet...")
    normal_by_user, attacker_events = load_events(con)
    con.close()

    print(f"loaded {sum(len(v) for v in normal_by_user.values())} normal events "
          f"({', '.join(f'{len(v)} for uid {k}' for k, v in normal_by_user.items())}), "
          f"{len(attacker_events)} attacker events")

    normal_iters = {uid: iter(evts * 100) for uid, evts in normal_by_user.items()}
    attacker_iter = iter(attacker_events * 100)
    burst_timer = time.time()

    print(f"sending to {args.url} — normal {args.rate}/s, attacker {args.attacker_rate}/s, "
          f"burst every {args.burst_interval}s ({args.burst_size} events)")
    print("Ctrl+C to stop\n")

    try:
        while True:
            now = time.time()

            for uid, it in normal_iters.items():
                for _ in range(int(args.rate)):
                    try:
                        ev = next(it)
                    except StopIteration:
                        normal_iters[uid] = iter(normal_by_user[uid] * 100)
                        ev = next(normal_iters[uid])
                    result = send_event(args.url, uid, ev)
                    level = result.get("risk_level", "?")
                    score = result.get("combined_score", 0)
                    print(f"  [normal uid={uid}] {ev['src_computer']}->{ev['dst_computer']} "
                          f"score={score:.3f} {level}")
                    time.sleep(1.0 / args.rate)

            for _ in range(int(args.attacker_rate)):
                try:
                    ev = next(attacker_iter)
                except StopIteration:
                    attacker_iter = iter(attacker_events * 100)
                    ev = next(attacker_iter)
                result = send_event(args.url, ATTACKER["user_id"], ev)
                level = result.get("risk_level", "?")
                score = result.get("combined_score", 0)
                reasons = result.get("reasons", "")
                print(f"  [ATTACK uid={ATTACKER['user_id']}] {ev['src_computer']}->{ev['dst_computer']} "
                      f"score={score:.3f} {level} {reasons[:60]}")
                time.sleep(1.0 / args.attacker_rate)

            if now - burst_timer > args.burst_interval:
                burst_timer = now
                print(f"\n*** BURST: {args.burst_size} rapid attack events ***")
                for i in range(args.burst_size):
                    ev = random.choice(attacker_events)
                    result = send_event(args.url, ATTACKER["user_id"], ev)
                    level = result.get("risk_level", "?")
                    score = result.get("combined_score", 0)
                    print(f"  [BURST {i+1}/{args.burst_size}] {ev['src_computer']}->{ev['dst_computer']} "
                          f"score={score:.3f} {level}")
                    time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
