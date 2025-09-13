# backend/agent/nodes/router.py
from __future__ import annotations
from backend.agent.state import AgentState

ALLOWED_TASK_TYPE = "add_custom_item"


def route_task(state: AgentState) -> str:
    """Router with milestone/task queues semantics.
    Cases:
    1) milestones_queue empty AND task_queue empty -> summarize_and_finish
    2) milestones_queue not empty AND task_queue empty -> plan_next_tasks
    3) task_queue not empty -> route by current task type
    """
    # Normalize lists from state
    task_queue = list(state.get("task_queue") or [])
    milestones_queue = list(state.get("milestones_queue") or [])

    # If no explicit milestones_queue yet, peek at plan.milestones to infer non-empty
    plan = state.get("plan") or {}
    plan_milestones = list(plan.get("milestones") or [])
    milestones_empty = (len(milestones_queue) == 0) and (len(plan_milestones) == 0)

    if len(task_queue) == 0 and milestones_empty:
        return "summarize_and_finish"
    if len(task_queue) == 0:
        return "plan_next_tasks"

    # Case 3: route according to current task type (queue not empty; current should mirror task_queue[0])
    current = state.get("current_task") or (task_queue[0] if task_queue else {})
    t = (current.get("type") or "").strip()
    if t == ALLOWED_TASK_TYPE:
        return "item_subgraph"
    return "handle_result"


# Backwards-compat alias for existing graph wiring, if any
def route_task_skeleton(state: AgentState) -> str:
    return route_task(state)
