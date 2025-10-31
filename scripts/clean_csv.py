import csv

input_path = "data/2-clean_trades.csv"
output_path = "data/2-clean_trades_cleaned.csv"

with open(input_path, "r", encoding="utf-16") as infile, open(output_path, "w", encoding="utf-16", newline="") as outfile:
    reader = csv.reader(infile, delimiter=";")
    writer = csv.writer(outfile, delimiter=";")
    header = next(reader)
    writer.writerow(header)
    col_count = len(header)
    for row in reader:
        # Only keep the first N columns, pad with empty strings if too short
        clean_row = row[:col_count] + [""] * (col_count - len(row))
        writer.writerow(clean_row)

print(f"✅ Cleaned CSV saved to {output_path}")