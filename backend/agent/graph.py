from __future__ import annotations

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableLambda
from dotenv import load_dotenv
from pathlib import Path

import os

# Progress logging wrappers for long-running tests
# Enable by setting environment variable MM_PROGRESS_LOG=1

def _snapshot_lines(tag: str, s: dict) -> list[str]:
    cm = (s.get("current_milestone") or {}) if isinstance(s, dict) else {}
    ct = (s.get("current_task") or {}) if isinstance(s, dict) else {}
    mq = (s.get("milestones_queue") or []) if isinstance(s, dict) else []
    tq = (s.get("task_queue") or []) if isinstance(s, dict) else []
    last_ev = (s.get("events") or [{}])[-1] if isinstance(s, dict) and s.get("events") else {}
    artifacts = (s.get("artifacts") or {}) if isinstance(s, dict) else {}
    gradle_ok = (artifacts.get("gradle_smoke") or {}).get("ok") if isinstance(artifacts, dict) else None
    return [
        f"===== {tag} =====",
        f"node: {last_ev.get('node')}",
        f"workspace: {s.get('workspace_path') if isinstance(s, dict) else None}",
        f"effective_mc_version: {s.get('effective_mc_version') if isinstance(s, dict) else None}",
        f"items_initialized: {s.get('items_initialized') if isinstance(s, dict) else None}",
        f"milestones_queue_len: {len(mq)} current_milestone: {{'id': {cm.get('id')}, 'title': {cm.get('title')}, 'order': {cm.get('order')}}}",
        f"task_queue_len: {len(tq)} current_task: {{'type': {ct.get('type')}, 'title': {ct.get('title')}}}",
        f"gradle_ok: {gradle_ok}",
    ]


def _maybe_wrap(name: str, fn):
    flag = os.getenv("MM_PROGRESS_LOG")
    if not flag or flag.strip().lower() not in {"1", "true", "yes", "on"}:
        return fn

    def _wrapped(state):
        res = fn(state)
        try:
            lines = _snapshot_lines(name, res)
            for ln in lines:
                print(ln, flush=True)
            log_dir = Path("runs/test_logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "full_pipeline_run.log").open("a", encoding="utf-8") as fh:
                for ln in lines:
                    fh.write(ln + "\n")
                fh.flush()
        except Exception:
            pass
        return res

    return _wrapped

from .state import AgentState
from .providers.llm import build_name_desc_extractor

# Node Imports
from .nodes.intake import intake
from .nodes.ensure_workspace import ensure_workspace
from .nodes.infer_init_params import make_infer_init_params_node
from .nodes.init_subgraph import init_subgraph

from .nodes.plan_next_tasks import next_task_planner_node
from .nodes.handle_result import handle_result
from .nodes.summarize_and_finish import summarize_and_finish
from .nodes.verify_task import verify_task

# Item Pipeline Imports
from .nodes.item_subgraph import item_subgraph

# Subgraph stubs
from .nodes.block_subgraph import block_subgraph
from .nodes.mob_subgraph import mob_subgraph
from .nodes.biome_subgraph import biome_subgraph
from .nodes.weather_subgraph import weather_subgraph
from .nodes.qa_subgraph import qa_subgraph

# Routing Imports
from .nodes.router import route_task, route_after_handle_result, route_after_verify

def build_graph():
    BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(BACKEND_ENV, override=False)
    g = StateGraph(AgentState)

    name_desc_extractor = build_name_desc_extractor()

    # Register nodes (optionally wrapped for progress logging)
    g.add_node("intake", RunnableLambda(_maybe_wrap("intake", intake)))
    g.add_node("ensure_workspace", RunnableLambda(_maybe_wrap("ensure_workspace", ensure_workspace)))
    g.add_node("infer_init_params", RunnableLambda(_maybe_wrap("infer_init_params", make_infer_init_params_node(name_desc_extractor))))
    g.add_node("init_subgraph", RunnableLambda(_maybe_wrap("init_subgraph", init_subgraph)))
    g.add_node("plan_next_tasks", RunnableLambda(_maybe_wrap("plan_next_tasks", next_task_planner_node)))
    g.add_node("handle_result", RunnableLambda(_maybe_wrap("handle_result", handle_result)))
    g.add_node("summarize_and_finish", RunnableLambda(_maybe_wrap("summarize_and_finish", summarize_and_finish)))
    g.add_node("verify_task", RunnableLambda(_maybe_wrap("verify_task", verify_task)))

    # Item pipeline
    g.add_node("item_subgraph", RunnableLambda(_maybe_wrap("item_subgraph", item_subgraph)))

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

    # Direct flow: always initialize, then plan next tasks
    g.add_edge("infer_init_params", "init_subgraph")
    g.add_edge("init_subgraph", "plan_next_tasks")

    # After planning next tasks, route to the appropriate next step
    g.add_conditional_edges("plan_next_tasks", route_task, {
        "item_subgraph": "item_subgraph",
        "summarize_and_finish": "summarize_and_finish",
    })

    for sub in ("item_subgraph", "block_subgraph", "mob_subgraph", "biome_subgraph", "weather_subgraph", "qa_subgraph"):
        g.add_edge(sub, "verify_task")
    g.add_conditional_edges("verify_task", route_after_verify, {
        "handle_result": "handle_result",
        "summarize_and_finish": "summarize_and_finish",
    })

    # After handling result, route based on queues
    g.add_conditional_edges("handle_result", route_after_handle_result, {
        "item_subgraph": "item_subgraph",
        "summarize_and_finish": "summarize_and_finish",
    })
    g.add_edge("summarize_and_finish", END)

    return g.compile()