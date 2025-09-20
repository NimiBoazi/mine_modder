from __future__ import annotations

from typing import Optional
from langchain_core.runnables import Runnable

from backend.agent.wrappers.create_item_model import make_create_item_model


def build_create_item_model() -> Optional[Runnable]:
    """Return a Runnable that updates ModItemModelProvider with an item model registration line.

    This does not require an LLM; it renders a one-line template and inserts it
    above the ITEM_MODEL_REGISTRATIONS_END anchor in ModItemModelProvider.java.
    """
    try:
        return make_create_item_model()
    except Exception:
        return None

