# quick_check_store.py
import chromadb
from chromadb.config import Settings

PERSIST_DIR = "backend/rag/store/chroma_db_custom_model"
COLLECTION  = "minecraft_mods_custom_v1"

client = chromadb.PersistentClient(path=PERSIST_DIR)
print("Chroma version:", chromadb.__version__)
print("Collections:", [c.name for c in client.list_collections()])
col = client.get_collection(COLLECTION)
print("Count:", col.count())