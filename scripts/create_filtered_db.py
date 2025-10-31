import sqlite3

# Source and destination DB paths
SRC_DB = "data/1-training_data.db"
DST_DB = "data/1-training_data_prod.db"

# Columns to keep
COLUMNS = [
    "Action", "Hour_of_Day", "Minutes_of_Hour_of_Day", "Win", "Profit", "Profit_Pct", "Outcome"
]

# Connect to source DB
src_conn = sqlite3.connect(SRC_DB)
src_cur = src_conn.cursor()

# Get table name (assume only one table)
src_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
table_name = src_cur.fetchone()[0]

# Build SELECT statement
select_sql = f"SELECT {', '.join(COLUMNS)} FROM {table_name}"
src_cur.execute(select_sql)
rows = src_cur.fetchall()

# Create new DB and table
# Get column types from source table
src_cur.execute(f"PRAGMA table_info({table_name})")
col_info = {row[1]: row[2] for row in src_cur.fetchall() if row[1] in COLUMNS}

col_defs = ', '.join([f'{col} {col_info[col]}' for col in COLUMNS])
create_sql = f"CREATE TABLE {table_name} ({col_defs})"

dst_conn = sqlite3.connect(DST_DB)
dst_cur = dst_conn.cursor()
dst_cur.execute(f"DROP TABLE IF EXISTS {table_name}")
dst_cur.execute(create_sql)

# Insert rows
placeholders = ', '.join(['?'] * len(COLUMNS))
insert_sql = f"INSERT INTO {table_name} ({', '.join(COLUMNS)}) VALUES ({placeholders})"
dst_cur.executemany(insert_sql, rows)
dst_conn.commit()

src_conn.close()
dst_conn.close()
print(f"Filtered DB created: {DST_DB}")
