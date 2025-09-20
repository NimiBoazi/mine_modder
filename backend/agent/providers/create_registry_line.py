from __future__ import annotations

from typing import Optional
from langchain_core.runnables import Runnable

from backend.agent.providers.gpt5_provider import build_gpt5_chat_model
from backend.agent.wrappers.create_registry_line import make_create_registry_line


def build_create_registry_line() -> Optional[Runnable]:
    """Return a Runnable that asks GPT-5 to craft the registry line and returns the updated ModItems.java content.
    """
    try:
        model = build_gpt5_chat_model()
        if model is None:
            return None
        return make_create_registry_line(model)
    except Exception:
        return None

