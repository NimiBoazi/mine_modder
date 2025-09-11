from ..state import AgentState

def handle_result(state: AgentState) -> AgentState:
    state.setdefault("events", []).append({"node": "handle_result", "ok": True})
    return state