from __future__ import annotations

import os
from typing import Optional
from langchain_core.runnables import Runnable

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover
    ChatOpenAI = None  # type: ignore

try:
    from ..wrappers.plan_next_tasks import make_next_tasks_planner
except Exception:  # pragma: no cover
    make_next_tasks_planner = None  # type: ignore


def build_next_tasks_planner() -> Optional[Runnable]:
    """Builds a Runnable that plans the next small milestone tasks from allowed types.
    Returns None if unavailable or misconfigured.
    """
    try:
        if ChatOpenAI is None or make_next_tasks_planner is None:
            return None
        if not os.getenv("OPENAI_API_KEY"):
            return None
        model = ChatOpenAI(model="gpt-5")
        return make_next_tasks_planner(model)
    except Exception:
        return None

