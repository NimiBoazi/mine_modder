from __future__ import annotations

from typing import Dict, Any, List
from backend.agent.state import AgentState
from backend.agent.providers.plan_next_tasks import build_next_tasks_planner


def next_task_planner_node(state: AgentState) -> AgentState:
    """
    Pure node: consumes (user_input, plan) and produces a short-term milestone
    with task_queue and sets current_task.

    Expects:
      - state['plan']: high-level outline (from high_level_outline_node)
      - optional state['max_tasks'] (int)
    Produces:
      - state['task_queue']: upcoming tasks (list of dict)
      - state['current_task']: first task to execute
    """
    if not state.get("plan"):
        raise RuntimeError("next_task_planner_node requires 'plan' in state")
    runnable = build_next_tasks_planner()
    if runnable is None:
        raise RuntimeError("Next-tasks planner provider unavailable or misconfigured.")

    user_prompt = state.get("user_input", "")
    outline = state["plan"]
    max_tasks = int(state.get("max_tasks", 3))

    # Ensure milestones_queue exists and current_milestone mirrors its head
    milestones_queue: List[Dict[str, Any]] = list(state.get("milestones_queue") or [])
    if not milestones_queue:
        milestones_queue = list((outline.get("milestones") or []))
        state["milestones_queue"] = milestones_queue
        state["current_milestone"] = milestones_queue[0] if milestones_queue else None

    # Determine current milestone selector for wrapper: use head index 0
    current_selector: Any = 0 if milestones_queue else None

    result: Dict[str, Any] = runnable.invoke({
        "user_prompt": user_prompt,
        "outline": outline,
        "current_milestone": current_selector,
        "max_tasks": max_tasks,
    })

    tasks: List[Dict[str, Any]] = list(result.get("tasks") or [])
    if not tasks:
        raise RuntimeError("Planner returned no tasks")

    # Queue invariant: current_task == task_queue[0]
    state["task_queue"] = tasks
    state["current_task"] = tasks[0]
    state.setdefault("events", []).append({
        "node": "next_task_planner_node", "ok": True, "planned": len(tasks)
    })
    return state

