# backend/tests/query_test.py
from __future__ import annotations
import os, json
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

# Load .env (repo root or backend/.env)
env = find_dotenv() or (Path(__file__).resolve().parents[1] / ".env")
load_dotenv(env)

from backend.rag.retrieval.query_vector_store import query_vector_store

# Config (env-driven)
STORE = os.getenv("STORE_NAME", "minecraft_mods_custom_v1")
QUERY = os.getenv("TEST_QUERY", "Change the hardness of a block")
TOP_K = int(os.getenv("TOP_K", "1"))
OUT_PATH = Path(os.getenv("OUTPUT_FILE", "") or (Path(__file__).resolve().parent / "query_results.txt"))

# Detect mode (for header only)
mode = (
    "CHROMA_HTTP_URL" if os.getenv("CHROMA_HTTP_URL")
    else "CHROMA_DB_ROOT" if os.getenv("CHROMA_DB_ROOT")
    else "RETRIEVE_URL" if os.getenv("RETRIEVE_URL")
    else "UNCONFIGURED"
)

docs = query_vector_store(
    store=STORE,
    query=QUERY,
    top_k=TOP_K,
    expand_pages_from_top_k=True,
    filters={
        "heading_path": {
            "$nin": [
                "Tags list, block",
                "Tags list, item",
                "Tags List - Forge Documentation"
            ]
        }
    }
)

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with OUT_PATH.open("w", encoding="utf-8") as f:
    f.write(f"# STORE={STORE}\n# MODE={mode}\n# QUERY={QUERY}\n# TOP_K={TOP_K}\n\n")
    if not docs:
        f.write("No results.\n")
    else:
        for i, d in enumerate(docs, 1):
            md = dict(d.metadata or {})
            distance = md.pop("_similarity", None)  # attached by the pipeline when available
            f.write(f"{i}. similarity={distance}\n")

            # Pretty-print ALL metadata
            f.write("METADATA:\n")
            f.write(json.dumps(md, ensure_ascii=False, indent=2))
            f.write("\n")

            # Full content (no truncation)
            content = (d.page_content or "")
            f.write("CONTENT:\n")
            f.write(content)
            f.write("\n" + "-" * 80 + "\n")

print(f"✅ Full results written to {OUT_PATH}")
