from __future__ import annotations

import os
from typing import Optional
from langchain_core.runnables import Runnable

try:
    from langchain_openai import ChatOpenAI  # type: ignore
except Exception:  # pragma: no cover
    ChatOpenAI = None  # type: ignore

try:
    from backend.agent.wrappers.plan_next_tasks import make_next_tasks_planner
except Exception:  # pragma: no cover
    make_next_tasks_planner = None  # type: ignore


def build_gpt5_chat_model() -> Optional["ChatOpenAI"]:
    """Return a configured GPT-5 chat model instance, or None if unavailable.

    We centralize GPT-5 model construction here so any wrapper/provider can depend
    on a single source of truth for model setup.
    """
    try:
        if ChatOpenAI is None:
            return None
        if not os.getenv("OPENAI_API_KEY"):
            return None
        # Enforce timeouts and low retries to surface failures fast (no silent hangs)
        # Make timeout configurable via OPENAI_REQUEST_TIMEOUT (seconds)
        try:
            timeout_s = int(os.getenv("OPENAI_REQUEST_TIMEOUT", "60"))
        except Exception:
            timeout_s = 60
        return ChatOpenAI(model="gpt-5", max_retries=1, timeout=timeout_s)
    except Exception:
        return None


def build_next_tasks_planner() -> Optional[Runnable]:
    """Build a Runnable that plans next tasks, backed by GPT-5.

    Kept for compatibility with nodes/plan_next_tasks.py, but file renamed to
    reflect GPT-5 ownership of this provider.
    """
    try:
        if make_next_tasks_planner is None:
            return None
        model = build_gpt5_chat_model()
        if model is None:
            return None
        return make_next_tasks_planner(model)
    except Exception:
        return None

