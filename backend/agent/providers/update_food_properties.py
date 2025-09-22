from __future__ import annotations

from typing import Optional
from langchain_core.runnables import Runnable

from backend.agent.providers.gpt5_provider import build_gpt5_chat_model

try:
    from backend.agent.wrappers.update_food_properties import make_update_food_properties
except Exception:  # pragma: no cover
    make_update_food_properties = None  # type: ignore


def build_update_food_properties() -> Optional[Runnable]:
    """Return a Runnable that asks GPT-5 for FoodProperties code and updates ModFoodProperties.java."""
    try:
        if make_update_food_properties is None:
            return None
        model = build_gpt5_chat_model()
        if model is None:
            return None
        return make_update_food_properties(model)
    except Exception:
        return None

