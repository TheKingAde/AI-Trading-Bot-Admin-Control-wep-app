import argparse
import csv
import os
import re
import sqlite3
from pathlib import Path
from typing import List, Tuple

# --- Configuration defaults ---
DEFAULT_DB_PATH = Path('data') / 'training_data.db'
DEFAULT_TABLE = 'trades_dataset'
DEFAULT_CSV = Path('training_data_0.1_0.4_2015_2025_10_14.csv')
BATCH_SIZE = 1000

# --- Only keep these columns ---
TARGET_COLUMNS = [
    "Time", "Symbol", "Action", "Entry", "Exit_Price", "SL", "TP",
    "ATR", "ATR_rel", "EMA_diff", "RSI14", "Range_Ratio",
    "Pct_from_30h", "Pct_from_30l", "Breakout_level_atr_multiplier",
    "SL_ATR_Mult", "TP_ATR_Mult", "Use_BE", "Risk_Reward_Ratio",
    "High_Volatility", "Day_of_Week", "Consecutive_Bullish",
    "Consecutive_Bearish", "Avg_Body_Size", "Avg_Range",
    "Trend_Score", "Momentum_Strength", "Profitable", "Final_PnL", "Outcome_Category"
]


def sanitize_column_name(name: str) -> str:
    col = re.sub(r"[^0-9a-zA-Z_]", "_", name.strip())
    if re.match(r"^[0-9]", col):
        col = f"c_{col}"
    return col or "col"


def ensure_db_dir(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)


def create_table(conn: sqlite3.Connection, table: str, columns: List[str]) -> None:
    cols_def = ", ".join([f'"{c}" TEXT' for c in columns])
    sql = f'CREATE TABLE IF NOT EXISTS "{table}" ({cols_def});'
    conn.execute(sql)
    conn.commit()


def create_indexes(conn: sqlite3.Connection, table: str, columns: List[str]) -> None:
    for target in ("Time", "Symbol", "Action"):
        match = next((c for c in columns if c.lower() == target.lower()), None)
        if match:
            conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{table}_{match} ON "{table}"("{match}");')
    conn.commit()


def import_csv_to_sqlite(csv_path: Path, db_path: Path, table: str) -> Tuple[int, List[str]]:
    ensure_db_dir(db_path)
    
    # Try multiple encodings
    encodings_to_try = ['utf-8-sig', 'utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'latin-1', 'cp1252']
    last_error = None
    
    for encoding in encodings_to_try:
        try:
            with csv_path.open('r', encoding=encoding, newline='') as f:
                reader = csv.DictReader(f, delimiter=';')
                # Normalize fieldnames
                field_map = {h.strip(): h.strip() for h in reader.fieldnames or []}
                # Keep only target columns that exist
                keep_cols = [c for c in TARGET_COLUMNS if c in field_map]
                
                # If we successfully read fieldnames, continue with this encoding
                print(f"Successfully opened file with encoding: {encoding}")
                break
        except (UnicodeDecodeError, UnicodeError) as e:
            last_error = e
            continue
    else:
        # If all encodings failed
        raise ValueError(f"Could not decode CSV file with any supported encoding. Last error: {last_error}")
    
    # Now process the file with the working encoding
    with csv_path.open('r', encoding=encoding, newline='') as f:
        reader = csv.DictReader(f, delimiter=';')
        field_map = {h.strip(): h.strip() for h in reader.fieldnames or []}
        keep_cols = [c for c in TARGET_COLUMNS if c in field_map]

        sanitized = [sanitize_column_name(c) for c in keep_cols]

        with sqlite3.connect(db_path) as conn:
            conn.execute('PRAGMA journal_mode = WAL;')
            conn.execute('PRAGMA synchronous = NORMAL;')
            create_table(conn, table, sanitized)
            create_indexes(conn, table, sanitized)

            total = 0
            batch = []
            for row in reader:
                filtered_row = [row.get(c, "") for c in keep_cols]
                batch.append(filtered_row)
                total += 1

                if len(batch) >= BATCH_SIZE:
                    insert_batch(conn, table, sanitized, batch)
                    conn.commit()
                    batch.clear()

            if batch:
                insert_batch(conn, table, sanitized, batch)
                conn.commit()

    return total, sanitized


def insert_batch(conn: sqlite3.Connection, table: str, columns: List[str], batch: List[List[str]]):
    if not batch:
        return
    placeholders = ", ".join(["?"] * len(columns))
    col_list = ", ".join([f'"{c}"' for c in columns])
    sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})'
    conn.executemany(sql, batch)


def main():
    parser = argparse.ArgumentParser(description='Import selected columns from CSV into SQLite.')
    parser.add_argument('--csv', type=Path, default=DEFAULT_CSV)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument('--table', type=str, default=DEFAULT_TABLE)
    args = parser.parse_args()

    if not args.csv.exists():
        raise FileNotFoundError(f"CSV file not found: {args.csv}")

    total, columns = import_csv_to_sqlite(args.csv, args.db, args.table)
    print(f"Imported {total} rows into '{args.db}' table '{args.table}'.")
    print(f"Columns ({len(columns)}): {', '.join(columns)}")


if __name__ == '__main__':
    main()
