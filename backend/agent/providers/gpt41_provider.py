from __future__ import annotations

import os
from typing import Optional

try:
    from langchain_openai import ChatOpenAI  # type: ignore
except Exception:  # pragma: no cover
    ChatOpenAI = None  # type: ignore


def build_gpt41_chat_model() -> Optional["ChatOpenAI"]:
    """Return a configured GPT-4.1 chat model instance, or None if unavailable.

    Kept separate so nodes/wrappers can depend on a clean provider and we can
    swap models without touching node logic.
    """
    try:
        if ChatOpenAI is None:
            return None
        if not os.getenv("OPENAI_API_KEY"):
            return None
        # Use a stable, general-purpose GPT-4.1.
        return ChatOpenAI(model="gpt-4.1")
    except Exception:
        return None

