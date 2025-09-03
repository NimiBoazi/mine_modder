# backend/tools/inspect_chroma_store.py
import os, glob, sqlite3

PERSIST_DIR = "backend/rag/store/chroma_db_custom_model"
print("Inspecting:", os.path.abspath(PERSIST_DIR))

cands = glob.glob(os.path.join(PERSIST_DIR, "*.sqlite3"))
print("DB files:", cands)

for db in cands:
    con = sqlite3.connect(db)
    cur = con.cursor()
    print("\n=>", db)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    print("tables:", tables)
    if "collections" in tables:
        cur.execute("PRAGMA table_info(collections)")
        print("collections columns:", [r[1] for r in cur.fetchall()])
    con.close()
