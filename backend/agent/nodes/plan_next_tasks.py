from __future__ import annotations

from typing import Dict, Any, List
from backend.agent.state import AgentState
from backend.agent.providers.gpt5_provider import build_next_tasks_planner


def next_task_planner_node(state: AgentState) -> AgentState:
    """
    Pure node: consumes (user_input, optional available_tasks) and produces a
    short-term task_queue and sets current_task.

    Expects:
      - state['user_input']: the user's request / mod description
      - optional state['available_tasks']: list of allowed task types/descriptors the planner may choose from
      - optional state['max_tasks'] (int)

    Produces:
      - state['task_queue']: planned tasks (list of dict)
      - state['current_task']: first task to execute (dict or None)
    """
    print("[ENTER] node:next_task_planner_node")

    user_prompt = state.get("user_input", "") or ""
    if not user_prompt.strip():
        raise RuntimeError("next_task_planner_node requires non-empty 'user_input' in state")

    runnable = build_next_tasks_planner()
    if runnable is None:
        raise RuntimeError("Next-tasks planner provider unavailable or misconfigured.")

    available_tasks: List[Dict[str, Any]] = list(state.get("available_tasks") or state.get("possible_tasks") or [])
    max_tasks = int(state.get("max_tasks", 5))

    # Ask the LLM to plan tasks purely from the user prompt (and optional allowed task catalog).
    result: Dict[str, Any] = runnable.invoke({
        "user_prompt": user_prompt,
        "available_tasks": available_tasks,
        "max_tasks": max_tasks,
    })

    tasks: List[Dict[str, Any]] = list(result.get("tasks") or [])

    # Queue invariant: current_task == task_queue[0] when tasks exist
    state["task_queue"] = tasks
    state["current_task"] = tasks[0] if tasks else None

    state.setdefault("events", []).append({
        "node": "next_task_planner_node",
        "ok": True,
        "planned": len(tasks),
        "source": "prompt_only" + ("_with_catalog" if available_tasks else "")
    })
    return state


