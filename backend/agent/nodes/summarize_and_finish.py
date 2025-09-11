from ..state import AgentState

def summarize_and_finish(state: AgentState) -> AgentState:
    # Summarize minimal info
    tasks = ((state.get("plan") or {}).get("tasks") or [])
    results = state.get("results") or {}
    summary = {
        "tasks": [t.get("type") for t in tasks],
        "ok_count": sum(1 for r in results.values() if r.get("ok")),
    }
    state["summary"] = summary
    state.setdefault("events", []).append({"node": "summarize_and_finish", "ok": True})
    return state