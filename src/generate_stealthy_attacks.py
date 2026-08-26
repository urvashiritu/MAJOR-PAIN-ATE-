#!/usr/bin/env python3
"""Generate stealthy attack events for training data augmentation.

Creates 5 attack IPs with realistic patterns that evade simple threshold detection:
- 10.20.99.101: Slow brute force (2-3 failures/day, business hours, SSH+WEB)
- 10.20.99.102: Credential stuffing (50 users, 40% failure, ENTRA+AWS)
- 10.20.99.103: Lateral movement (80% success, MYSQL+WINDOWS, normal hours)
- 10.20.99.104: Low-and-slow (1 failure/2hrs, 300 users, SSH only)
- 10.20.99.105: Distributed spray (all 6 sources, 5 events/source/day)
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

# Load existing user list from normalized CSV
import csv
USERS = []
csv_path = Path("outputs/normalized_authentication_events.csv")
with open(csv_path) as f:
    reader = csv.DictReader(f)
    for row in reader:
        uid = row.get("user_id", "")
        if uid and uid not in USERS:
            USERS.append(uid)
        if len(USERS) >= 500:
            break

USERS = [u.split("@")[0] for u in USERS]  # strip @contoso.com

SOURCES = ["SSH", "WEB", "AWS", "ENTRA", "MYSQL", "WINDOWS"]

# July 2026 date range
START = datetime(2026, 7, 1)
END = datetime(2026, 7, 31, 23, 59, 59)


def ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def rand_time(dt_min, dt_max):
    delta = (dt_max - dt_min).total_seconds()
    return dt_min + timedelta(seconds=random.uniform(0, delta))


def business_hour(dt):
    """Return dt with hour constrained to 8-18."""
    h = random.randint(8, 18)
    m = random.randint(0, 59)
    s = random.randint(0, 59)
    return dt.replace(hour=h, minute=m, second=s)


# ── 10.20.99.101: Slow brute force ──
def gen_slow_brute():
    events = []
    target_users = random.sample(USERS, min(100, len(USERS)))
    for day in range(31):
        dt = START + timedelta(days=day)
        # 2-3 failures per day, business hours
        n_fails = random.randint(2, 3)
        for _ in range(n_fails):
            t = business_hour(dt)
            if t > END:
                continue
            user = random.choice(target_users)
            success = random.random() < 0.15  # 15% success (compromised occasionally)
            events.append({
                "timestamp": ts(t),
                "src_user": user,
                "src_ip": "10.20.99.101",
                "success": success,
                "source": random.choice(["SSH", "WEB"]),
                "auth_type": "password",
            })
    return events


# ── 10.20.99.102: Credential stuffing ──
def gen_cred_stuff():
    events = []
    target_users = random.sample(USERS, min(50, len(USERS)))
    for day in range(31):
        dt = START + timedelta(days=day)
        # 1 attempt per user per day
        for user in target_users:
            h = random.choices(range(24), weights=[1,1,1,1,1,1,1,2,4,4,4,4,4,4,4,4,3,3,2,2,1,1,1,1])[0]
            t = dt.replace(hour=h, minute=random.randint(0,59), second=random.randint(0,59))
            if t > END:
                continue
            success = random.random() < 0.40  # 40% success
            events.append({
                "timestamp": ts(t),
                "src_user": user,
                "src_ip": "10.20.99.102",
                "success": success,
                "source": random.choice(["ENTRA", "AWS"]),
                "auth_type": "password",
            })
    return events


# ── 10.20.99.103: Lateral movement ──
def gen_lateral():
    events = []
    target_users = random.sample(USERS, min(30, len(USERS)))
    for day in range(31):
        dt = START + timedelta(days=day)
        # 5-8 events per day, business hours, high success
        n_events = random.randint(5, 8)
        for _ in range(n_events):
            t = business_hour(dt)
            if t > END:
                continue
            user = random.choice(target_users)
            success = random.random() < 0.80  # 80% success (compromised creds)
            events.append({
                "timestamp": ts(t),
                "src_user": user,
                "src_ip": "10.20.99.103",
                "success": success,
                "source": random.choice(["MYSQL", "WINDOWS"]),
                "auth_type": "password",
            })
    return events


# ── 10.20.99.104: Low-and-slow ──
def gen_low_slow():
    events = []
    target_users = random.sample(USERS, min(300, len(USERS)))
    for day in range(31):
        dt = START + timedelta(days=day)
        # 12 failures per day (1 every 2 hours), spread across users
        for hour in range(0, 24, 2):
            t = dt.replace(hour=hour, minute=random.randint(0,59), second=random.randint(0,59))
            if t > END:
                continue
            user = random.choice(target_users)
            success = random.random() < 0.10  # 10% success
            events.append({
                "timestamp": ts(t),
                "src_user": user,
                "src_ip": "10.20.99.104",
                "success": success,
                "source": "SSH",
                "auth_type": "password",
            })
    return events


# ── 10.20.99.105: Distributed spray ──
def gen_spray():
    events = []
    target_users = random.sample(USERS, min(40, len(USERS)))
    for day in range(31):
        dt = START + timedelta(days=day)
        # 5 events per source per day = 30 total per day
        for source in SOURCES:
            for _ in range(5):
                h = random.choices(range(24), weights=[1,1,1,1,1,1,1,2,4,4,4,4,4,4,4,4,3,3,2,2,1,1,1,1])[0]
                t = dt.replace(hour=h, minute=random.randint(0,59), second=random.randint(0,59))
                if t > END:
                    continue
                user = random.choice(target_users)
                success = random.random() < 0.30  # 30% success
                events.append({
                    "timestamp": ts(t),
                    "src_user": user,
                    "src_ip": "10.20.99.105",
                    "success": success,
                    "source": source,
                    "auth_type": "password",
                })
    return events


def main():
    out_path = Path("data/stealthy_attacks.jsonl")
    all_events = []

    generators = [
        ("10.20.99.101 (slow brute)", gen_slow_brute),
        ("10.20.99.102 (cred stuffing)", gen_cred_stuff),
        ("10.20.99.103 (lateral)", gen_lateral),
        ("10.20.99.104 (low-and-slow)", gen_low_slow),
        ("10.20.99.105 (spray)", gen_spray),
    ]

    for name, gen in generators:
        events = gen()
        all_events.extend(events)
        print(f"  {name}: {len(events)} events")

    # Shuffle by timestamp
    all_events.sort(key=lambda e: e["timestamp"])

    with open(out_path, "w") as f:
        for ev in all_events:
            f.write(json.dumps(ev) + "\n")

    print(f"\nTotal: {len(all_events)} events → {out_path}")


if __name__ == "__main__":
    main()
