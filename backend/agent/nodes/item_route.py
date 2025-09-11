from backend.agent.state import AgentState

def route_item_init(state: AgentState) -> str:
    return "items_init_guard" if not state.get("items_initialized") else "item_subgraph"
