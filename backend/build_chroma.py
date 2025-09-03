import os, glob, sqlite3

PERSIST_DIR = "backend/rag/store/chroma_db_custom_model"  # adjust if needed

def add_column_if_missing(conn, table, col, ddl_type="TEXT"):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in cur.fetchall()}
    if table not in tables:
        print(f"   (no '{table}' table)")
        return
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    print(f"   {table} columns: {cols}")
    if col not in cols:
        print(f"   ➕ Adding column {table}.{col}")
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl_type};")
        conn.commit()

dbs = glob.glob(os.path.join(PERSIST_DIR, "*.sqlite3"))
if not dbs:
    raise SystemExit(f"No .sqlite3 file found in {PERSIST_DIR}")

for db in dbs:
    print(f"🔧 Checking {db}")
    conn = sqlite3.connect(db)
    try:
        add_column_if_missing(conn, "collections", "topic", "TEXT")
        add_column_if_missing(conn, "segments",    "topic", "TEXT")
    finally:
        conn.close()

print("✅ Repair complete. Try your query again.")
