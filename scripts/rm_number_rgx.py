import sqlite3
import re

DB_PATH = r"data/1-training_data.db"
TABLE_NAME = "training_data"
COLUMN = "Outcome"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get all rows with the Win column
cursor.execute(f"SELECT rowid, {COLUMN} FROM {TABLE_NAME}")
rows = cursor.fetchall()

for rowid, val in rows:
    if val is not None:
        # Extract the word (letters) from strings like 'Win1', 'Loss0', etc.
        match = re.match(r'([A-Za-z]+)', str(val))
        if match:
            word = match.group(1)
            cursor.execute(f"UPDATE {TABLE_NAME} SET {COLUMN} = ? WHERE rowid = ?", (word, rowid))

conn.commit()
conn.close()
print("✅ Win column updated to words only.")