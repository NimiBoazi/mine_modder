from ..state import AgentState

def biome_subgraph(state: AgentState) -> AgentState:
    print("[ENTER] node:biome_subgraph")

    state.setdefault("results", {})
    task = state.get("current_task") or {}
    state["results"][task.get("id", "")] = {"ok": True, "notes": ["biome stub"]}
    state.setdefault("events", []).append({"node": "biome_subgraph", "ok": True})
    return state