"""
Single entry point for retrieval: query_vector_store(store, query, filters)

Modes (auto-selected by env):
  - CUSTOM HTTP (preferred 1-URL): set RETRIEVE_URL to your FastAPI /retrieve endpoint
  - CHROMA HTTP:                  set CHROMA_HTTP_URL (e.g., "https://abcd.ngrok.app")
  - LOCAL FOLDER:                 set CHROMA_DB_ROOT (e.g., "/data/chroma_dbs")

Common:
  - COLLECTION_MAP: JSON or Python dict mapping store -> collection name (optional)
  - EMBED_URL + EMBED_SERVER_TOKEN: use your Colab embed server for query vectors
    (HF fallback disabled unless ALLOW_HF_FALLBACK=1)

Install:
  pip install -U langchain langchain-chroma chromadb sentence-transformers requests pydantic
"""

from __future__ import annotations
import os, json
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlsplit

# ---- LangChain doc/emb types (compatible import)
try:
    from langchain_core.documents import Document
    from langchain_core.embeddings import Embeddings
except Exception:  # pragma: no cover
    from langchain.schema import Document  # type: ignore
    class Embeddings:  # type: ignore
        pass

import chromadb
from chromadb.config import Settings
import requests

# Optional HF fallback (disabled by default)
try:
    from sentence_transformers import SentenceTransformer  # noqa: F401
    _HAS_ST = True
except Exception:  # pragma: no cover
    _HAS_ST = False

# ---------------------------
# Environment & configuration
# ---------------------------

CHROMA_HTTP_URL  = os.environ.get("CHROMA_HTTP_URL", "").strip()
CHROMA_DB_ROOT   = os.environ.get("CHROMA_DB_ROOT", "").rstrip("/")
RETRIEVE_URL     = os.environ.get("RETRIEVE_URL", "").rstrip("/")

# Optional: map logical store -> actual Chroma collection
_COLLECTION_MAP_ENV = os.environ.get("COLLECTION_MAP", "")
COLLECTION_MAP: Dict[str, str] = {}
if _COLLECTION_MAP_ENV:
    try:
        COLLECTION_MAP = json.loads(_COLLECTION_MAP_ENV)
    except json.JSONDecodeError:
        pass

# Embedding (remote server on Colab)
EMBED_URL   = os.environ.get("EMBED_URL", "").rstrip("/")
EMBED_TOKEN = os.environ.get("EMBED_SERVER_TOKEN", "")

# HF fallback (only if ALLOW_HF_FALLBACK=1)
ALLOW_HF_FALLBACK = os.environ.get("ALLOW_HF_FALLBACK", "0") == "1"
HF_REPO_ID   = os.environ.get("HF_REPO_ID", "Nimiii/nv-embedcode-7b-mine-modder-st")
HF_CACHE_DIR = os.environ.get("HF_CACHE_DIR", None)

# Chroma telemetry off
ANON_TELEMETRY = os.environ.get("ANONYMIZED_TELEMETRY", "FALSE")
os.environ["ANONYMIZED_TELEMETRY"] = ANON_TELEMETRY

TASK_INSTRUCTION = "Retrieve code or text based on user query"
QUERY_PREFIX = f"Instruct: {TASK_INSTRUCTION}\nQuery: "

# ---------------------------
# Embedding implementations
# ---------------------------

class ColabHTTPEmbeddings(Embeddings):
    """Embeddings via your Colab /embed server."""
    def __init__(self, embed_url: str, token: str, normalize: bool = True, timeout: int = 60):
        if not embed_url or not token:
            raise RuntimeError("ColabHTTPEmbeddings requires EMBED_URL and EMBED_SERVER_TOKEN")
        self.embed_url = embed_url.rstrip("/")
        self.token = token
        self.normalize = normalize
        self.timeout = timeout

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        r = requests.post(
            f"{self.embed_url}/embed",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"texts": texts, "normalize": self.normalize},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()["vectors"]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


