#!/usr/bin/env python3
"""Measure live-scoring separation between normal and attack scenarios.

Drives score_event() directly against the seeded demo DB inside ONE
transaction, then rolls back — zero pollution of history/profiles.

Scenarios (per persona: alice=1, bob=2, carol=3):
  normal_frame   replay own history, time continued after history end
  normal_now     replay own history, wall-clock now (demo-day condition)
  wrong_password own src/dst, result Fail
  new_machine    unseen src + unseen dst
  odd_hour       pseudo-hour far from the user's typical hours
  burst          10 rapid events, last 5 measured (velocity accumulation)
Attacker (user_id=-1):
  attack_replay  own C17693 events replayed
  attack_burst   10 rapid C17693-style events, last 5 measured

Output: console summary table + lanl-anomaly/reports/score_measurements.json
"""
import json
import random
import statistics
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live"))

import db as db  # noqa: E402
from scoring import score_event, BLOCK_THRESHOLD, FLAG_THRESHOLD  # noqa: E402

DB_PATH = ROOT / "data" / "live.duckdb"
OUT_PATH = ROOT / "reports" / "score_measurements.json"

SEED = 42
N_NORMAL = 15
N_FAULT = 10
BURST_LEN = 10
BURST_MEASURE_LAST = 5

PERSONAS = [1, 2, 3]
ATTACKER = -1


def persona_facts(con, uid):
    rows = con.execute("""
        SELECT time, src_computer, dst_computer FROM events
        WHERE user_id = ? AND decision = 'history' ORDER BY time
    """, [uid]).fetchall()
    seen_dst = {r[2] for r in rows}
    seen_src = {r[1] for r in rows}
    hrs = sorted({int((r[0] % 86400) / 3600) for r in rows})
    return rows, seen_dst, seen_src, hrs


def main():
    rng = random.Random(SEED)
    con = duckdb.connect(str(DB_PATH))
    db.init_schema(con)
    con.execute("BEGIN TRANSACTION")
    results = {}

    # Demo-day condition: events stamped on the continuation frame exactly
    # like app.py does for clients that omit 'time'.
    anchor = db.get_seed_anchor(con)
    session_time = lambda i=0: (anchor[0] + max(0, int(time.time()) - anchor[1]) + i
                                if anchor else int(time.time()))

    def run(label, uid, ev):
        r = score_event(con, ev)
        results.setdefault(label, []).append(
            {"user": uid, "if": r["if_score"], "lgb": r["lgb_score"],
             "decision": r["decision"], "level": r["risk_level"]})

    hist_max = con.execute(
        "SELECT MAX(time) FROM events WHERE decision='history'").fetchone()[0]

    for uid in PERSONAS + [ATTACKER]:
        rows, seen_dst, seen_src, hrs = persona_facts(con, uid)
        tag = "attack" if uid == ATTACKER else f"user{uid}"
        off_hours = [(h + 7) % 24 for h in hrs] or [3]

        def frame_time(i):
            return hist_max + 60 * (i + 1)

        def odd_time(i):
            day0 = (hist_max // 86400) * 86400
            t = day0 + off_hours[i % len(off_hours)] * 3600 + 1800
            while t <= hist_max:
                t += 86400
            return t

        for i in range(N_NORMAL):
            _, src, dst = rng.choice(rows)[-3:]
            run(f"{tag}:normal_frame", uid,
                dict(user_id=uid, src_computer=src, dst_computer=dst,
                     time=frame_time(i)))
            # human-paced demo-day logins: one every ~45 s on the frame
            run(f"{tag}:normal_session", uid,
                dict(user_id=uid, src_computer=src, dst_computer=dst,
                     time=session_time(i * 45)))

        if uid != ATTACKER:
            for i in range(N_FAULT):
                _, src, dst = rng.choice(rows)[-3:]
                run(f"{tag}:wrong_password", uid,
                    dict(user_id=uid, src_computer=src, dst_computer=dst,
                         result="Fail", time=frame_time(N_NORMAL + i)))
            for i in range(N_FAULT):
                run(f"{tag}:new_machine", uid,
                    dict(user_id=uid, src_computer=f"C9{700+i}",
                         dst_computer=f"C9{800+i}", time=frame_time(30 + i)))
            for i in range(N_FAULT):
                _, src, dst = rng.choice(rows)[-3:]
                run(f"{tag}:odd_hour", uid,
                    dict(user_id=uid, src_computer=src, dst_computer=dst,
                         time=odd_time(i)))
            for i in range(BURST_LEN):
                _, src, dst = rng.choice(rows)[-3:]
                run(f"{tag}:burst_last" if i >= BURST_LEN - BURST_MEASURE_LAST
                    else f"{tag}:burst_warmup",
                    uid, dict(user_id=uid, src_computer=src, dst_computer=dst,
                              result="Fail" if i % 3 == 0 else "Success",
                              time=hist_max + 7200 + i * 20))
        else:
            c17693 = [r for r in rows if r[1] == "C17693"] or rows
            for i in range(N_NORMAL):
                _, src, dst = rng.choice(c17693)[-3:]
                run(f"{tag}:replay", uid,
                    dict(user_id=uid, src_computer=src, dst_computer=dst,
                         time=frame_time(i)))
            for i in range(BURST_LEN):
                _, src, dst = rng.choice(c17693)[-3:]
                run(f"{tag}:burst_last" if i >= BURST_LEN - BURST_MEASURE_LAST
                    else f"{tag}:burst_warmup",
                    uid, dict(user_id=uid, src_computer="C17693",
                              dst_computer=dst,
                              result="Fail" if i % 2 == 0 else "Success",
                              time=hist_max + 7200 + i * 20))

    con.execute("ROLLBACK")
    con.close()

    print(f"\ncurrent thresholds: FLAG>={FLAG_THRESHOLD} BLOCK>={BLOCK_THRESHOLD}\n")
    header = f"{'scenario':<24}{'n':>4}{'min':>7}{'p50':>7}{'max':>7}  {'allow':>5}{'flag':>5}{'block':>6}"
    print(header)
    print("-" * len(header))
    summary = {}
    for label in sorted(results.keys()):
        scores = [r["if"] for r in results[label]]
        dec = [r["decision"] for r in results[label]]
        summary[label] = {
            "n": len(scores),
            "min": round(min(scores), 4),
            "p50": round(statistics.median(scores), 4),
            "max": round(max(scores), 4),
            "allow": dec.count("allow"),
            "flag": dec.count("flag"),
            "block": dec.count("block"),
        }
        s = summary[label]
        print(f"{label:<24}{s['n']:>4}{s['min']:>7.3f}{s['p50']:>7.3f}"
              f"{s['max']:>7.3f}  {s['allow']:>5}{s['flag']:>5}{s['block']:>6}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(
        {"measured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
         "thresholds": {"flag": FLAG_THRESHOLD, "block": BLOCK_THRESHOLD},
         "summary": summary, "raw": results}, indent=2))
    print(f"\nfull scores -> {OUT_PATH}")


if __name__ == "__main__":
    main()
