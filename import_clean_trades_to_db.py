import argparse
import csv
import os
import sqlite3
from typing import List, Dict, Any, Tuple

# Headers matching the new MQ5 collector schema (order matters)
# Updated schema: focuses on candlestick patterns before breakout
HEADERS: List[str] = [
    # TRADE IDENTIFICATION
    "Trade_Time",
    "Symbol",
    "Action",

    # TRADE EXECUTION
    "Entry",
    "Exit_Price",
    "SL",
    "TP",

    # BREAKOUT QUALITY
    "Breakout_Strength",

    # BREAKOUT TIME & SESSION
    "Hour_of_Day",
    "Day_of_Week",
    "Is_London_Session",
    "Is_NY_Session",
    "Is_Asian_Session",

    # 7 H1 CANDLES BEFORE BREAKOUT (C1=most recent, C7=oldest)
    # Candle 1
    "C1_Open", "C1_High", "C1_Low", "C1_Close", "C1_BodyPts", "C1_UpperWickPts", "C1_LowerWickPts",
    # Candle 2
    "C2_Open", "C2_High", "C2_Low", "C2_Close", "C2_BodyPts", "C2_UpperWickPts", "C2_LowerWickPts",
    # Candle 3
    "C3_Open", "C3_High", "C3_Low", "C3_Close", "C3_BodyPts", "C3_UpperWickPts", "C3_LowerWickPts",
    # Candle 4
    "C4_Open", "C4_High", "C4_Low", "C4_Close", "C4_BodyPts", "C4_UpperWickPts", "C4_LowerWickPts",
    # Candle 5
    "C5_Open", "C5_High", "C5_Low", "C5_Close", "C5_BodyPts", "C5_UpperWickPts", "C5_LowerWickPts",
    # Candle 6
    "C6_Open", "C6_High", "C6_Low", "C6_Close", "C6_BodyPts", "C6_UpperWickPts", "C6_LowerWickPts",
    # Candle 7
    "C7_Open", "C7_High", "C7_Low", "C7_Close", "C7_BodyPts", "C7_UpperWickPts", "C7_LowerWickPts",

    # OUTCOMES
    "Win",
    "Profit",
    "Profit_Pct",
    "Outcome",
]

# SQLite type mapping for each column
# TEXT for categorical/time, INTEGER for flags and counts, REAL for numeric metrics
TYPE_MAP: Dict[str, str] = {
    # identification
    "Trade_Time": "TEXT",
    "Symbol": "TEXT",
    "Action": "TEXT",

    # execution
    "Entry": "REAL",
    "Exit_Price": "REAL",
    "SL": "REAL",
    "TP": "REAL",

    # breakout quality
    "Breakout_Strength": "REAL",

    # time & session
    "Hour_of_Day": "INTEGER",
    "Day_of_Week": "INTEGER",
    "Is_London_Session": "INTEGER",
    "Is_NY_Session": "INTEGER",
    "Is_Asian_Session": "INTEGER",

    # 7 candles before breakout (OHLC = REAL, body/wicks = INTEGER points)
    "C1_Open": "REAL", "C1_High": "REAL", "C1_Low": "REAL", "C1_Close": "REAL",
    "C1_BodyPts": "INTEGER", "C1_UpperWickPts": "INTEGER", "C1_LowerWickPts": "INTEGER",

    "C2_Open": "REAL", "C2_High": "REAL", "C2_Low": "REAL", "C2_Close": "REAL",
    "C2_BodyPts": "INTEGER", "C2_UpperWickPts": "INTEGER", "C2_LowerWickPts": "INTEGER",

    "C3_Open": "REAL", "C3_High": "REAL", "C3_Low": "REAL", "C3_Close": "REAL",
    "C3_BodyPts": "INTEGER", "C3_UpperWickPts": "INTEGER", "C3_LowerWickPts": "INTEGER",

    "C4_Open": "REAL", "C4_High": "REAL", "C4_Low": "REAL", "C4_Close": "REAL",
    "C4_BodyPts": "INTEGER", "C4_UpperWickPts": "INTEGER", "C4_LowerWickPts": "INTEGER",

    "C5_Open": "REAL", "C5_High": "REAL", "C5_Low": "REAL", "C5_Close": "REAL",
    "C5_BodyPts": "INTEGER", "C5_UpperWickPts": "INTEGER", "C5_LowerWickPts": "INTEGER",

    "C6_Open": "REAL", "C6_High": "REAL", "C6_Low": "REAL", "C6_Close": "REAL",
    "C6_BodyPts": "INTEGER", "C6_UpperWickPts": "INTEGER", "C6_LowerWickPts": "INTEGER",

    "C7_Open": "REAL", "C7_High": "REAL", "C7_Low": "REAL", "C7_Close": "REAL",
    "C7_BodyPts": "INTEGER", "C7_UpperWickPts": "INTEGER", "C7_LowerWickPts": "INTEGER",

    # outcomes
    "Win": "INTEGER",
    "Profit": "REAL",
    "Profit_Pct": "REAL",
    "Outcome": "TEXT",
}

