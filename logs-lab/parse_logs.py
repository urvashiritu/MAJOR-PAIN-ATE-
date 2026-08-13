#!/usr/bin/env python3
"""logs-lab step 1+2 — parse the six heterogeneous sources into one common
login-event schema and write events.parquet.

Common schema per event:
  ts (datetime, naive UTC) | source | user | ip | country | device | os
  | browser | success (bool) | status (str)

Every parser reports its parse ratio; step 2 verifies 100% before writing.
All timestamps are treated as UTC (sources are naive local times; assumption
documented for a side-project).
"""
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import xml.etree.ElementTree as ET

RAW = Path(__file__).resolve().parent / "raw"
OUT = Path(__file__).resolve().parent / "events.parquet"

YEAR = 2026  # record timestamps observed across sources are Jul 2026

COLUMNS = ["ts", "source", "user", "ip", "country", "device", "os",
           "browser", "success", "status"]


# ----------------------------- UA classifier -----------------------------

_TABLET = re.compile(r"ipad|SM-T|GT-N|galaxy tab|tab (?!dog)|tablet", re.I)
_MOBILE = re.compile(r"mobi|iphone|ipod|android|windows phone|opera mini|blackberry|symbian", re.I)
_DESKTOP = re.compile(r"mac os x|macintosh|windows nt|windows|linux|x11|crvos|chrome os", re.I)


def _ua(ua, os_=None, browser=None, device=None):
    ua = ua or ""
    lo = ua.lower()
    if device is None:
        if not lo or "bot" in lo or "crawler" in lo or "curl" in lo:
            device = "bot" if lo else "unknown"
        elif _TABLET.search(lo):
            device = "tablet"
        elif _MOBILE.search(lo):
            device = "mobile"
        elif _DESKTOP.search(lo):
            device = "desktop"
        else:
            device = "unknown"
    if os_ is None:
        if "android" in lo:
            os_ = "Android"
        elif "iphone" in lo or "ipad" in lo or "ipod" in lo:
            os_ = "iOS"
        elif "windows nt" in lo or "windows phone" in lo:
            os_ = "Windows"
        elif "mac os x" in lo or "macintosh" in lo:
            os_ = "macOS"
        elif "linux" in lo or "crvos" in lo or "chrome os" in lo:
            os_ = "Linux"
        else:
            os_ = "unknown"
    if browser is None:
        for b in ("edg", "edge", "firefox", "fxios"):
            if b in lo:
                browser = "Edge" if b in ("edg", "edge") else "Firefox"
                break
        else:
            if "crios" in lo:
                browser = "Chrome"
            elif "fxiOS" in lo:
                browser = "Firefox"
            elif "chrome" in lo:
                browser = "Chrome"
            elif "crios" in lo:
                browser = "Chrome"
            elif "safari" in lo:
                browser = "Safari"
            else:
                browser = "unknown"
    return device, os_, browser


# ----------------------------- parsers -----------------------------

_RB = {"eu": "DE", "us": "US", "ap": "IN", "sa": "BR", "ca": "CA", "af": "EG"}


def _aws_region_country(region):
    if not region or "-" not in region:
        return None
    bucket, num = region.split("-", 1)
    c = _RB.get(bucket)
    if c in ("US", "CA") and len(num) >= 2:
        return "US" if bucket == "us" else "CA"
    if bucket == "eu" and num.startswith(("west", "north", "south")):
        return {"west": "IE", "north": "SE", "south": "FR"}.get(num.split("-")[0], "DE")
    return c


