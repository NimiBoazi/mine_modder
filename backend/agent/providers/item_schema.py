from __future__ import annotations

import os
from typing import Optional
from langchain_core.runnables import Runnable

# Same vendor/model setup as your example provider
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:  # pragma: no cover
    ChatGoogleGenerativeAI = None  # type: ignore

try:
    from ..wrappers.item_schema import make_item_schema_extractor
except Exception:  # pragma: no cover
    make_item_schema_extractor = None  # type: ignore


def build_item_schema_extractor() -> Optional[Runnable]:
    """Returns a Runnable that expects {'task', 'user_prompt'} and
    yields a dict containing at least {'item_id': str}. Raises on invalid output."""
    try:
        if ChatGoogleGenerativeAI is None or make_item_schema_extractor is None:
            return None
        if not os.getenv("GOOGLE_API_KEY"):
            return None

        model = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            temperature=0.2,
        )
        return make_item_schema_extractor(model)
    except Exception:
        return None
