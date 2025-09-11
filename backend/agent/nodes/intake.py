from __future__ import annotations
from backend.agent.state import AgentState

def intake(state: AgentState) -> AgentState:
    state.setdefault("events", []).append({"node": "intake", "ok": True})
    return state
