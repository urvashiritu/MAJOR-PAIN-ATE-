import duckdb

FILE = "rba_dataset/processed/user_profiles.csv"

con = duckdb.connect()

con.execute("SET threads = 4")
con.execute("SET memory_limit = '2GB'")

print("=" * 80)
print("USER PROFILE ANALYSIS")
print("=" * 80)

# ------------------------------------------------------------
# BASIC STATISTICS
# ------------------------------------------------------------

print("\nUSER STATISTICS")
print("-" * 80)

result = con.execute(f"""
SELECT
    COUNT(*) AS Users,
    AVG(Total_Logins) AS Avg_Logins,
    MEDIAN(Total_Logins) AS Median_Logins,
    MAX(Total_Logins) AS Max_Logins
FROM read_csv_auto('{FILE}')
""").fetchone()

print("Users          :", result[0])
print("Average logins :", round(result[1], 2))
print("Median logins  :", result[2])
print("Maximum logins :", result[3])


# ------------------------------------------------------------
# USERS BY ACTIVITY
# ------------------------------------------------------------

print("\nUSERS BY LOGIN COUNT")
print("-" * 80)

result = con.execute(f"""
SELECT
    CASE
        WHEN Total_Logins = 1 THEN '1'
        WHEN Total_Logins BETWEEN 2 AND 5 THEN '2-5'
        WHEN Total_Logins BETWEEN 6 AND 10 THEN '6-10'
        WHEN Total_Logins BETWEEN 11 AND 100 THEN '11-100'
        WHEN Total_Logins BETWEEN 101 AND 1000 THEN '101-1000'
        WHEN Total_Logins BETWEEN 1001 AND 10000 THEN '1001-10000'
        ELSE '10000+'
    END AS Login_Range,

    COUNT(*) AS Users

FROM read_csv_auto('{FILE}')

GROUP BY Login_Range

ORDER BY
    MIN(Total_Logins)
""").fetchall()

for row in result:
    print(f"{row[0]:15} : {row[1]:,}")


# ------------------------------------------------------------
# TOP USERS
# ------------------------------------------------------------

print("\nTOP 20 USERS BY LOGIN COUNT")
print("-" * 80)

result = con.execute(f"""
SELECT
    "User ID",
    Total_Logins,
    Successful_Logins,
    Failed_Logins,
    Attack_IP_Logins,
    ATO_Count,
    Unique_Countries,
    Unique_Devices,
    Unique_Browsers
FROM read_csv_auto('{FILE}')
ORDER BY Total_Logins DESC
LIMIT 20
""").fetchall()

for row in result:
    print(
        f"User: {row[0]} | "
        f"Logins: {row[1]:,} | "
        f"Success: {row[2]:,} | "
        f"Failed: {row[3]:,} | "
        f"Attack IP: {row[4]:,} | "
        f"ATO: {row[5]:,} | "
        f"Countries: {row[6]} | "
        f"Devices: {row[7]} | "
        f"Browsers: {row[8]}"
    )


# ------------------------------------------------------------
# USERS WITH ATTACK ACTIVITY
# ------------------------------------------------------------

print("\nATTACK-ACTIVE USERS")
print("-" * 80)

result = con.execute(f"""
SELECT
    COUNT(*) AS Attack_Users,

    SUM(
        CASE
            WHEN Attack_IP_Logins >= 10
            THEN 1 ELSE 0
        END
    ) AS Users_10plus_Attacks,

    SUM(
        CASE
            WHEN ATO_Count > 0
            THEN 1 ELSE 0
        END
    ) AS ATO_Users

FROM read_csv_auto('{FILE}')
WHERE Attack_IP_Logins > 0
""").fetchone()

print("Users with attack activity :", result[0])
print("Users with 10+ attacks     :", result[1])
print("Users with ATO             :", result[2])


# ------------------------------------------------------------
# HIGH RISK USER PROFILES
# ------------------------------------------------------------

print("\nTOP 20 USERS BY ATTACK COUNT")
print("-" * 80)

result = con.execute(f"""
SELECT
    "User ID",
    Total_Logins,
    Attack_IP_Logins,
    Successful_Logins,
    ATO_Count,
    Unique_Countries
FROM read_csv_auto('{FILE}')
WHERE Attack_IP_Logins > 0
ORDER BY Attack_IP_Logins DESC
LIMIT 20
""").fetchall()

for row in result:
    print(
        f"User: {row[0]} | "
        f"Total: {row[1]:,} | "
        f"Attack IP: {row[2]:,} | "
        f"Success: {row[3]:,} | "
        f"ATO: {row[4]} | "
        f"Countries: {row[5]}"
    )


con.close()

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)