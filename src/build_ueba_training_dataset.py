"""Build a leakage-safe, event-level dataset for UEBA anomaly modelling.

The output deliberately retains identifiers, timestamps, and known-incident flags
as metadata/evaluation columns.  They must not be passed to an anomaly model.
Only columns listed in MODEL_FEATURES are model inputs.
"""

from pathlib import Path
import argparse

import duckdb


INPUT_FILE = "rba_dataset/processed/rba-featured-v2.csv"
OUTPUT_DIR = "rba_dataset/processed/ueba_model_training_events"
EXPECTED_INPUT_RECORDS = 31_269_264  # CSV rows excluding the header

MODEL_FEATURES = [
    "login_hour_sin", "login_hour_cos", "weekday", "is_weekend", "night_login",
    "is_first_login", "time_gap_missing", "time_since_last_login_log1p",
    "failed_before_success_log1p", "country_change", "device_change",
    "new_browser", "new_os", "browser_os_mismatch", "is_bot_browser",
    "device_missing", "is_private_ip", "is_synthetic_asn",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", required=True, help="Month to build, in YYYY-MM form")
    args = parser.parse_args()
    if not Path(INPUT_FILE).exists():
        raise FileNotFoundError(INPUT_FILE)

    output_file = f"{OUTPUT_DIR}/events_{args.month}.parquet"
    temp_output_file = output_file + ".building"
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads = 4")
    con.execute("SET memory_limit = '4GB'")
    con.execute("SET preserve_insertion_order = true")

    # Use an explicit schema and fail on any malformed source row.  Do not use
    # ignore_errors: silently omitting events is unsafe for security analytics.
    source = f"""
        read_csv(
            '{INPUT_FILE}',
            header=true,
            delim=',',
            quote='"',
            escape='"',
            strict_mode=true,
            null_padding=false,
            ignore_errors=false,
            columns={{
                'Login Timestamp': 'TIMESTAMP',
                'User ID': 'BIGINT',
                'IP Address': 'VARCHAR',
                'Country': 'VARCHAR',
                'Region': 'VARCHAR',
                'City': 'VARCHAR',
                'ASN': 'VARCHAR',
                'Browser Name and Version': 'VARCHAR',
                'OS Name and Version': 'VARCHAR',
                'Device Type': 'VARCHAR',
                'Login Successful': 'BOOLEAN',
                'Is Attack IP': 'BOOLEAN',
                'Is Account Takeover': 'BOOLEAN',
                'Browser_Family': 'VARCHAR',
                'OS_Family': 'VARCHAR',
                'Browser_OS_Mismatch': 'INTEGER',
                'Login_Hour': 'INTEGER',
                'Weekday': 'INTEGER',
                'Is_Weekend': 'INTEGER',
                'Night_Login': 'INTEGER',
                'Country_Change': 'INTEGER',
                'Device_Change': 'INTEGER',
                'New_Browser': 'INTEGER',
                'New_OS': 'INTEGER',
                'Time_Since_Last_Login': 'DOUBLE',
                'Failed_Before_Success': 'BIGINT',
                'Is_First_Login': 'INTEGER'
            }}
        )
    """

    source_count = con.execute(f"SELECT COUNT(*) FROM {source}").fetchone()[0]
    if source_count != EXPECTED_INPUT_RECORDS:
        raise RuntimeError(
            f"Source reconciliation failed: expected {EXPECTED_INPUT_RECORDS:,}, "
            f"read {source_count:,}."
        )

    query = f"""
    COPY (
        SELECT
            "Login Timestamp" AS event_timestamp,
            "User ID" AS user_id,

            -- Model features: numeric, point-in-time, and no target columns.
            SIN(2 * PI() * Login_Hour / 24.0) AS login_hour_sin,
            COS(2 * PI() * Login_Hour / 24.0) AS login_hour_cos,
            Weekday AS weekday,
            Is_Weekend AS is_weekend,
            Night_Login AS night_login,
            Is_First_Login AS is_first_login,
            CAST(Time_Since_Last_Login IS NULL AS INTEGER) AS time_gap_missing,
            LN(1 + GREATEST(COALESCE(Time_Since_Last_Login, 0.0), 0.0))
                AS time_since_last_login_log1p,
            LN(1 + GREATEST(Failed_Before_Success, 0))
                AS failed_before_success_log1p,
            Country_Change AS country_change,
            Device_Change AS device_change,
            New_Browser AS new_browser,
            New_OS AS new_os,
            Browser_OS_Mismatch AS browser_os_mismatch,
            CAST(Browser_Family IN ('ZipppBot', 'Linkbot', 'StartMeBot', 'AwarioSmartBot') AS INTEGER)
                AS is_bot_browser,
            CAST("Device Type" IS NULL OR TRIM("Device Type") = '' AS INTEGER)
                AS device_missing,
            CAST("IP Address" LIKE '10.%' AS INTEGER) AS is_private_ip,
            CAST(TRY_CAST(ASN AS BIGINT) >= 500000 AS INTEGER) AS is_synthetic_asn,

            -- Evaluation only: never include these in X during unsupervised fitting.
            CAST("Login Successful" AS INTEGER) AS eval_login_successful,
            CAST("Is Attack IP" AS INTEGER) AS eval_is_attack_ip,
            CAST("Is Account Takeover" AS INTEGER) AS eval_is_account_takeover
        FROM {source}
        WHERE STRFTIME("Login Timestamp", '%Y-%m') = '{args.month}'
    ) TO '{temp_output_file}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """
    con.execute(query)

    output_count, null_features = con.execute(
        "SELECT COUNT(*), "
        + " + ".join(f"COUNT(*) FILTER (WHERE {name} IS NULL)" for name in MODEL_FEATURES)
        + f" FROM read_parquet('{temp_output_file}')"
    ).fetchone()
    if null_features != 0:
        raise RuntimeError(f"Model-feature null check failed: {null_features:,} null values.")

    Path(temp_output_file).replace(output_file)

    print(f"Created: {output_file}")
    print(f"Rows: {output_count:,}; source rows: {source_count:,}; model features: {len(MODEL_FEATURES)}; feature nulls: 0")
    print("MODEL_FEATURES =", ", ".join(MODEL_FEATURES))
    con.close()


if __name__ == "__main__":
    main()
