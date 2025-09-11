from ..state import AgentState

def block_subgraph(state: AgentState) -> AgentState:
    state.setdefault("results", {})
    task = state.get("current_task") or {}
    state["results"][task.get("id", "")] = {"ok": True, "changed_files": [], "notes": ["block stub"]}
    state.setdefault("events", []).append({"node": "block_subgraph", "ok": True})
    return state