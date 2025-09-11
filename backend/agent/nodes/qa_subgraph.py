from ..state import AgentState

def qa_subgraph(state: AgentState) -> AgentState:
    state.setdefault("results", {})
    task = state.get("current_task") or {}
    state["results"][task.get("id", "")] = {"ok": True, "answer": "(stub)"}
    state.setdefault("events", []).append({"node": "qa_subgraph", "ok": True})
    return state