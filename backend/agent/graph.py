from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableLambda
from .state import AgentState
from .nodes.intake import route_or_info
from .nodes.planning import decide_planning, create_tasklist
from .nodes.controller import select_action, route_action
from .nodes.actions import info_scoped, apply_safe_edits
from .nodes.verify import run_verification, verify_next
from .nodes.summarize import summarize_and_finish

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("route_or_info", RunnableLambda(route_or_info))
    g.add_node("create_tasklist", RunnableLambda(create_tasklist))
    g.add_node("select_action", RunnableLambda(select_action))
    g.add_node("info_scoped", RunnableLambda(info_scoped))
    g.add_node("apply_safe_edits", RunnableLambda(apply_safe_edits))
    g.add_node("run_verification", RunnableLambda(run_verification))
    g.add_node("summarize_and_finish", RunnableLambda(summarize_and_finish))

    g.add_conditional_edges(START, lambda s: "route_or_info")
    g.add_conditional_edges("route_or_info", decide_planning, {
        "create_tasklist": "create_tasklist",
        "direct_mode": "select_action",
    })
    g.add_edge("create_tasklist", "select_action")
    g.add_conditional_edges("select_action", route_action, {
        "info_scoped": "info_scoped",
        "apply_safe_edits": "apply_safe_edits",
        "run_verification": "run_verification",
        "summarize_and_finish": "summarize_and_finish",
    })
    g.add_edge("info_scoped", "select_action")
    g.add_edge("apply_safe_edits", "run_verification")
    g.add_conditional_edges("run_verification", verify_next, {
        "summarize_and_finish": "summarize_and_finish",
        "select_action": "select_action",
    })
    g.add_edge("summarize_and_finish", END)
    return g.compile()
