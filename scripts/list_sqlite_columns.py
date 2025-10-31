#!/usr/bin/env python3
"""List column headers for all tables in a SQLite database.

Usage examples:
  python scripts\list_sqlite_columns.py data\app.db
  python scripts\list_sqlite_columns.py data\app.db --format json --output cols.json
  python scripts\list_sqlite_columns.py data\app.db --table users -v

This script prints a mapping of table -> list of column names by default.
In verbose mode it prints full PRAGMA table_info rows for each column.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from typing import Dict, List, Any


def quote_ident(name: str) -> str:
    """Safely quote an identifier for SQLite PRAGMA use by doubling internal quotes.

    Note: This is intentionally simple — it quotes the name with double quotes and
    escapes any existing double quotes by doubling them. It avoids SQL injection
    for typical table names. If you have unusual names, handle accordingly.
    """
    return '"' + name.replace('"', '""') + '"'


def get_tables(conn: sqlite3.Connection) -> List[str]:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    return [row[0] for row in cur.fetchall()]


def get_columns(conn: sqlite3.Connection, table: str, verbose: bool = False) -> List[Any]:
    safe = quote_ident(table)
    cur = conn.execute(f"PRAGMA table_info({safe});")
    rows = cur.fetchall()
    if verbose:
        # Return list of dicts with full PRAGMA info
        cols = []
        for r in rows:
            # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
            cols.append({
                "cid": r[0],
                "name": r[1],
                "type": r[2],
                "notnull": bool(r[3]),
                "default_value": r[4],
                "pk": bool(r[5]),
            })
        return cols
    # default: just return column names
    return [r[1] for r in rows]


def main(argv: List[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description="List column headers for each table in a SQLite database.")
    parser.add_argument("db", help="Path to the SQLite database file")
    parser.add_argument("--table", "-t", help="Only list columns for this table (name)")
    parser.add_argument("--format", "-f", choices=("text", "json"), default="text", help="Output format")
    parser.add_argument("--output", "-o", help="Write output to a file instead of stdout")
    parser.add_argument("--verbose", "-v", action="store_true", help="Include full PRAGMA table_info output for each column")

    args = parser.parse_args(argv)

    db_path = os.path.expanduser(args.db)
    if not os.path.exists(db_path):
        print(f"Error: database file not found: {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(db_path)
    try:
        tables = get_tables(conn)
        if args.table:
            if args.table not in tables:
                print(f"Error: table '{args.table}' not found in database.", file=sys.stderr)
                return 3
            tables = [args.table]

        result: Dict[str, Any] = {}
        for t in tables:
            result[t] = get_columns(conn, t, verbose=args.verbose)

        if args.format == "json":
            out = json.dumps(result, indent=2)
        else:
            # plain text: table: col1, col2
            lines = []
            for t, cols in result.items():
                if args.verbose:
                    lines.append(f"{t}: \n  " + "\n  ".join(json.dumps(c) for c in cols))
                else:
                    lines.append(f"{t}: {', '.join(cols)}")
            out = "\n".join(lines)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(out)
        else:
            print(out)

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
