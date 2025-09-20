from ..state import AgentState

def decide_after_result(state: AgentState) -> str:
    print("[ENTER] node:decide_after_result")

    plan = state.get("plan") or {}
    tasks = plan.get("tasks") or []
    cursor = int(plan.get("cursor", 0))
    no_more = state.get("_no_tasks_left") or (cursor >= len(tasks))
    return "summarize_and_finish" if no_more else "next_task"