class HFLocalEmbeddings(Embeddings):
    """Local SentenceTransformer fallback (opt-in)."""
    def __init__(self, repo_id: str, cache_dir: Optional[str] = None, normalize: bool = True):
        if not _HAS_ST:
            raise RuntimeError(
                "sentence-transformers not installed. "
                "Either install it or set EMBED_URL/EMBED_SERVER_TOKEN to use the Colab embed server."
            )
        from sentence_transformers import SentenceTransformer as _ST  # defer heavy import
        self.model = _ST(model_name_or_path=repo_id, cache_folder=cache_dir, trust_remote_code=True)
        self.normalize = normalize

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        vecs = self.model.encode(
            texts, convert_to_numpy=True, normalize_embeddings=self.normalize, show_progress_bar=False
        ).astype("float32").tolist()
        return vecs

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


def _get_embeddings() -> Embeddings:
    if EMBED_URL and EMBED_TOKEN:
        return ColabHTTPEmbeddings(EMBED_URL, EMBED_TOKEN, normalize=True)
    if ALLOW_HF_FALLBACK:
        return HFLocalEmbeddings(HF_REPO_ID, HF_CACHE_DIR, normalize=True)
    raise RuntimeError(
        "No EMBED_URL set and HF fallback disabled. "
        "Set EMBED_URL/EMBED_SERVER_TOKEN or export ALLOW_HF_FALLBACK=1 (downloads HF model)."
    )


# ---------------------------
# Filter grammar (neutral JSON)
# ---------------------------

FilterValue = Union[str, int, float, bool]
FilterDict  = Dict[str, Any]

