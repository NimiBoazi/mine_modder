from __future__ import annotations

from typing import Optional
from langchain_core.runnables import Runnable

from backend.agent.providers.gpt5_provider import build_gpt5_chat_model
from backend.agent.wrappers.create_item_recipe import make_create_item_recipe


def build_create_item_recipe() -> Optional[Runnable]:
    """Return a Runnable that asks GPT-5 for recipe code and updates ModRecipeProvider.java."""
    try:
        model = build_gpt5_chat_model()
        if model is None:
            return None
        return make_create_item_recipe(model)
    except Exception:
        return None

