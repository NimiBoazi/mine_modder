from __future__ import annotations

from typing import Optional
from langchain_core.runnables import Runnable

from backend.agent.providers.gpt5_provider import build_gpt5_chat_model

try:
    from ..wrappers.item_schema import make_item_schema_extractor
except Exception:  # pragma: no cover
    make_item_schema_extractor = None  # type: ignore


def build_item_schema_extractor() -> Optional[Runnable]:
    """Returns a Runnable that expects {'task', 'user_prompt'} and
    yields a dict containing at least {'item_id': str}. Raises on invalid output."""
    try:
        if make_item_schema_extractor is None:
            return None
        model = build_gpt5_chat_model()
        if model is None:
            return None
        return make_item_schema_extractor(model)
    except Exception:
        return None
