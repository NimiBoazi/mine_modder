# backend/agent/nodes/router_skeleton.py
from __future__ import annotations
from backend.agent.state import AgentState

def route_task_skeleton(state: AgentState) -> str:
    if state.get("_no_tasks_left"):
        return "summarize_and_finish"
    t = ((state.get("current_task") or {}).get("type") or "").strip()
    return {
        "create_item_object": "item_entry",      # was select_item_schema
        "add_custom_block": "block_subgraph",
        "add_custom_mob": "mob_subgraph",
        "add_custom_biome": "biome_subgraph",
        "add_custom_weather": "weather_subgraph",
        "qa": "qa_subgraph",
    }.get(t, "handle_result")
