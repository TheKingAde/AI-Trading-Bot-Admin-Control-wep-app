import pandas as pd
import sqlite3
from pathlib import Path

# === CONFIG ===
CSV_PATH = Path("data/2-clean_trades_cleaned.csv")
DB_PATH = Path("data/1-training_data.db")
TABLE_NAME = "training_data"

# === READ CSV ===
df = pd.read_csv(CSV_PATH, sep=';', encoding='utf-16', dtype=str, keep_default_na=False)
print(f"✅ Loaded CSV: {len(df):,} rows × {len(df.columns)} columns")

# === CLEAN COLUMN NAMES ===
df.columns = [str(c).strip().replace(" ", "_").replace("-", "_") for c in df.columns]

# === CHECK FOR DUPLICATE COLUMNS ===
if len(df.columns) != len(set(df.columns)):
    raise ValueError("Duplicate column names found in CSV!")

# === CREATE / CONNECT TO DATABASE ===
conn = sqlite3.connect(DB_PATH)

# === WRITE TO SQLITE ===
df.to_sql(TABLE_NAME, conn, if_exists='replace', index=False, method='multi')

# === VALIDATE EXPORT ===
df_check = pd.read_sql_query(f"SELECT * FROM {TABLE_NAME} LIMIT 5", conn)
print("Sample from DB after export:")
print(df_check.head())

conn.close()
print(f"💾 Exported to {DB_PATH} (table: {TABLE_NAME}) successfully.")