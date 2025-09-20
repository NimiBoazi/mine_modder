from __future__ import annotations

from typing import Dict, Any
from backend.agent.state import AgentState
from backend.agent.providers.plan_outline import build_high_level_outline


def high_level_outline_node(state: AgentState) -> AgentState:
    """
    Pure node: consumes state['user_input'], produces state['plan'] (high-level outline).
    """
    print("[ENTER] node:high_level_outline_node")

    user_prompt = (state.get("user_input") or "").strip()
    if not user_prompt:
        raise RuntimeError("high_level_outline_node requires 'user_input' in state")

    runnable = build_high_level_outline()
    if runnable is None:
        raise RuntimeError("High-level outline provider unavailable or misconfigured.")

    outline: Dict[str, Any] = runnable.invoke({"user_prompt": user_prompt})

    # Update state with outline and initialize milestones_queue here (source of truth)
    state["plan"] = outline
    milestones = list((outline.get("milestones") or []))
    state["milestones_queue"] = milestones
    state["current_milestone"] = milestones[0] if milestones else None

    state.setdefault("events", []).append({"node": "high_level_outline_node", "ok": True})
    return state

