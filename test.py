import sqlite3
import os
import argparse

# Columns you want to export
SELECTED_COLUMNS = [
    "Trade_Time",
    "Symbol",
    "Action",
    "Hour_of_Day",
    "Is_NY_Session",
    "Is_Asian_Session",
    "Is_London_Session",
    "Breakout_Strength",
    "Win",
    "Profit",
    "Profit_Pct",
    "Outcome",
]

def ensure_db_dir(db_path: str):
    """Create folder for database if it doesn’t exist."""
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

def build_create_sql(table_name: str) -> str:
    """Generate SQL for creating the export table."""
    columns_def = []
    for col in SELECTED_COLUMNS:
        if col.startswith("Is_"):
            col_type = "INTEGER"
        elif col in ["Hour_of_Day"]:
            col_type = "REAL"
        elif col in ["Action"]:
            col_type = "TEXT"
        else:
            col_type = "REAL"
        columns_def.append(f'"{col}" {col_type}')
    columns_def.insert(0, "id INTEGER PRIMARY KEY AUTOINCREMENT")
    return f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns_def)});"

def export_data(source_db: str, dest_db: str, source_table: str, dest_table: str):
    """Copy selected columns from source database to new database."""
    ensure_db_dir(dest_db)

    src_conn = sqlite3.connect(source_db)
    dst_conn = sqlite3.connect(dest_db)

    try:
        # Check if all columns exist in the source table
        cursor = src_conn.execute(f"PRAGMA table_info({source_table});")
        available_cols = [row[1] for row in cursor.fetchall()]
        missing = [col for col in SELECTED_COLUMNS if col not in available_cols]
        if missing:
            raise ValueError(f"Missing columns in source table: {missing}")

        # Create destination table
        dst_conn.execute(build_create_sql(dest_table))
        dst_conn.commit()

        # Export data
        col_str = ", ".join(SELECTED_COLUMNS)
        src_cursor = src_conn.execute(f"SELECT {col_str} FROM {source_table};")
        rows = src_cursor.fetchall()

        placeholders = ", ".join(["?"] * len(SELECTED_COLUMNS))
        insert_sql = f"INSERT INTO {dest_table} ({col_str}) VALUES ({placeholders});"
        dst_conn.executemany(insert_sql, rows)
        dst_conn.commit()

        print(f"✅ Exported {len(rows)} rows from '{source_db}::{source_table}' to '{dest_db}::{dest_table}'")

    finally:
        src_conn.close()
        dst_conn.close()

def main():
    parser = argparse.ArgumentParser(description="Export selected columns from one SQLite DB to another.")
    parser.add_argument("--source-db", default="data/training_data.db", help="Path to source SQLite database.")
    parser.add_argument("--source-table", default="clean_trades", help="Table name in source DB.")
    parser.add_argument("--dest-db", default="data/feature_subset.db", help="Path for new database.")
    parser.add_argument("--dest-table", default="feature_data", help="Table name in new DB.")
    args = parser.parse_args()

    export_data(args.source_db, args.dest_db, args.source_table, args.dest_table)

if __name__ == "__main__":
    main()
