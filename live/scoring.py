#!/usr/bin/env python3
"""Phase 7b — live scoring.

One event in, a decision out. The scoring path is the *same SQL* the
offline pipeline used:

  feature_sql (src/02)  -> behavioral + seen-before features for the user
  score_sql   (src/04)  -> rule points, risk level, human-readable reasons

The new event is inserted into `events` first; the feature query runs over
the user's full history (new event included, so its window features —
LAG, seen-before, rapid_login_rate — are computed against the real past),
then the scores ride back onto the event row.

Decision policy (state assumption, demo defaults):
  - is_attack_ip (blocklist)          -> block, hard kill
  - rule_score >= critical (90)       -> block (stops a fake "foreign + night"
                                         login, while a plain new device stays
                                         a flag instead of a hard block)
  - rule_score >= flag (45)           -> flag (challenge / OTP)
  - otherwise                          -> allow

The `flag` cutoff defaults to 45 (medium) and is overridable via the
DEMO_FLAG_AT environment variable.
"""
import importlib.util
import os
from pathlib import Path

import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_shared = _load_module("_shared", ROOT / "src" / "_shared.py")
_feat = _load_module("feat", ROOT / "src" / "02_feature_engineering.py")
_rule = _load_module("rule", ROOT / "src" / "04_rule_baseline.py")

feature_sql = _feat.feature_sql
score_sql = _rule.score_sql
LEVEL_BOUNDS = _rule.LEVEL_BOUNDS

from db import refresh_profile  # noqa: E402

FLAG_AT = int(os.environ.get("DEMO_FLAG_AT", "45"))


def score_event(con: duckdb.DuckDBPyConnection, ev: dict) -> dict:
    """Score one login event against the user's stored history.

    `ev` must carry: user_id, ts, ip, country, device_type, os_family,
    browser_family, login_success, is_attack_ip, is_ato, is_private_ip,
    geo_unreliable, rtt_missing, ua_os_conflict, is_generator_bot, is_vlc, asn.
    Inserts the row, computes features + rules, writes the decision back,
    raises an alert when needed. Returns the scored row.
    """
    row_id = int(con.execute("SELECT COALESCE(MAX(row_id), 0) + 1 FROM events").fetchone()[0])
    con.execute("""
        INSERT INTO events (row_id, ts, user_id, ip, country, device_type,
            os_family, browser_family, login_success, is_attack_ip, is_ato,
            is_private_ip, geo_unreliable, rtt_missing, ua_os_conflict,
            is_generator_bot, is_vlc, asn)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (row_id, ev["ts"], ev["user_id"], ev.get("ip"), ev.get("country"),
          ev.get("device_type"), ev.get("os_family"), ev.get("browser_family"),
          ev["login_success"], ev.get("is_attack_ip"), ev.get("is_ato"),
          ev.get("is_private_ip"), ev.get("geo_unreliable"), ev.get("rtt_missing"),
          ev.get("ua_os_conflict"), ev.get("is_generator_bot"), ev.get("is_vlc"),
          ev.get("asn")))

    user_src = f"""
        (SELECT row_id, ts, user_id, ip, country, asn, device_type, os_family,
                browser_family, login_success, is_attack_ip, is_ato,
                is_private_ip, geo_unreliable, rtt_missing, ua_os_conflict,
                is_generator_bot, is_vlc
         FROM events WHERE user_id = {ev['user_id']})
    """
    feat = con.execute(f"""
        SELECT * FROM ({feature_sql(user_src)})
        WHERE row_id = {row_id}
    """).fetchdf().iloc[0]

    h = feat["hour"] / 24.0 * 2 * np.pi
    feat["hour_sin"] = np.sin(h)
    feat["hour_cos"] = np.cos(h)

    row = con.execute(f"""
        SELECT * FROM ({score_sql(f"({feature_sql(user_src)})")})
        WHERE row_id = {row_id}
    """).fetchdf().iloc[0]

    rule_reasons = str(row["reasons"])
    if bool(feat["is_attack_ip"]):
        decision, level = "block", "critical"
        reasons = "blocklist ip"
    elif int(row["rule_score"]) >= LEVEL_BOUNDS["critical"]:
        decision, level = "block", row["risk_level"]
        reasons = rule_reasons
    elif int(row["rule_score"]) >= FLAG_AT:
        decision, level = "flag", row["risk_level"]
        reasons = rule_reasons
    else:
        decision, level = "allow", row["risk_level"]
        reasons = rule_reasons

    con.execute("""
        UPDATE events SET rule_score = ?, risk_level = ?, reasons = ?, decision = ?
        WHERE row_id = ?
    """, (int(row["rule_score"]), level, reasons, decision, row_id))

    if decision in ("block", "flag"):
        alert_id = int(con.execute("SELECT COALESCE(MAX(alert_id), 0) + 1 FROM alerts").fetchone()[0])
        con.execute("""
            INSERT INTO alerts (alert_id, event_id, user_id, ts, level,
                rule_score, reasons, decision)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (alert_id, row_id, ev["user_id"], ev["ts"], level,
              int(row["rule_score"]), reasons, decision))
    elif decision == "allow":
        refresh_profile(con, ev["user_id"])

    return {
        "row_id": row_id, "user_id": ev["user_id"], "ts": ev["ts"],
        "ip": ev.get("ip"), "country": ev.get("country"),
        "device_type": ev.get("device_type"), "os_family": ev.get("os_family"),
        "browser_family": ev.get("browser_family"),
        "login_success": bool(ev["login_success"]),
        "rule_score": int(row["rule_score"]), "risk_level": level,
        "reasons": reasons, "decision": decision,
    }
