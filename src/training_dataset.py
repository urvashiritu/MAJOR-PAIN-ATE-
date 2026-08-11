import duckdb

FILE = "rba_dataset/processed/final_training_dataset_v2.csv"

con = duckdb.connect()

print("=" * 80)
print("FINAL FEATURE AUDIT")
print("=" * 80)

features = [
    "Login_Hour",
    "Weekday",
    "Is_Weekend",
    "Night_Login",
    "Country_Change",
    "Device_Change",
    "New_Browser",
    "New_OS",
    "Time_Since_Last_Login",
    "Failed_Before_Success",
    "Is_First_Login",
    "Browser_OS_Mismatch"
]

# --------------------------------------------------
# 1. Basic statistics
# --------------------------------------------------

feature_sql = ",\n".join(
    f'''
    MIN("{col}") AS "{col}_min",
    MAX("{col}") AS "{col}_max",
    AVG("{col}") AS "{col}_mean",
    COUNT(*) FILTER (WHERE "{col}" IS NULL) AS "{col}_missing"
    '''
    for col in features
)

query = f"""
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT "User ID") AS unique_users,
    {feature_sql}
FROM read_csv_auto(
    '{FILE}',
    sample_size=-1,
    strict_mode=false,
    null_padding=true
)
"""

result = con.execute(query).fetchone()
columns = [desc[0] for desc in con.description]

print("\nDATASET")
print("-" * 80)

print("Rows        :", result[0])
print("Unique users:", result[1])

print("\nFEATURE STATISTICS")
print("-" * 80)

for i, name in enumerate(columns[2:], start=2):
    print(f"{name:40} : {result[i]}")

# --------------------------------------------------
# 2. Boolean feature distributions
# --------------------------------------------------

boolean_features = [
    "Is_Weekend",
    "Night_Login",
    "Country_Change",
    "Device_Change",
    "New_Browser",
    "New_OS",
    "Is_First_Login",
    "Browser_OS_Mismatch"
]

print("\n")
print("=" * 80)
print("BOOLEAN FEATURE DISTRIBUTIONS")
print("=" * 80)

for col in boolean_features:

    print(f"\n{col}")

    query = f"""
    SELECT
        "{col}" AS value,
        COUNT(*) AS count
    FROM read_csv_auto(
        '{FILE}',
        sample_size=-1,
        strict_mode=false,
        null_padding=true
    )
    GROUP BY "{col}"
    ORDER BY "{col}"
    """

    rows = con.execute(query).fetchall()

    for value, count in rows:
        print(f"  {value} : {count}")

# --------------------------------------------------
# 3. Important numerical distributions
# --------------------------------------------------

print("\n")
print("=" * 80)
print("NUMERICAL FEATURE DISTRIBUTIONS")
print("=" * 80)

for col in [
    "Time_Since_Last_Login",
    "Failed_Before_Success"
]:

    query = f"""
    SELECT
        MIN("{col}"),
        QUANTILE_CONT("{col}", 0.25),
        QUANTILE_CONT("{col}", 0.50),
        QUANTILE_CONT("{col}", 0.75),
        QUANTILE_CONT("{col}", 0.90),
        QUANTILE_CONT("{col}", 0.95),
        QUANTILE_CONT("{col}", 0.99),
        MAX("{col}")
    FROM read_csv_auto(
        '{FILE}',
        sample_size=-1,
        strict_mode=false,
        null_padding=true
    )
    """

    r = con.execute(query).fetchone()

    print(f"\n{col}")
    print("  Min :", r[0])
    print("  25% :", r[1])
    print("  50% :", r[2])
    print("  75% :", r[3])
    print("  90% :", r[4])
    print("  95% :", r[5])
    print("  99% :", r[6])
    print("  Max :", r[7])

print("\n")
print("=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)