from ..state import AgentState

def weather_subgraph(state: AgentState) -> AgentState:
    state.setdefault("results", {})
    task = state.get("current_task") or {}
    state["results"][task.get("id", "")] = {"ok": True, "notes": ["weather stub"]}
    state.setdefault("events", []).append({"node": "weather_subgraph", "ok": True})
    return state