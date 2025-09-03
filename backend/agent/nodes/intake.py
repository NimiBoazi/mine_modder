from ..state import AgentState
from ..policies import pick_high_signal_tool
from ...tools.augment_wrappers import high_signal_info

def route_or_info(state: AgentState) -> AgentState:
    if not state.get("info_called", False):
        tool = pick_high_signal_tool(state.get("user_input",""))
        state["last_info_result"] = high_signal_info(tool, state["user_input"])
        state["info_called"] = True
    return state
