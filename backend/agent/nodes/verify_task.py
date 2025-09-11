from __future__ import annotations
from backend.agent.state import AgentState

def verify_task(state: AgentState) -> AgentState:
    """Skeleton verification step that runs after every task subgraph."""
    task = state.get("current_task") or {}
    tid = task.get("id", "unknown")
    # TODO: implement real checks; for now record a pass
    state.setdefault("verification", {})[tid] = {"ok": True, "notes": ["verification stub"]}
    state.setdefault("events", []).append({"node": "verify_task", "ok": True, "task_id": tid})
    return state
