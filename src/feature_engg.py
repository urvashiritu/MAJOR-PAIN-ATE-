import pandas as pd

INPUT_FILE = "rba_dataset/processed/rba-cleaned-step4.csv"
OUTPUT_FILE = "rba_dataset/processed/rba-featured.csv"

CHUNK_SIZE = 100000

print("Creating behavioural features...")

first_chunk = True

# ---------- Dictionaries ----------

last_country = {}
last_device = {}
seen_browser = {}
seen_os = {}
last_timestamp = {}
failed_count = {}

for chunk in pd.read_csv(
        INPUT_FILE,
        chunksize=CHUNK_SIZE,
        parse_dates=["Login Timestamp"]):

    # ---------------------------------
    # Login Hour
    # ---------------------------------

    chunk["Login_Hour"] = chunk["Login Timestamp"].dt.hour

    # ---------------------------------
    # Weekday
    # ---------------------------------

    chunk["Weekday"] = chunk["Login Timestamp"].dt.dayofweek

    # ---------------------------------
    # Weekend
    # ---------------------------------

    chunk["Is_Weekend"] = (
        chunk["Weekday"] >= 5
    ).astype(int)

    # ---------------------------------
    # Night Login
    # ---------------------------------

    chunk["Night_Login"] = (
        chunk["Login_Hour"] < 6
    ).astype(int)

    # Columns to create

    country_change = []
    device_change = []
    new_browser = []
    new_os = []
    time_since_last = []
    failed_before_success = []

    # ---------------------------------

    for row in chunk.itertuples(index=False):

        uid = row._1      # User ID
        ts = row._0       # Login Timestamp

        country = row.Country
        device = row._9          # Device Type
        browser = row.Browser_Family
        os = row.OS_Family
        success = row._10        # Login Successful

        # ---------------------------------
        # Country Change
        # ---------------------------------

        if uid not in last_country:
            country_change.append(0)
        else:
            country_change.append(
                int(last_country[uid] != country)
            )

        last_country[uid] = country

        # ---------------------------------
        # Device Change
        # ---------------------------------

        if uid not in last_device:
            device_change.append(0)
        else:
            device_change.append(
                int(last_device[uid] != device)
            )

        last_device[uid] = device

        # ---------------------------------
        # New Browser
        # ---------------------------------

        if uid not in seen_browser:
            seen_browser[uid] = set()

        if browser in seen_browser[uid]:
            new_browser.append(0)
        else:
            new_browser.append(1)
            seen_browser[uid].add(browser)

        # ---------------------------------
        # New OS
        # ---------------------------------

        if uid not in seen_os:
            seen_os[uid] = set()

        if os in seen_os[uid]:
            new_os.append(0)
        else:
            new_os.append(1)
            seen_os[uid].add(os)

        # ---------------------------------
        # Time Since Last Login
        # ---------------------------------

        if uid not in last_timestamp:
            time_since_last.append(-1)
        else:
            delta = (
                ts -
                last_timestamp[uid]
            ).total_seconds()

            time_since_last.append(delta)

        last_timestamp[uid] = ts

        # ---------------------------------
        # Failed Before Success
        # ---------------------------------

        if uid not in failed_count:
            failed_count[uid] = 0

        if success:
            failed_before_success.append(
                failed_count[uid]
            )
            failed_count[uid] = 0
        else:
            failed_before_success.append(
                failed_count[uid]
            )
            failed_count[uid] += 1

    # ---------------------------------

    chunk["Country_Change"] = country_change
    chunk["Device_Change"] = device_change
    chunk["New_Browser"] = new_browser
    chunk["New_OS"] = new_os
    chunk["Time_Since_Last_Login"] = time_since_last
    chunk["Failed_Before_Success"] = failed_before_success

    chunk.to_csv(
        OUTPUT_FILE,
        mode="w" if first_chunk else "a",
        header=first_chunk,
        index=False
    )

    first_chunk = False

print("Feature engineering completed.")