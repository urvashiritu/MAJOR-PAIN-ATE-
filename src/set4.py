import pandas as pd

INPUT_FILE = "rba-cleaned-step3.csv"
OUTPUT_FILE = "rba-cleaned-step4.csv"

CHUNK_SIZE = 100000

print("Creating Browser–OS mismatch feature...")

first_chunk = True

for chunk in pd.read_csv(INPUT_FILE, chunksize=CHUNK_SIZE):

    mismatch = (
        ((chunk["Browser_Family"] == "Android Browser") & (chunk["OS_Family"] != "Android")) |
        ((chunk["Browser_Family"] == "Safari") & (chunk["OS_Family"] != "iOS")) |
        ((chunk["Browser_Family"] == "Chrome WebView") & (chunk["OS_Family"] != "Android"))
    )

    chunk["Browser_OS_Mismatch"] = mismatch.astype(int)

    chunk.to_csv(
        OUTPUT_FILE,
        mode="w" if first_chunk else "a",
        header=first_chunk,
        index=False
    )

    first_chunk = False

print("Mismatch feature added.")

bot_browsers = [
    "ZipppBot",
    "Linkbot",
    "StartMeBot",
    "AwarioSmartBot"
]

chunk["Is_Bot_Browser"] = chunk["Browser_Family"].isin(bot_browsers).astype(int)