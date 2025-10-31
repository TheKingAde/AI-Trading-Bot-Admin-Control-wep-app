import sqlite3

DB_PATH = r"data/4-feature_subset_breakeven.db"
TABLE_NAME = "training_data"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Update Win column based on Outcome
cursor.execute(f"SELECT rowid, Outcome FROM {TABLE_NAME}")
rows = cursor.fetchall()

for rowid, outcome in rows:
    if outcome is not None:
        val = str(outcome).strip().lower()
        if val in ["be", "breakeven", "2"]:
            win_val = 2
        elif val in ["win", "1"]:
            win_val = 1
        elif val in ["loss", "lose", "0"]:
            win_val = 0
        else:
            continue  # skip unknowns
        cursor.execute(f"UPDATE {TABLE_NAME} SET Win = ? WHERE rowid = ?", (win_val, rowid))

conn.commit()
conn.close()
print("✅ Win column updated from Outcome column.")
