import pandas as pd

INPUT_FILE = "rba-cleaned-step2.csv"
OUTPUT_FILE = "rba-cleaned-step3.csv"

CHUNK_SIZE = 100000

print("Cleaning operating systems...")

first_chunk = True

for chunk in pd.read_csv(INPUT_FILE, chunksize=CHUNK_SIZE):

    os_col = chunk["OS Name and Version"].fillna("").str.lower()

    def os_family(x):

        if "android" in x:
            return "Android"

        if "ios" in x:
            return "iOS"

        if "mac" in x:
            return "MacOS"

        if "windows phone" in x:
            return "Windows Phone"

        if "windows" in x:
            return "Windows"

        if "chrome os" in x:
            return "ChromeOS"

        if "kaios" in x:
            return "KaiOS"

        if "chromecast" in x:
            return "Chromecast"

        if "other" in x:
            return "Other"

        return "Other"

    chunk["OS_Family"] = os_col.apply(os_family)

    chunk.to_csv(
        OUTPUT_FILE,
        mode="w" if first_chunk else "a",
        header=first_chunk,
        index=False
    )

    first_chunk = False

print("OS cleaning completed.")