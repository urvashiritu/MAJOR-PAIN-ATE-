import duckdb
import os
import glob

INPUT_FILE = "rba_dataset/processed/rba-featured-v2.csv"
PROFILE_DIR = "rba_dataset/processed/user_profile_parts"
OUTPUT_FILE = "rba_dataset/processed/user_profiles.csv"

CHUNK_ROWS = 1_000_000

os.makedirs(PROFILE_DIR, exist_ok=True)

print("=" * 80)
print("BUILDING USER PROFILES - LOW MEMORY MODE")
print("=" * 80)

con = duckdb.connect()

# Limit DuckDB memory so it does not consume all your RAM
con.execute("SET threads = 4")
con.execute("SET memory_limit = '4GB'")
con.execute("SET preserve_insertion_order = false")

# -------------------------------------------------------------------
# STEP 1: Get total rows
# -------------------------------------------------------------------

print("\nChecking dataset...")

total_rows = con.execute(f"""
    SELECT COUNT(*)
    FROM read_csv_auto(
        '{INPUT_FILE}',
        header=true,
        strict_mode=false,
        null_padding=true,
        ignore_errors=true,
        sample_size=50000
    )
""").fetchone()[0]

print("Total rows:", total_rows)

# -------------------------------------------------------------------
# STEP 2: Build profiles directly with DuckDB
# -------------------------------------------------------------------

print("\nBuilding user profiles...")
print("This may take some time, but memory usage is limited.")

# Instead of trying to load everything into pandas,
# DuckDB performs aggregation internally.

query = f"""
COPY (
    SELECT
        "User ID",

        COUNT(*) AS Total_Logins,

        MIN("Login Timestamp") AS First_Login,
        MAX("Login Timestamp") AS Last_Login,

        SUM(
            CASE WHEN "Login Successful" = TRUE
            THEN 1 ELSE 0 END
        ) AS Successful_Logins,

        SUM(
            CASE WHEN "Login Successful" = FALSE
            THEN 1 ELSE 0 END
        ) AS Failed_Logins,

        SUM(
            CASE WHEN "Is Attack IP" = TRUE
            THEN 1 ELSE 0 END
        ) AS Attack_IP_Logins,

        SUM(
            CASE WHEN "Is Account Takeover" = TRUE
            THEN 1 ELSE 0 END
        ) AS ATO_Count,

        COUNT(DISTINCT Country) AS Unique_Countries,

        COUNT(DISTINCT "Device Type") AS Unique_Devices,

        COUNT(DISTINCT Browser_Family) AS Unique_Browsers,

        COUNT(DISTINCT OS_Family) AS Unique_OS,

        SUM(
            CASE WHEN Country_Change = 1
            THEN 1 ELSE 0 END
        ) AS Country_Changes,

        SUM(
            CASE WHEN Device_Change = 1
            THEN 1 ELSE 0 END
        ) AS Device_Changes,

        SUM(
            CASE WHEN New_Browser = 1
            THEN 1 ELSE 0 END
        ) AS New_Browser_Count,

        SUM(
            CASE WHEN New_OS = 1
            THEN 1 ELSE 0 END
        ) AS New_OS_Count,

        AVG(
            CASE
                WHEN Time_Since_Last_Login >= 0
                THEN Time_Since_Last_Login
                ELSE NULL
            END
        ) AS Avg_Time_Between_Logins,

        SUM(
            CASE WHEN Night_Login = 1
            THEN 1 ELSE 0 END
        ) AS Night_Logins,

        SUM(
            CASE WHEN Is_Weekend = 1
            THEN 1 ELSE 0 END
        ) AS Weekend_Logins,

        SUM(
            CASE WHEN Browser_OS_Mismatch = 1
            THEN 1 ELSE 0 END
        ) AS Browser_OS_Mismatches,

        SUM(
            CASE WHEN Is_First_Login = 1
            THEN 1 ELSE 0 END
        ) AS First_Login_Count

    FROM read_csv_auto(
        '{INPUT_FILE}',
        header=true,
        strict_mode=false,
        null_padding=true,
        ignore_errors=true,
        sample_size=50000
    )

    GROUP BY "User ID"
)
TO '{OUTPUT_FILE}'
(FORMAT CSV, HEADER)
"""

print("\nRunning aggregation...")
print("Do NOT open the CSV in VS Code while this is running.")

con.execute(query)

# -------------------------------------------------------------------
# STEP 3: Verify result
# -------------------------------------------------------------------

print("\nVerifying user profiles...")

users = con.execute(f"""
    SELECT COUNT(*)
    FROM read_csv_auto(
        '{OUTPUT_FILE}',
        header=true
    )
""").fetchone()[0]

print()
print("=" * 80)
print("USER PROFILE CREATION COMPLETE")
print("=" * 80)

print("Users in profile :", users)
print("Output file      :", OUTPUT_FILE)

con.close()