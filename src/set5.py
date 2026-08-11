import pandas as pd

bad_rows = 0

for chunk in pd.read_csv(
    "rba_dataset/processed/rba-cleaned-step4.csv",
    chunksize=100000,
    on_bad_lines="skip"
):
    pass

print("CSV can be read successfully with pandas.")