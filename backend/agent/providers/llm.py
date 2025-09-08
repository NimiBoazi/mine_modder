from __future__ import annotations

import os
from typing import Optional
from langchain_core.runnables import Runnable

# Vendor and wrappers are isolated here (provider), not inside nodes.
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:  # pragma: no cover - optional dependency, handled at runtime
    ChatGoogleGenerativeAI = None  # type: ignore

try:
    from ..wrappers.llm import make_name_desc_extractor
except Exception:  # pragma: no cover
    make_name_desc_extractor = None  # type: ignore


def build_name_desc_extractor() -> Optional[Runnable]:
    """Build and return a LangChain Runnable for inferring name/description.
    Returns None if the provider is unavailable or misconfigured.
    """
    try:
        if ChatGoogleGenerativeAI is None or make_name_desc_extractor is None:
            return None
        if not os.getenv("GOOGLE_API_KEY"):
            return None
        model = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.2)
        return make_name_desc_extractor(model)
    except Exception:
        return None

