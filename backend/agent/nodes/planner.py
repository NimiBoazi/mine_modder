from __future__ import annotations
from typing import Any, Dict, List
from backend.agent.state import AgentState

def planner_node(state: AgentState) -> AgentState:
    """LLM-ready planner. For now: if items exist, make create_item_object tasks; else QA."""
    if isinstance(state.get("plan"), dict):
        state.setdefault("events", []).append({"node": "planner_node", "ok": True, "skipped": True})
        return state

    items: Dict[str, Dict[str, Any]] = state.get("items") or {}
    tasks: List[Dict[str, Any]] = []
    if items:
        for i, item_id in enumerate(items.keys(), start=1):
            tasks.append({"id": f"t_item_{i}", "type": "create_item_object", "params": {"item_id": item_id}, "status": "pending"})
    else:
        tasks.append({"id": "t_qa_1", "type": "qa", "params": {"query": state.get("user_input", "")}, "status": "pending"})

    state["plan"] = {"tasks": tasks, "cursor": 0}
    state.setdefault("events", []).append({"node": "planner_node", "ok": True, "planned_task_types": [t["type"] for t in tasks], "count": len(tasks)})
    return state
