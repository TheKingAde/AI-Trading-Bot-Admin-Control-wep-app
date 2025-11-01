import sqlite3
import pandas as pd

# Path to your SQLite database
DB_PATH = "data/1-training_data_prod.db"
# Table to export
TABLE_NAME = "training_data"
# Output CSV file
CSV_PATH = "data/training_data_export.csv"

# Connect to the database
conn = sqlite3.connect(DB_PATH)

# Read the table into a DataFrame
try:
    df = pd.read_sql_query(f"SELECT * FROM {TABLE_NAME}", conn)
    df.to_csv(CSV_PATH, index=False)
    print(f"✅ Exported {len(df)} rows to {CSV_PATH}")
except Exception as e:
    print(f"❌ Error exporting table: {e}")
finally:
    conn.close()
