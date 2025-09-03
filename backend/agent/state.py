from typing import TypedDict, Optional, Literal, Dict, Any

class AgentState(TypedDict, total=False):
    user_input: str
    info_called: bool
    tasklist_active: bool
    iteration: int
    max_iterations: int
    plan_needed: bool
    current_task_id: Optional[str]
    last_info_result: Optional[Dict[str, Any]]
    last_action: Optional[Literal["info","edit","verify","summarize"]]
    verification: Optional[Dict[str, Any]]
    summary: Optional[str]
