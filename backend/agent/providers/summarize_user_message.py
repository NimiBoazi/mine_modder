from __future__ import annotations

from typing import Optional
from langchain_core.runnables import Runnable

from backend.agent.providers.gpt41_provider import build_gpt41_chat_model
try:
    from backend.agent.providers.gpt5_provider import build_gpt5_chat_model
except Exception:  # pragma: no cover
    build_gpt5_chat_model = None  # type: ignore

try:
    from backend.agent.wrappers.summarize_user_message import make_summarize_user_message
except Exception:  # pragma: no cover
    make_summarize_user_message = None  # type: ignore


def build_summarize_user_message() -> Optional[Runnable]:
    """Builds a Runnable that converts mod + items + events into a friendly summary.
    Returns None if the model or wrapper isn't available, in which case callers
    should fall back to a simple deterministic summary.
    """
    try:
        if make_summarize_user_message is None:
            return None
        # Prefer GPT-4.1 for summarization; fall back to GPT-5 if needed
        model = build_gpt41_chat_model()
        if model is None and build_gpt5_chat_model is not None:
            model = build_gpt5_chat_model()
        if model is None:
            return None
        return make_summarize_user_message(model)
    except Exception:
        return None

