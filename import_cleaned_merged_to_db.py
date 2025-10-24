import argparse
import csv
import os
import re
import sqlite3
from pathlib import Path
from typing import List, Tuple

# --- Configuration defaults ---
DEFAULT_DB_PATH = Path('data') / 'imported_data.db'
DEFAULT_TABLE = 'trades_dataset'
DEFAULT_CSV = Path('cleaned_merged.csv')
BATCH_SIZE = 1000


def sanitize_column_name(name: str) -> str:
    """Make a safe SQLite column name: letters, numbers, underscores; not starting with number."""
    # Replace non-alnum with underscore
    col = re.sub(r"[^0-9a-zA-Z_]", "_", name.strip())
    # Avoid leading digits
    if re.match(r"^[0-9]", col):
        col = f"c_{col}"
    # Avoid empty
    if not col:
        col = "col"
    return col


def unique_column_names(names: List[str]) -> List[str]:
    seen = {}
    result = []
    for n in names:
        base = sanitize_column_name(n)
        c = base
        i = 1
        while c.lower() in seen:
            i += 1
            c = f"{base}_{i}"
        seen[c.lower()] = True
        result.append(c)
    return result


def ensure_db_dir(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)


def create_table(conn: sqlite3.Connection, table: str, columns: List[str]) -> None:
    # Use TEXT for maximum compatibility; SQLite is dynamic typing and will accept numeric text
    cols_def = ", ".join([f'"{c}" TEXT' for c in columns])
    sql = f'CREATE TABLE IF NOT EXISTS "{table}" ({cols_def});'
    conn.execute(sql)
    conn.commit()


def create_indexes(conn: sqlite3.Connection, table: str, columns: List[str]) -> None:
    # Add helpful indexes if present
    index_cols = []
    for target in ("Time", "Symbol", "Action"):
        # Find sanitized matching column (case-insensitive)
        match = next((c for c in columns if c.lower() == sanitize_column_name(target).lower()), None)
        if match:
            index_cols.append(match)
            conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{table}_{match} ON "{table}"("{match}");')
    if index_cols:
        conn.commit()


def read_header(csv_path: Path) -> List[str]:
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f, delimiter=';')
        header = next(reader, None)
        if not header:
            raise ValueError('CSV has no header row')
        return header


def iter_rows(csv_path: Path, expected_len: int):
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f, delimiter=';')
        # Skip header
        next(reader, None)
        for row in reader:
            if len(row) < expected_len:
                # Pad with empty strings if short
                row = row + [""] * (expected_len - len(row))
            elif len(row) > expected_len:
                # Truncate if long
                row = row[:expected_len]
            yield row


def insert_batch(conn: sqlite3.Connection, table: str, columns: List[str], batch: List[List[str]]):
    if not batch:
        return
    placeholders = ", ".join(["?"] * len(columns))
    col_list = ", ".join([f'"{c}"' for c in columns])
    sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})'
    conn.executemany(sql, batch)


def import_csv_to_sqlite(csv_path: Path, db_path: Path, table: str) -> Tuple[int, List[str]]:
    ensure_db_dir(db_path)
    header = read_header(csv_path)
    sanitized = unique_column_names(header)

    with sqlite3.connect(db_path) as conn:
        conn.execute('PRAGMA foreign_keys = OFF;')
        conn.execute('PRAGMA journal_mode = WAL;')
        conn.execute('PRAGMA synchronous = NORMAL;')
        create_table(conn, table, sanitized)
        create_indexes(conn, table, sanitized)

        total = 0
        batch: List[List[str]] = []
        try:
            for row in iter_rows(csv_path, len(sanitized)):
                batch.append(row)
                total += 1
                if len(batch) >= BATCH_SIZE:
                    insert_batch(conn, table, sanitized, batch)
                    conn.commit()
                    batch.clear()
            # Final batch
            if batch:
                insert_batch(conn, table, sanitized, batch)
                conn.commit()
        except Exception as e:
            # On any error, raise with context
            raise RuntimeError(f"Failed at row {total+1}: {e}") from e

        return total, sanitized


def main():
    parser = argparse.ArgumentParser(description='Import a semicolon-delimited CSV into a new SQLite database table.')
    parser.add_argument('--csv', type=Path, default=DEFAULT_CSV, help='Path to cleaned_merged.csv (semicolon-delimited)')
    parser.add_argument('--db', type=Path, default=DEFAULT_DB_PATH, help='Path to SQLite DB to create/use')
    parser.add_argument('--table', type=str, default=DEFAULT_TABLE, help='Table name to create/populate')
    args = parser.parse_args()

    csv_path: Path = args.csv
    db_path: Path = args.db
    table: str = args.table

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    total, columns = import_csv_to_sqlite(csv_path, db_path, table)

    print(f"Imported {total} rows into '{db_path}' table '{table}'.")
    print(f"Columns ({len(columns)}): {', '.join(columns)}")


if __name__ == '__main__':
    main()
