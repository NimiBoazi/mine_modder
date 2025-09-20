from ..state import AgentState

def mob_subgraph(state: AgentState) -> AgentState:
    print("[ENTER] node:mob_subgraph")

    state.setdefault("results", {})
    task = state.get("current_task") or {}
    state["results"][task.get("id", "")] = {"ok": True, "notes": ["mob stub"]}
    state.setdefault("events", []).append({"node": "mob_subgraph", "ok": True})
    return state