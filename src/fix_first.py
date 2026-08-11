import duckdb

INPUT_FILE = "rba_dataset/processed/rba-featured.csv"
OUTPUT_FILE = "rba_dataset/processed/rba-featured-v2.csv"

print("=" * 80)
print("FIXING FIRST LOGIN FEATURE")
print("=" * 80)

con = duckdb.connect()
con.execute("SET threads = 8")

query = f"""
COPY (
    SELECT
        "Login Timestamp",
        "User ID",
        "IP Address",
        "Country",
        "Region",
        "City",
        "ASN",
        "Browser Name and Version",
        "OS Name and Version",
        "Device Type",
        "Login Successful",
        "Is Attack IP",
        "Is Account Takeover",
        "Browser_Family",
        "OS_Family",
        "Browser_OS_Mismatch",
        "Login_Hour",
        "Weekday",
        "Is_Weekend",
        "Night_Login",
        "Country_Change",
        "Device_Change",
        "New_Browser",
        "New_OS",

        CASE
            WHEN CAST(Time_Since_Last_Login AS DOUBLE) = -1
            THEN NULL
            ELSE CAST(Time_Since_Last_Login AS DOUBLE)
        END AS Time_Since_Last_Login,

        "Failed_Before_Success",

        CASE
            WHEN CAST(Time_Since_Last_Login AS DOUBLE) = -1
            THEN 1
            ELSE 0
        END AS Is_First_Login

    FROM read_csv(
        '{INPUT_FILE}',
        header = true,
        delim = ',',
        quote = '"',
        escape = '"',

        columns = {{
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
            'Failed_Before_Success': 'BIGINT'
        }},

        strict_mode = false,
        null_padding = true
    )
)
TO '{OUTPUT_FILE}'
(FORMAT CSV, HEADER);
"""

print("Processing dataset...")
print("This may take some time for 31M rows.")

con.execute(query)

print()
print("=" * 80)
print("SUCCESS")
print("=" * 80)
print("Output:", OUTPUT_FILE)

con.close()