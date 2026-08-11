import pandas as pd
import re

INPUT_FILE = "rba-cleaned-step1.csv"
OUTPUT_FILE = "rba-cleaned-step2.csv"

CHUNK_SIZE = 100000

print("Cleaning browser names...")

first_chunk = True

for chunk in pd.read_csv(INPUT_FILE, chunksize=CHUNK_SIZE):

    browser = chunk["Browser Name and Version"].fillna("").str.lower()

    def browser_family(x):

        if "zipppbot" in x:
            return "ZipppBot"

        if "linkbot" in x:
            return "Linkbot"

        if "startmebot" in x:
            return "StartMeBot"

        if "awariosmartbot" in x:
            return "AwarioSmartBot"

        if "vlc" in x:
            return "VLC"

        if "webview" in x:
            return "Chrome WebView"

        if "chrome mobile" in x:
            return "Chrome Mobile"

        if "chrome" in x:
            return "Chrome"

        if "firefox" in x:
            return "Firefox"

        if "edge" in x:
            return "Edge"

        if "opera" in x:
            return "Opera"

        if "safari" in x:
            return "Safari"

        if "android" in x:
            return "Android Browser"

        return "Other"

    chunk["Browser_Family"] = browser.apply(browser_family)

    chunk.to_csv(
        OUTPUT_FILE,
        mode="w" if first_chunk else "a",
        header=first_chunk,
        index=False
    )

    first_chunk = False

print("Browser cleaning completed.")