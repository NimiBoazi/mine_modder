from __future__ import annotations

from typing import Dict, Any
from backend.agent.state import AgentState
from backend.agent.providers.plan_outline import build_high_level_outline


def high_level_outline_node(state: AgentState) -> AgentState:
    """
    Pure node: consumes state['user_input'], produces state['plan'] (high-level outline).
    """
    user_prompt = (state.get("user_input") or "").strip()
    if not user_prompt:
        raise RuntimeError("high_level_outline_node requires 'user_input' in state")

    runnable = build_high_level_outline()
    if runnable is None:
        raise RuntimeError("High-level outline provider unavailable or misconfigured.")

    outline: Dict[str, Any] = runnable.invoke({"user_prompt": user_prompt})

    # Update state (returning a delta is fine; tests use dict-style updates too)
    state["plan"] = outline
    state.setdefault("events", []).append({"node": "high_level_outline_node", "ok": True})
    return state

