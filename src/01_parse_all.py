#!/usr/bin/env python3
"""Ingest all 6 data sources into DuckDB with normalized schema."""

import duckdb
import json
import re
from pathlib import Path

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "auth.duckdb"

SSH_RE = re.compile(
    r"^(\w+ \d+ \d+:\d+:\d+) \S+ sshd\[\d+\]: "
    r"(Accepted|Failed) \S+ (?:for )?(?:invalid user )?(\S+)? "
    r"from (\S+) port \d+"
)


def main():
    con = duckdb.connect(str(DB_PATH))
    con.execute("DROP TABLE IF EXISTS auth_events")

    # ── SSH ──
    print("Loading SSH ...")
    ssh_lines = (DATA_DIR / "ssh_auth.log").read_text().splitlines()
    ssh_tmp = DATA_DIR / "_ssh_tmp.csv"
    with open(ssh_tmp, "w") as f:
        f.write("timestamp,src_user,src_ip,success,source,auth_type\n")
        for line in ssh_lines:
            m = SSH_RE.match(line)
            if m:
                ts, status, user, ip = m.groups()
                f.write(f"2026-{ts},{user or ''},{ip},{status == 'Accepted'},SSH,password\n")
    con.execute("""
        CREATE TABLE auth_events AS
        SELECT timestamp, src_user, src_ip, (success = 'True') AS success, source, auth_type
        FROM read_csv_auto($1, header=true)
    """, [str(ssh_tmp)])
    ssh_tmp.unlink(missing_ok=True)

    # ── Web ──
    print("Loading Web ...")
    con.execute("""
        INSERT INTO auth_events
        SELECT
            datetime AS timestamp,
            userid AS src_user,
            source_address AS src_ip,
            (result = 'SUCCESS') AS success,
            'WEB' AS source,
            'password' AS auth_type
        FROM read_json_auto($1)
    """, [str(DATA_DIR / "web_authentication.jsonl")])

    # ── AWS (parse with Python — single giant JSON object, DuckDB can't handle) ──
    print("Loading AWS ...")
    aws_tmp = DATA_DIR / "_aws_tmp.jsonl"
    with open(DATA_DIR / "aws_cloudtrail_console_login.json") as f:
        data = json.load(f)
    with open(aws_tmp, "w") as f:
        for rec in data["Records"]:
            row = {
                "timestamp": rec.get("eventTime", ""),
                "src_user": rec.get("userIdentity", {}).get("userName", ""),
                "src_ip": rec.get("sourceIPAddress", ""),
                "success": rec.get("responseElements", {}).get("ConsoleLogin") == "Success",
                "source": "AWS",
                "auth_type": "password",
            }
            f.write(json.dumps(row) + "\n")
    con.execute("""
        INSERT INTO auth_events
        SELECT
            timestamp, src_user, src_ip, success::BOOLEAN, source, auth_type
        FROM read_json_auto($1)
    """, [str(aws_tmp)])
    aws_tmp.unlink(missing_ok=True)

    # ── Entra ──
    print("Loading Entra ...")
    con.execute("""
        INSERT INTO auth_events
        SELECT
            createdDateTime AS timestamp,
            split_part(userPrincipalName, '@', 1) AS src_user,
            ipAddress AS src_ip,
            (conditionalAccessStatus = 'success') AS success,
            'ENTRA' AS source,
            COALESCE(clientAppUsed, 'unknown') AS auth_type
        FROM read_json_auto($1, format='array')
    """, [str(DATA_DIR / "entra_signin_logs.json")])

    # ── MySQL ──
    print("Loading MySQL ...")
    con.execute("""
        INSERT INTO auth_events
        SELECT
            timestamp,
            account.user AS src_user,
            account.ip AS src_ip,
            (COALESCE(connection_data.status, general_data.status) = 0) AS success,
            'MYSQL' AS source,
            'password' AS auth_type
        FROM read_json_auto($1, format='array')
    """, [str(DATA_DIR / "mysql_audit_logs.json")])

    # ── Windows ──
    print("Loading Windows ...")
    con.execute("""
        INSERT INTO auth_events
        SELECT
            TimeCreated AS timestamp,
            TargetUserName AS src_user,
            IpAddress AS src_ip,
            (EventID = 4624) AS success,
            'WINDOWS' AS source,
            COALESCE(AuthenticationPackageName, 'unknown') AS auth_type
        FROM read_json_auto($1)
    """, [str(DATA_DIR / "windows_security_events.json")])

    # ── Stealthy attacks ──
    stealthy_path = DATA_DIR / "stealthy_attacks.jsonl"
    if stealthy_path.exists():
        print("Loading stealthy attacks ...")
        con.execute("""
            INSERT INTO auth_events
            SELECT
                timestamp,
                src_user,
                src_ip,
                success::BOOLEAN,
                source,
                auth_type
            FROM read_json_auto($1)
        """, [str(stealthy_path)])
    else:
        print("No stealthy_attacks.jsonl found, skipping.")

    # ── Stats ──
    total = con.execute("SELECT count(*) FROM auth_events").fetchone()[0]
    by_src = con.execute("SELECT source, count(*) FROM auth_events GROUP BY source ORDER BY 2 DESC").fetchall()
    print(f"\nTotal: {total} events")
    for src, cnt in by_src:
        print(f"  {src}: {cnt}")

    con.close()
    print(f"\nSaved → {DB_PATH}")


if __name__ == "__main__":
    main()
