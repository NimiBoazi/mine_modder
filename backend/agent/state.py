from typing import TypedDict, Optional, Literal, Dict, Any, List

class AgentState(TypedDict, total=False):
    # Core input
    user_input: str
    framework: Optional[str]
    mc_version: Optional[str]
    author: Optional[str]           # frontend may send a single string
    authors: Optional[List[str]]    # normalized list

    # Planning and control
    plan: Optional[Dict[str, Any]]
    current_task: Optional[Dict[str, Any]]
    _needs_init: Optional[bool]
    _no_tasks_left: Optional[bool]
    awaiting_user: Optional[Dict[str, Any]]

    # Workspace/config
    workspace_path: Optional[str]
    runs_root: Optional[str]
    downloads_root: Optional[str]

    # Inferred/derived init params
    display_name: Optional[str]
    description: Optional[str]
    modid: Optional[str]
    group: Optional[str]
    package: Optional[str]
    version: Optional[str]
    timeout: Optional[int]

    # Artifacts + logs/results
    artifacts: Optional[Dict[str, Any]]
    results: Optional[Dict[str, Any]]
    events: Optional[List[Dict[str, Any]]]

    # Items registry + selection
    items: Optional[Dict[str, Dict[str, Any]]]   # { item_id: itemSchema-like dict }
    current_item_id: Optional[str]               # which item the pipeline is working on
    item: Optional[Dict[str, Any]]               # fully prepared schema for current item
    items_initialized: Optional[bool]            # init guard (runs once)

    # Legacy/general bookkeeping
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
