from ..state import AgentState

def ensure_workspace(state: AgentState) -> AgentState:
    needs_init = not bool(state.get("workspace_path"))
    state["_needs_init"] = needs_init
    state.setdefault("events", []).append({"node": "ensure_workspace", "ok": True, "needs_init": needs_init})
    return state