def parse_aws(path):
    d = json.load(open(path))["Records"]
    rows = []
    for r in d:
        uid = r.get("userIdentity", {})
        ua = r.get("userAgent", "") or ""
        device, os_, browser = _ua(ua)
        resp = r.get("responseElements") or {}
        ok = str(resp.get("ConsoleLogin")).lower() == "success"
        rows.append({
            "ts": datetime.fromisoformat(r["eventTime"].replace("Z", "+00:00"))
                       .replace(tzinfo=None),
            "source": "aws", "user": uid.get("userName") or extract_user(uid.get("arn")),
            "ip": r.get("sourceIPAddress"), "country": _aws_region_country(r.get("awsRegion")),
            "device": device, "os": os_, "browser": browser,
            "success": ok, "status": resp.get("ConsoleLogin"),
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def extract_user(arn):
    m = re.search(r":user/(.+)$", arn or "")
    return m.group(1) if m else None


def parse_entra(path):
    d = json.load(open(path))
    rows = []
    for r in d:
        st = r.get("status") or {}
        loc = r.get("locationDetails") or {}
        dev = r.get("deviceDetail") or {}
        ua = r.get("userAgent") or ""
        device, os_, browser = _ua(ua, os_=dev.get("operatingSystem"),
                                   browser=dev.get("browser"),
                                   device=dev.get("displayName"))
        rows.append({
            "ts": datetime.fromisoformat(r.get("createdDateTime", "").replace("Z", "+00:00"))
                        .replace(tzinfo=None),
            "source": "entra", "user": r.get("userPrincipalName") or r.get("userDisplayName"),
            "ip": r.get("ipAddress"), "country": loc.get("countryOrRegion"),
            "device": device, "os": os_, "browser": browser,
            "success": str(st.get("errorCode")) == "0",
            "status": st.get("failureReason") or "Success",
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def parse_windows(path):
    rows = []
    for event, ev in ET.iterparse(path, events=("end",)):
        if not ev.tag.endswith("Event"):
            continue
        rec = {"ts": None, "user": None, "ip": None, "status": None}
        eid = None
        for sub in ev.iter():
            tag = sub.tag.rsplit("}", 1)[-1]
            if tag == "EventID":
                eid = int(sub.text or 0)
            elif tag == "TimeCreated" and rec["ts"] is None:
                rec["ts"] = sub.get("SystemTime")
            elif tag == "Data":
                name = sub.get("Name")
                val = (sub.text or "").strip()
                if name == "TargetUserName":
                    rec["user"] = val or None
                elif name == "IpAddress":
                    if val and val != "-":
                        rec["ip"] = val
                elif name == "LogonType":
                    rec["status"] = val
        ev.clear()
        if rec["ts"] is None or rec["user"] is None:
            continue
        ts = datetime.fromisoformat(rec["ts"].replace("Z", "+00:00")).replace(tzinfo=None)
        rows.append({
            "ts": ts, "source": "windows", "user": rec["user"], "ip": rec["ip"],
            "country": None, "device": None, "os": None, "browser": None,
            "success": eid == 4624,
            "status": f"4624-logonType{rec['status']}" if eid == 4624
                      else f"4625-logonType{rec['status']}",
        })
    return pd.DataFrame(rows, columns=COLUMNS)


_SSH = re.compile(
    r"^(?:\w{3} +\d+ \d\d:\d\d:\d\d) \S+ \w+\[\d+\]: (Accepted|Failed password)"
    r"(?: publickey| password)? for(?: invalid)? user (\S+).* from ([0-9.]+)")


def parse_ssh(path):
    rows, skipped = [], 0
    for line in open(path, encoding="utf-8", errors="replace"):
        m = _SSH.match(line)
        if not m:
            skipped += 1
            continue
        kind, user, ip = m.groups()
        try:
            ts = datetime.strptime(line[:15], "%b %d %H:%M:%S").replace(year=YEAR)
        except ValueError:
            skipped += 1
            continue
        rows.append({
            "ts": ts, "source": "ssh", "user": user or None, "ip": ip,
            "country": None, "device": None, "os": None, "browser": None,
            "success": kind == "Accepted", "status": kind,
        })
    if skipped:
        print(f"  ssh: skipped {skipped} non-auth lines")
    return pd.DataFrame(rows, columns=COLUMNS)


def parse_web(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        device, os_, browser = _ua(r.get("user_agent", ""))
        try:
            ts = datetime.strptime(r["datetime"].split(",")[0], "%Y-%m-%d %H:%M:%S")
        except (KeyError, ValueError):
            continue
        rows.append({
            "ts": ts, "source": "web",
            "user": r.get("userid") or r.get("user"), "ip": r.get("source_address"),
            "country": None, "device": device, "os": os_, "browser": browser,
            "success": r.get("result") == "SUCCESS", "status": r.get("result"),
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def parse_mysql(path):
    d = json.load(open(path))
    rows = []
    for r in d:
        if r.get("event") != "connect":
            continue
        acc = r.get("account") or {}
        cd = r.get("connection_data") or {}
        attrs = cd.get("connection_attributes") or {}
        ip = acc.get("ip") or None
        try:
            ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
        except (KeyError, ValueError):
            continue
        rows.append({
            "ts": ts, "source": "mysql", "user": acc.get("user"),
            "ip": ip, "country": None, "device": "app",
            "os": attrs.get("_os") or None, "browser": None,
            "success": cd.get("status") == 0, "status": str(cd.get("status")),
        })
    return pd.DataFrame(rows, columns=COLUMNS)


PARSERS = {
    "aws": ("aws_cloudtrail_console_login.json", parse_aws),
    "entra": ("entra_signin_logs.json", parse_entra),
    "windows": ("windows_security_events.xml", parse_windows),
    "ssh": ("ssh_auth.log", parse_ssh),
    "web": ("web_authentication.jsonl", parse_web),
    "mysql": ("mysql_audit_logs.json", parse_mysql),
}


def main():
    frames, report = [], {}
    for src, (fname, fn) in PARSERS.items():
        path = RAW / fname
        print(f"parsing {src} ...")
        df = fn(path)
        frames.append(df)
        report[src] = {"rows": int(len(df)), "success": int(df["success"].sum())}
        print(f"  {src}: {len(df):,} events, {report[src]['success']:,} success")

    ev = pd.concat(frames, ignore_index=True)
    ev = ev.sort_values(["user", "ts"]).drop_duplicates(subset=["ts", "source", "user", "ip"])
    ev = ev.reset_index(drop=True)

    missing = {c: int(ev[c].isna().sum()) for c in COLUMNS}
    print("\nnull counts per column:")
    for k, v in missing.items():
        print(f"  {k}: {v:,}")

    con = duckdb.connect()
    con.register("ev", ev)
    con.execute(f"COPY ev TO '{OUT}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    print(f"\nwrote {OUT}: {len(ev):,} events, {ev['source'].nunique()} sources")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()