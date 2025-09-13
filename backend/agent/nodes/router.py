# backend/agent/nodes/router.py
from __future__ import annotations
from backend.agent.state import AgentState

ALLOWED_TASK_TYPE = "add_custom_item"


def route_task(state: AgentState) -> str:
    """Router with milestone/task queues semantics.
    Rules:
    - Finish only if BOTH queues are empty
    - If tasks exist and type is add_custom_item -> item_subgraph
    - If no tasks but milestones remain -> plan_next_tasks
    """
    task_queue = list(state.get("task_queue") or [])
    milestones_queue = list(state.get("milestones_queue") or [])

    if len(task_queue) == 0 and len(milestones_queue) == 0:
        return "summarize_and_finish"

    if task_queue:
        current = state.get("current_task") or task_queue[0]
        t = (current.get("type") or "").strip()
        if t == ALLOWED_TASK_TYPE:
            return "item_subgraph"
        # No defensive fallback; unknown types are considered invalid in current design
        raise RuntimeError(f"Unsupported task type: {t}")

    # No tasks but milestones remain -> plan next tasks
    return "plan_next_tasks"


def route_after_handle_result(state: AgentState) -> str:
    """After handle_result:
    - If task_queue is empty -> go plan_next_tasks
    - If tasks remain -> route by task type (e.g., item_subgraph)
    """
    task_queue = list(state.get("task_queue") or [])
    if not task_queue:
        return "plan_next_tasks"
    return route_task(state)


# Backwards-compat alias for existing graph wiring, if any
def route_task_skeleton(state: AgentState) -> str:
    return route_task(state)
