import sqlite3

DB_PATH = r"data/2-training_data.db"
TABLE_NAME = "training_data"
COLUMN = "Win"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute(f"SELECT {COLUMN} FROM {TABLE_NAME}")
values = [row[0] for row in cursor.fetchall()]

# Convert all values to int (ignore errors)
int_values = []
for v in values:
    try:
        int_values.append(int(v))
    except (ValueError, TypeError):
        continue

win_count = sum(1 for v in int_values if v == 1)
loss_count = sum(1 for v in int_values if v == 0)
be_count = sum(1 for v in int_values if v == 2)

total = len(int_values)
print(f"Total rows: {total}")
print(f"Wins (1): {win_count}")
print(f"Losses (0): {loss_count}")
print(f"Breakevens (2): {be_count}")
conn.close()
