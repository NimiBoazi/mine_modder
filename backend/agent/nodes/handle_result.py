from ..state import AgentState
from typing import Any, Dict, List

_DEFAULT_TASK: Dict[str, Any] = {"type": None, "title": None, "params": {}}
_DEFAULT_MILESTONE: Dict[str, Any] = {"id": None, "title": None}


def handle_result(state: AgentState) -> AgentState:
    """
    Advance queues after a task/subgraph completes.
    Invariants:
    - current_task mirrors task_queue[0] when task_queue is non-empty
    - current_milestone mirrors milestones_queue[0] when milestones_queue is non-empty
    """
    print("[ENTER] node:handle_result")

    tq: List[Dict[str, Any]] = list(state.get("task_queue") or [])
    mq: List[Dict[str, Any]] = list(state.get("milestones_queue") or [])

    if tq:
        # Drop the current (head) task
        tq = tq[1:]
        state["task_queue"] = tq
        if tq:
            # Still tasks remaining in this milestone
            state["current_task"] = tq[0]
            state.setdefault("events", []).append({"node": "handle_result", "ok": True, "advanced": "task"})
            return state
        # No tasks remain: advance milestone now
        if mq:
            mq = mq[1:]
            state["milestones_queue"] = mq
            state["current_milestone"] = mq[0] if mq else {"id": None, "title": None}
        else:
            state["current_milestone"] = {"id": None, "title": None}
        state["current_task"] = {"type": None, "title": None, "params": {}}
        state.setdefault("events", []).append({"node": "handle_result", "ok": True, "advanced": "task_and_milestone"})
        return state

    # No tasks left for current milestone: advance milestones
    if mq:
        mq = mq[1:]
        state["milestones_queue"] = mq
        state["current_milestone"] = mq[0] if mq else {"id": None, "title": None}
    else:
        state["current_milestone"] = {"id": None, "title": None}

    # Reset current task when moving milestones
    state["current_task"] = {"type": None, "title": None, "params": {}}
    state.setdefault("events", []).append({"node": "handle_result", "ok": True, "advanced": "milestone"})
    return state