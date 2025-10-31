import sqlite3
import re

DB_PATH = r"data/2-training_data.db"
TABLE_NAME = "training_data"
COLUMN = "Win"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get all rows with the Win column
cursor.execute(f"SELECT rowid, {COLUMN} FROM {TABLE_NAME}")
rows = cursor.fetchall()

for rowid, val in rows:
    if val is not None:
        # Extract the number from strings like 'Win1', 'Loss1', etc.
        match = re.search(r'(\d+)', str(val))
        if match:
            num = int(match.group(1))
            cursor.execute(f"UPDATE {TABLE_NAME} SET {COLUMN} = ? WHERE rowid = ?", (num, rowid))

conn.commit()
conn.close()
print("✅ Win column updated to numbers only.")