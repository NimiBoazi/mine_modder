from __future__ import annotations

from typing import Optional
from langchain_core.runnables import Runnable

from backend.agent.wrappers.update_creative_tab_item import make_update_creative_tab_item


def build_update_creative_tab_item() -> Optional[Runnable]:
    """Return a Runnable that updates the main class creative tab item accept block.

    This does not require an LLM; it renders a template line and inserts it above
    the CREATIVE_ITEM_ACCEPT_END anchor in the main class.
    """
    try:
        return make_update_creative_tab_item()
    except Exception:
        return None