_ALLOWED_OPS = {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin"}
_LOGIC_KEYS  = {"$and", "$or"}

def _is_logic_node(d: FilterDict) -> bool:
    return any(k in d for k in _LOGIC_KEYS)

def _validate_filter_expr(expr: Optional[FilterDict]) -> None:
    if expr is None:
        return
    if _is_logic_node(expr):
        for key in list(expr.keys()):
            if key not in _LOGIC_KEYS:
                raise ValueError(f"Unknown logic key: {key}")
            val = expr[key]
            if not isinstance(val, list) or not val:
                raise ValueError(f"{key} expects a non-empty list.")
            for child in val:
                _validate_filter_expr(child)
        return
    for field, cond in expr.items():
        if isinstance(cond, dict):
            for op, v in cond.items():
                if op not in _ALLOWED_OPS:
                    raise ValueError(f"Unsupported operator {op} for field {field}")
                if op in {"$in", "$nin"} and not isinstance(v, list):
                    raise ValueError(f"{op} expects a list for field {field}")
        # shorthand equality is fine

def _compile_filter_to_chroma_where(expr: Optional[FilterDict]) -> Optional[FilterDict]:
    if expr is None:
        return None
    if _is_logic_node(expr):
        out: Dict[str, Any] = {}
        for key in _LOGIC_KEYS:
            if key in expr:
                out[key] = [_compile_filter_to_chroma_where(child) for child in expr[key]]
        return out
    compiled: Dict[str, Any] = {}
    for field, cond in expr.items():
        if isinstance(cond, dict):
            compiled[field] = cond
        else:
            compiled[field] = {"$eq": cond}
    return compiled


# ---------------------------
# Similarity conversion (L2 -> 0..1)
# ---------------------------

def _l2_distance_to_similarity01(d: Optional[float]) -> Optional[float]:
    """Convert L2 distance between unit vectors to cosine similarity in [0,1]."""
    if d is None:
        return None
    d = float(d)
    cos = 1.0 - (d * d) / 2.0  # cos in [-1,1]
    if cos < -1.0: cos = -1.0
    if cos > 1.0:  cos = 1.0
    return (cos + 1.0) / 2.0

# ---------------------------
# Prefix Formatter
# ---------------------------

def format_query(raw_query: str) -> str:
    """Prepend the task instruction prefix to a single query string."""
    # Safety check to avoid double-prefixing
    if raw_query.startswith("Instruct: "):
        return raw_query
    return f"{QUERY_PREFIX}{raw_query}"

# ---------------------------
# Core entry point
# ---------------------------

def query_vector_store(
    store: str,
    query: str,
    *,
    top_k: int = 8,
    filters: Optional[FilterDict] = None,
    where_document: Optional[FilterDict] = None,
    include: Optional[List[str]] = None,
    expand_pages_from_top_k: bool = False,
    similarity_threshold: Optional[float] = None,
) -> List[Document]:
    """
    Retrieve Documents for `query` from `store`.

    Returns `Document` objects where:
      - top-k items have metadata["_similarity"] in [0,1]
      - page-expansion items (same source_file) get metadata["_similarity"] = None

    Args:
        expand_pages_from_top_k:
            If True, after thresholding, take first N = min(top_k, len(kept_topk))
            and append ALL docs whose metadata["source_file"] matches any of those N.
            Threshold does NOT apply to these appended docs.

        similarity_threshold:
            If provided (0..1), only top-k items with similarity >= threshold are kept.
    """
    if not store:
        raise ValueError("store is required")
    if not query:
        raise ValueError("query is required")
    
    formatted_query = format_query(query)

    include = include or ["documents", "metadatas", "distances"]

    _validate_filter_expr(filters)
    where = _compile_filter_to_chroma_where(filters)
    if where_document is not None and not isinstance(where_document, dict):
        raise ValueError("where_document must be a dict or None")

    # Prefer single-URL custom server when present (no local embedder)
    if RETRIEVE_URL:
        return _query_via_custom_http(
            store=store,
            query=formatted_query,
            top_k=top_k,
            where=where,
            where_document=where_document,
            include=include,
            expand_pages_from_top_k=expand_pages_from_top_k,
            similarity_threshold=similarity_threshold,
        )

    # Otherwise, use direct Chroma modes which need an embedder
    emb = _get_embeddings()

    if CHROMA_HTTP_URL:
        return _query_via_chroma_direct(
            mode="http",
            store=store,
            query=formatted_query,
            top_k=top_k,
            emb=emb,
            where=where,
            where_document=where_document,
            include=include,
            expand_pages_from_top_k=expand_pages_from_top_k,
            similarity_threshold=similarity_threshold,
        )

    if CHROMA_DB_ROOT:
        return _query_via_chroma_direct(
            mode="local",
            store=store,
            query=formatted_query,
            top_k=top_k,
            emb=emb,
            where=where,
            where_document=where_document,
            include=include,
            expand_pages_from_top_k=expand_pages_from_top_k,
            similarity_threshold=similarity_threshold,
        )

    raise RuntimeError("No retrieval mode configured. Set RETRIEVE_URL or CHROMA_HTTP_URL or CHROMA_DB_ROOT.")


# ---------------------------
# Option C: Custom HTTP (/retrieve) — single URL server
# ---------------------------

def _query_via_custom_http(
    *,
    store: str,
    query: str,
    top_k: int,
    where: Optional[FilterDict],
    where_document: Optional[FilterDict],
    include: List[str],
    expand_pages_from_top_k: bool,
    similarity_threshold: Optional[float],
) -> List[Document]:
    headers = {}
    token = os.environ.get("EMBED_SERVER_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = {
        "query": query,
        "top_k": top_k,
        "include": include,
        "normalize": True,  # server encodes with normalized vectors (cosine semantics)
        "filters": where,
        "where_document": where_document,
        "expand_pages_from_top_k": bool(expand_pages_from_top_k),
        "similarity_threshold": similarity_threshold,
        "store": store,  # server may map store -> collection
    }
    r = requests.post(f"{RETRIEVE_URL}/retrieve", headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()

    # Server returns: hits[], applied_top_k, include, stats
    hits = data.get("hits", [])
    applied_top_k = int(data.get("applied_top_k", len(hits)))

    docs: List[Document] = []
    for i, h in enumerate(hits):
        md = (h.get("metadata") or {}).copy()
        # Prefer server-provided similarity if available, otherwise convert L2
        sim01 = h.get("similarity")
        if sim01 is None:
            sim01 = _l2_distance_to_similarity01(h.get("distance"))

        # Top-k band (first applied_top_k) carries similarity; expansion docs get None
        if i < applied_top_k:
            md["_similarity"] = sim01
        else:
            md["_similarity"] = None  # page-expansion docs

        # ensure id presence
        if "id" not in md and h.get("id"):
            md["id"] = h["id"]

        # Drop any raw distance—API exposes similarity only
        if "_distance" in md:
            md.pop("_distance", None)

        docs.append(Document(page_content=h.get("document") or "", metadata=md))

    return docs


# ---------------------------
# Options A/B: Direct Chroma (HTTP or Local)
# ---------------------------

def _query_via_chroma_direct(
    *,
    mode: str,  # "http" or "local"
    store: str,
    query: str,
    top_k: int,
    emb: Embeddings,
    where: Optional[FilterDict],
    where_document: Optional[FilterDict],
    include: List[str],
    expand_pages_from_top_k: bool,
    similarity_threshold: Optional[float],
) -> List[Document]:
    collection_name = COLLECTION_MAP.get(store, store)

    # Build Chroma client
    if mode == "http":
        headers = {}
        token = os.environ.get("CHROMA_HTTP_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        u = urlsplit(CHROMA_HTTP_URL)
        host = u.hostname or CHROMA_HTTP_URL.replace("https://", "").replace("http://", "")
        port = u.port or (443 if u.scheme == "https" else 80)
        ssl = (u.scheme == "https")
        client = chromadb.HttpClient(
            host=host,
            port=port,
            ssl=ssl,
            headers=headers or None,
            settings=Settings(anonymized_telemetry=False),
        )
    else:
        # Local folder is the DB root, not per-collection subdir
        client = chromadb.PersistentClient(path=CHROMA_DB_ROOT, settings=Settings(anonymized_telemetry=False))

    collection = client.get_collection(collection_name)

    # Embed query once
    qvec = emb.embed_query(query)

    # Low-level query to capture ids and distances deterministically
    res = collection.query(
        query_embeddings=[qvec],
        n_results=top_k,
        where=where,
        where_document=where_document,
        include=list(set(include) | {"ids", "documents", "metadatas", "distances"}),
    )

    ids         = res.get("ids", [[]])[0]
    dists       = res.get("distances", [[]])[0]
    docs_raw    = res.get("documents", [[]])[0]
    metas_raw   = res.get("metadatas", [[]])[0]

    # Build the primary top-k with similarity and threshold
    top_results: List[Document] = []
    for i, _id in enumerate(ids):
        meta = dict(metas_raw[i] or {})
        sim01 = _l2_distance_to_similarity01(dists[i])
        meta["_similarity"] = sim01
        if "id" not in meta:
            meta["id"] = _id

        if (similarity_threshold is None) or (sim01 is not None and sim01 >= similarity_threshold):
            top_results.append(Document(page_content=docs_raw[i] or "", metadata=meta))

    # Optional: expand by source_file using the first N kept results (N=min(top_k, len(kept)))
    results: List[Document] = list(top_results)
    if expand_pages_from_top_k and top_results:
        n = min(top_k, len(top_results))
        seeds = top_results[:n]
        srcs = list({d.metadata.get("source_file") for d in seeds if d.metadata.get("source_file")})
        if srcs:
            exp_where = {"source_file": {"$in": srcs}}
            if where:
                exp_where = {"$and": [where, exp_where]}

            page_res = collection.get(
                where=exp_where,
                include=["ids", "documents", "metadatas"],
            )
            page_ids   = page_res.get("ids", [])
            page_docs  = page_res.get("documents", [])
            page_metas = page_res.get("metadatas", [])

            # Dedup against existing by 'id'
            seen_ids = {d.metadata.get("id") for d in results if d.metadata.get("id")}
            for i, pid in enumerate(page_ids):
                if pid in seen_ids:
                    continue
                pmeta = dict(page_metas[i] or {})
                pmeta["id"] = pid
                pmeta["_similarity"] = None  # expansion docs bypass threshold & score
                pmeta["_expanded_from_source_file"] = pmeta.get("source_file")
                results.append(Document(page_content=page_docs[i] or "", metadata=pmeta))

    return results
