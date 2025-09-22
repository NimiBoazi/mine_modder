# backend/agent/nodes/router.py
from __future__ import annotations
from backend.agent.state import AgentState

ALLOWED_TASK_TYPE = "add_custom_item"


def route_task(state: AgentState) -> str:
    """Route strictly by task queue (no milestones).
    Rules:
    - If no tasks -> summarize_and_finish
    - If tasks exist -> route by type to the correct subgraph
    """
    print("[ENTER] node:route_task")

    task_queue = list(state.get("task_queue") or [])

    if not task_queue:
        return "summarize_and_finish"

    current = state.get("current_task") or task_queue[0]
    t = (current.get("type") or "").strip()

    # Map known task types to subgraphs
    if t == ALLOWED_TASK_TYPE:
        return "item_subgraph"

    # Unknown task types are invalid for now
    raise RuntimeError(f"Unsupported task type: {t}")


def route_after_handle_result(state: AgentState) -> str:
    """After handle_result:
    - If task_queue is empty -> summarize_and_finish
    - If tasks remain -> route by task type (e.g., item_subgraph)
    """
    print("[ENTER] node:route_after_handle_result")
    task_queue = list(state.get("task_queue") or [])
    if not task_queue:
        return "summarize_and_finish"
    return route_task(state)


def route_after_verify(state: AgentState) -> str:
    """Route after verify_task based on verification outcome."""
    print("[ENTER] node:route_after_verify")
    ver = state.get("verification") or {}
    ok = bool(ver.get("ok"))
    return "handle_result" if ok else "summarize_and_finish"


# Backwards-compat alias for existing graph wiring, if any
def route_task_skeleton(state: AgentState) -> str:
    return route_task(state)
