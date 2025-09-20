from __future__ import annotations

from typing import Optional
from langchain_core.runnables import Runnable

from backend.agent.wrappers.create_item_tags import make_create_item_tags


def build_create_item_tags() -> Optional[Runnable]:
    """Return a Runnable that updates ModItemTagProvider with item tag lines.

    This does not require an LLM; it renders a one-line template per tag and inserts
    them above the ITEM_TAGS_END anchor in ModItemTagProvider.java.
    """
    try:
        return make_create_item_tags()
    except Exception:
        return None

