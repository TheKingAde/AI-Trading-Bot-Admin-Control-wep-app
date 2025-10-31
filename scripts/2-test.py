import sqlite3

db_path = r"data\2-training_data.db"  # Change path as needed

with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()
    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"{table}: {', '.join(columns)}")