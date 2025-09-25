from __future__ import annotations

from typing import Optional
from langchain_core.runnables import Runnable

from backend.agent.providers.gpt5_provider import build_gpt5_chat_model

try:
    from backend.agent.wrappers.respond_to_user import make_respond_to_user
except Exception:  # pragma: no cover
    make_respond_to_user = None  # type: ignore


def build_respond_to_user() -> Optional[Runnable]:
    """Return a Runnable that decides how to handle a user's follow-up request and, given context, produces edits/answers."""
    try:
        if make_respond_to_user is None:
            return None
        model = build_gpt5_chat_model()
        if model is None:
            return None
        return make_respond_to_user(model)
    except Exception:
        return None

