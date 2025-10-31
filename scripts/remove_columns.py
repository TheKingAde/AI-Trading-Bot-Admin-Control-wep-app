import sqlite3
import sys

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else r"data/2-training_data.db"
TABLE_NAME = sys.argv[2] if len(sys.argv) > 2 else "training_data"
COLUMNS_TO_REMOVE = ["Entry", "Exit_Price", "SL", "TP"]

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get current columns
cursor.execute(f"PRAGMA table_info({TABLE_NAME})")
columns = [row[1] for row in cursor.fetchall()]

for col in COLUMNS_TO_REMOVE:
    if col in columns:
        print(f"Removing column: {col}")
        cursor.execute(f"ALTER TABLE {TABLE_NAME} DROP COLUMN {col}")
    else:
        print(f"Column not found: {col}")

conn.commit()
conn.close()
print("✅ Done removing columns.")