assert set(HEADERS) == set(TYPE_MAP.keys()), "TYPE_MAP must cover all headers"


def ensure_db_dir(db_path: str) -> None:
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)


def build_create_table_sql(table: str) -> str:
    cols = [f'"{col}" {TYPE_MAP[col]}' for col in HEADERS]
    # optional primary key
    cols_sql = ["id INTEGER PRIMARY KEY AUTOINCREMENT"] + cols
    return f"CREATE TABLE IF NOT EXISTS \"{table}\" (" + ", ".join(cols_sql) + ");"


def maybe_strip_bom(path: str) -> None:
    # If file has UTF-8 BOM, it can break first header field. We'll strip it in-place cheaply.
    try:
        with open(path, 'rb') as f:
            data = f.read(3)
            rest = f.read()
        if data == b'\xef\xbb\xbf':
            with open(path, 'wb') as f:
                f.write(rest)
    except Exception:
        pass


def detect_has_header(sample_line: str) -> bool:
    # Detect if the sample line looks like the header row
    parts = [p.strip() for p in sample_line.rstrip("\n\r").split(";")]
    return parts == HEADERS


def cast_value(col: str, val: str) -> Any:
    if val is None:
        return None
    s = val.strip()
    if s == "" or s.lower() == "nan":
        return None

    t = TYPE_MAP[col]
    try:
        if t == "INTEGER":
            # Some CSVs may contain float-looking ints like "1.0"; handle safely
            if "." in s:
                return int(float(s))
            return int(s)
        elif t == "REAL":
            # Replace commas in locales like "1,234.56" just in case
            return float(s.replace(",", ""))
        else:
            return s
    except ValueError:
        # Fallback to None if casting fails
        return None


def parse_csv_rows(csv_path: str, encoding: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    # Only attempt to strip UTF-8 BOM if reading as UTF-8
    if encoding.lower().startswith("utf-8"):
        maybe_strip_bom(csv_path)

    with open(csv_path, mode="r", newline="", encoding=encoding) as f:
        # Peek first line to detect header presence
        pos = f.tell()
        first_line = f.readline()
        if not first_line:
            return rows
        has_header = detect_has_header(first_line)
        f.seek(pos)

        if has_header:
            reader = csv.DictReader(f, delimiter=';')
        else:
            reader = csv.DictReader(f, fieldnames=HEADERS, delimiter=';')

        for rec in reader:
            # If there was a header row, DictReader already skipped it
            casted = {col: cast_value(col, rec.get(col)) for col in HEADERS}
            rows.append(casted)

    return rows


def insert_rows(conn: sqlite3.Connection, table: str, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0

    placeholders = ",".join(["?"] * len(HEADERS))
    sql = f"INSERT INTO \"{table}\" (" + ",".join([f'"{c}"' for c in HEADERS]) + f") VALUES ({placeholders});"

    values: List[Tuple[Any, ...]] = [tuple(row[col] for col in HEADERS) for row in rows]

    with conn:
        conn.executemany(sql, values)

    return len(values)


def main():
    parser = argparse.ArgumentParser(description="Import clean trades CSV into SQLite database.")
    parser.add_argument("--csv", dest="csv_path", default="clean_trades.csv", help="Path to input CSV (semicolon-delimited)")
    parser.add_argument("--db", dest="db_path", default=os.path.join("data", "training_data.db"), help="Path to SQLite database file")
    parser.add_argument("--table", dest="table", default="clean_trades", help="Destination table name")
    parser.add_argument("--encoding", dest="encoding", default="utf-16", help="File text encoding (e.g., utf-16, utf-8, utf-8-sig)")
    args = parser.parse_args()

    if not os.path.exists(args.csv_path):
        raise SystemExit(f"Input CSV not found: {args.csv_path}")

    ensure_db_dir(args.db_path)

    # Read CSV
    try:
        rows = parse_csv_rows(args.csv_path, args.encoding)
    except UnicodeDecodeError as e:
        # Helpful guidance if encoding is wrong
        raise SystemExit(f"Failed to decode file with encoding '{args.encoding}': {e}. Try --encoding utf-16 or utf-8-sig.")
    print(f"Loaded {len(rows):,} rows from {args.csv_path} using encoding {args.encoding}")

    # Create table and insert
    conn = sqlite3.connect(args.db_path)
    try:
        create_sql = build_create_table_sql(args.table)
        with conn:
            conn.execute(create_sql)
        inserted = insert_rows(conn, args.table, rows)
        print(f"Inserted {inserted:,} rows into {args.db_path}::{args.table}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
