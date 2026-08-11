import pandas as pd

# Input and output files
INPUT_FILE = "rba-dataset.csv"
OUTPUT_FILE = "rba-cleaned-step1.csv"

# Read 100k rows at a time
CHUNK_SIZE = 100000

# Columns to remove
DROP_COLUMNS = [
    "index",
    "Round-Trip Time [ms]",
    "User Agent String"
]

print("Starting dataset cleaning...")

first_chunk = True
total_rows = 0

for chunk in pd.read_csv(INPUT_FILE, chunksize=CHUNK_SIZE):

    # Remove unwanted columns
    chunk.drop(columns=DROP_COLUMNS, inplace=True)

    # Save to a new CSV
    chunk.to_csv(
        OUTPUT_FILE,
        mode="w" if first_chunk else "a",
        header=first_chunk,
        index=False
    )

    total_rows += len(chunk)

    print(f"Processed {total_rows:,} rows")

    first_chunk = False

print("\nCleaning completed successfully!")
print(f"Cleaned dataset saved as: {OUTPUT_FILE}")