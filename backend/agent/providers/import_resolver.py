from __future__ import annotations

from typing import Optional
from langchain_core.runnables import Runnable

from backend.agent.providers.gpt5_provider import build_gpt5_chat_model

try:
    from backend.agent.wrappers.import_resolver import make_import_resolver
except Exception:  # pragma: no cover
    make_import_resolver = None  # type: ignore


def build_import_resolver() -> Optional[Runnable]:
    """Build the import resolver runnable using the default GPT-5 chat model.

    Returns None if the wrapper or model is unavailable.
    """
    try:
        if make_import_resolver is None:
            return None
        model = build_gpt5_chat_model()
        if model is None:
            return None
        return make_import_resolver(model)
    except Exception:
        return None

