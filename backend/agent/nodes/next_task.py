from typing import Any, Dict, List
from ..state import AgentState

def next_task(state: AgentState) -> AgentState:
    plan = state.get("plan") or {}
    cursor = int(plan.get("cursor", 0))
    tasks: List[Dict[str, Any]] = list(plan.get("tasks", []))
    if cursor >= len(tasks):
        state["_no_tasks_left"] = True
        state["current_task"] = None
    else:
        state["_no_tasks_left"] = False
        state["current_task"] = tasks[cursor]
        plan["cursor"] = cursor + 1
        state["plan"] = plan
    state.setdefault("events", []).append({"node": "next_task", "ok": True, "cursor": plan.get("cursor", 0)})
    return state
