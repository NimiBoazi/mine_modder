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
    """Route after verify_task based on verification outcome.
    Rules:
    - If verification ok:
      - If last_followup_action was EDIT_FILES -> go to summarize_and_finish
      - Else -> advance queues via handle_result
    - If failed and there are more tasks queued -> advance to next task via handle_result
    - If failed and no more tasks -> summarize_and_finish (package flawed build and show errors)
    """
    print("[ENTER] node:route_after_verify")
    ver = state.get("verification") or {}
    ok = bool(ver.get("ok"))
    if ok:
        if (state.get("last_followup_action") or "").upper() == "EDIT_FILES":
            return "summarize_and_finish"
        return "handle_result"
    # Failure case: either max attempts reached or early exit; decide next step
    task_queue = list(state.get("task_queue") or [])
    # If more tasks remain after the current one, advance the queue and continue
    if len(task_queue) > 1:
        return "handle_result"
    # Otherwise, finalize and present errors + downloadable artifact
    return "summarize_and_finish"


def route_after_respond(state: AgentState) -> str:
    """Route after respond_to_user based on the node's decision.
    Allowed routes:
    - plan_next_tasks (default when undecided)
    - verify_task (after EDIT_FILE)
    - await_user_input (after VIEW_FILE)
    """
    print("[ENTER] node:route_after_respond")
    route = (state.get("route_after_respond") or "").strip()
    if route in {"plan_next_tasks", "verify_task", "await_user_input"}:
        return route
    # Default to planning next tasks instead of idling
    return "plan_next_tasks"


# Backwards-compat alias for existing graph wiring, if any
def route_task_skeleton(state: AgentState) -> str:
    return route_task(state)


def route_after_await(state: AgentState) -> str:
    """After await_user_input, route to respond_to_user if input present, else loop on await_user_input."""
    print("[ENTER] node:route_after_await")
    # Accept either followup_message (preferred) or followup_user_input (legacy)
    followup_raw = (state.get("followup_message") or state.get("followup_user_input") or "")
    followup = followup_raw.strip()
    print(f"[ROUTER] route_after_await followup_len={len(followup)} preview={followup[:120]!r}")
    return "respond_to_user" if followup else "await_user_input"
