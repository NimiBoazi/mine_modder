from ..state import AgentState

def item_entry(state: AgentState) -> AgentState:
    state.setdefault("events", []).append({"node": "item_entry", "ok": True})
    return state