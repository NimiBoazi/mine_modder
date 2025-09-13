from __future__ import annotations

import os
from typing import Optional
from langchain_core.runnables import Runnable

# Vendor model and wrapper live behind this provider
try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover
    ChatOpenAI = None  # type: ignore

try:
    from ..wrappers.plan_outline import make_high_level_outline_wrapper
except Exception:  # pragma: no cover
    make_high_level_outline_wrapper = None  # type: ignore


def build_high_level_outline() -> Optional[Runnable]:
    """Builds a Runnable that takes {"user_prompt": str} and returns a high-level outline.
    Returns None if unavailable or misconfigured.
    """
    try:
        if ChatOpenAI is None or make_high_level_outline_wrapper is None:
            return None
        if not os.getenv("OPENAI_API_KEY"):
            return None
        model = ChatOpenAI(model="gpt-5")
        return make_high_level_outline_wrapper(model)
    except Exception:
        return None

