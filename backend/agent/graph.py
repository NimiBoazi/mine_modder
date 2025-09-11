from __future__ import annotations

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableLambda
from dotenv import load_dotenv
from pathlib import Path

from .state import AgentState
from .providers.llm import build_name_desc_extractor

# Node Imports
from .nodes.intake import intake
from .nodes.ensure_workspace import ensure_workspace
from .nodes.infer_init_params import make_infer_init_params_node
from .nodes.init_subgraph import init_subgraph
from .nodes.planner import planner_node
from .nodes.next_task import next_task
from .nodes.handle_result import handle_result
from .nodes.summarize_and_finish import summarize_and_finish
from .nodes.verify_task import verify_task

# Item Pipeline Imports
from .nodes.item_entry import item_entry
from .nodes.item_init import items_init_guard
from .nodes.item_subgraph import item_subgraph

# Subgraph stubs
from .nodes.block_subgraph import block_subgraph
from .nodes.mob_subgraph import mob_subgraph
from .nodes.biome_subgraph import biome_subgraph
from .nodes.weather_subgraph import weather_subgraph
from .nodes.qa_subgraph import qa_subgraph

# Routing Imports
from .nodes.router import route_task_skeleton
from .nodes.item_route import route_item_init
from .nodes.decide_after_result import decide_after_result

def build_graph():
    BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(BACKEND_ENV, override=False)
    g = StateGraph(AgentState)

    name_desc_extractor = build_name_desc_extractor()

    # Register nodes
    g.add_node("intake", RunnableLambda(intake))
    g.add_node("ensure_workspace", RunnableLambda(ensure_workspace))
    g.add_node("infer_init_params", RunnableLambda(make_infer_init_params_node(name_desc_extractor)))
    g.add_node("init_subgraph", RunnableLambda(init_subgraph))
    g.add_node("planner", RunnableLambda(planner_node))
    g.add_node("next_task", RunnableLambda(next_task))
    g.add_node("handle_result", RunnableLambda(handle_result))
    g.add_node("summarize_and_finish", RunnableLambda(summarize_and_finish))
    g.add_node("verify_task", RunnableLambda(verify_task))
    
    # Item pipeline
    g.add_node("item_entry", RunnableLambda(item_entry))
    g.add_node("items_init_guard", RunnableLambda(items_init_guard))
    g.add_node("item_subgraph", RunnableLambda(item_subgraph))

    # Task subgraphs
    g.add_node("block_subgraph", RunnableLambda(block_subgraph))
    g.add_node("mob_subgraph", RunnableLambda(mob_subgraph))
    g.add_node("biome_subgraph", RunnableLambda(biome_subgraph))
    g.add_node("weather_subgraph", RunnableLambda(weather_subgraph))
    g.add_node("qa_subgraph", RunnableLambda(qa_subgraph))

    # Define edges
    g.add_conditional_edges(START, lambda _s: "intake")
    g.add_edge("intake", "ensure_workspace")
    g.add_edge("ensure_workspace", "infer_init_params")

    def route_workspace(state: AgentState) -> str:
        return "init_subgraph" if state.get("_needs_init") else "planner"

    g.add_conditional_edges("infer_init_params", route_workspace, {"init_subgraph": "init_subgraph", "planner": "planner"})
    g.add_edge("init_subgraph", "planner")
    g.add_edge("planner", "next_task")

    g.add_conditional_edges("next_task", route_task_skeleton, {
        "item_entry": "item_entry",
        "block_subgraph": "block_subgraph",
        "mob_subgraph": "mob_subgraph",
        "biome_subgraph": "biome_subgraph",
        "weather_subgraph": "weather_subgraph",
        "qa_subgraph": "qa_subgraph",
        "summarize_and_finish": "summarize_and_finish",
        "handle_result": "handle_result",
    })
    
    g.add_conditional_edges("item_entry", route_item_init, {"items_init_guard": "items_init_guard", "item_subgraph": "item_subgraph"})
    g.add_edge("items_init_guard", "item_subgraph")

    for sub in ("item_subgraph", "block_subgraph", "mob_subgraph", "biome_subgraph", "weather_subgraph", "qa_subgraph"):
        g.add_edge(sub, "verify_task")
    g.add_edge("verify_task", "handle_result")

    g.add_conditional_edges("handle_result", decide_after_result, {"next_task": "next_task", "summarize_and_finish": "summarize_and_finish"})
    g.add_edge("summarize_and_finish", END)

    return g.compile()