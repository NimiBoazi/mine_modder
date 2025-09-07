from __future__ import annotations

from typing import Any, Dict, List, Optional
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableLambda

from .state import AgentState


# ---------------------
# Minimal node impls to realize the proposed structure
# (Stubs now; plug real logic/subgraphs incrementally.)
# ---------------------

def intake(state: AgentState) -> AgentState:
    # No-op for now; in future parse channels, normalize input
    state.setdefault("events", []).append({"node": "intake", "ok": True})
    return state


def plan_tasks(state: AgentState) -> AgentState:
    # If a plan already exists, don't overwrite
    if "plan" in state and isinstance(state["plan"], dict):
        return state
    user_input = (state.get("user_input") or "").lower()
    tasks: List[Dict[str, Any]] = []
    # Extremely simple heuristic planner for demo purposes.
    if "block" in user_input:
        tasks.append({"id": "t_block_1", "type": "add_custom_block", "params": {}, "status": "pending"})
    if "weather" in user_input or "rain" in user_input:
        tasks.append({"id": "t_weather_1", "type": "add_custom_weather", "params": {}, "status": "pending"})
    # If nothing recognized, treat as QA for now
    if not tasks:
        tasks.append({"id": "t_qa_1", "type": "qa", "params": {"query": state.get("user_input", "")}, "status": "pending"})
    state["plan"] = {"tasks": tasks, "cursor": 0}
    state.setdefault("events", []).append({"node": "plan_tasks", "ok": True, "tasks": [t["type"] for t in tasks]})
    return state


def route_after_plan(state: AgentState) -> str:
    # If any task missing obvious params, we could ask. For now always proceed.
    return "ensure_workspace"


def clarify_params(state: AgentState) -> AgentState:
    # Placeholder: In future, validate task schemas and set awaiting_user if needed
    state.setdefault("events", []).append({"node": "clarify_params", "ok": True})
    return state


def ensure_workspace(state: AgentState) -> AgentState:
    # Decide if initialization is required (no workspace_path yet)
    needs_init = not bool(state.get("workspace_path"))
    state["_needs_init"] = needs_init
    state.setdefault("events", []).append({"node": "ensure_workspace", "ok": True, "needs_init": needs_init})
    return state


def route_workspace(state: AgentState) -> str:
    return "init_subgraph" if state.get("_needs_init") else "next_task"


def init_subgraph(state: AgentState) -> AgentState:
    # Stub: set a fake workspace so downstream nodes can run
    state["workspace_path"] = state.get("workspace_path") or "runs/_workspace_stub"
    state.setdefault("events", []).append({"node": "init_subgraph", "ok": True, "workspace_path": state["workspace_path"]})
    return state


def next_task(state: AgentState) -> AgentState:
    plan = state.get("plan") or {}
    cursor = int(plan.get("cursor", 0))
    tasks: List[Dict[str, Any]] = list(plan.get("tasks", []))
    if cursor >= len(tasks):
        state["_no_tasks_left"] = True
        state["current_task"] = None
    else:
        state["_no_tasks_left"] = False
        state["current_task"] = tasks[cursor]
        plan["cursor"] = cursor + 1
        state["plan"] = plan
    state.setdefault("events", []).append({"node": "next_task", "ok": True, "cursor": plan.get("cursor", 0)})
    return state


def route_next_task(state: AgentState) -> str:
    if state.get("_no_tasks_left"):
        return "summarize_and_finish"
    task = state.get("current_task") or {}
    t = task.get("type")
    return {
        "add_custom_block": "block_subgraph",
        "add_custom_mob": "mob_subgraph",
        "add_custom_biome": "biome_subgraph",
        "add_custom_weather": "weather_subgraph",
        "qa": "qa_subgraph",
    }.get(t, "handle_result")


# ---- Subgraph stubs (replace with real pipelines) ----

def block_subgraph(state: AgentState) -> AgentState:
    state.setdefault("results", {})
    task = state.get("current_task") or {}
    state["results"][task.get("id", "")] = {"ok": True, "changed_files": [], "notes": ["block stub"]}
    state.setdefault("events", []).append({"node": "block_subgraph", "ok": True})
    return state


def mob_subgraph(state: AgentState) -> AgentState:
    state.setdefault("results", {})
    task = state.get("current_task") or {}
    state["results"][task.get("id", "")] = {"ok": True, "notes": ["mob stub"]}
    state.setdefault("events", []).append({"node": "mob_subgraph", "ok": True})
    return state


def biome_subgraph(state: AgentState) -> AgentState:
    state.setdefault("results", {})
    task = state.get("current_task") or {}
    state["results"][task.get("id", "")] = {"ok": True, "notes": ["biome stub"]}
    state.setdefault("events", []).append({"node": "biome_subgraph", "ok": True})
    return state


def weather_subgraph(state: AgentState) -> AgentState:
    state.setdefault("results", {})
    task = state.get("current_task") or {}
    state["results"][task.get("id", "")] = {"ok": True, "notes": ["weather stub"]}
    state.setdefault("events", []).append({"node": "weather_subgraph", "ok": True})
    return state


def qa_subgraph(state: AgentState) -> AgentState:
    state.setdefault("results", {})
    task = state.get("current_task") or {}
    state["results"][task.get("id", "")] = {"ok": True, "answer": "(stub)"}
    state.setdefault("events", []).append({"node": "qa_subgraph", "ok": True})
    return state


def handle_result(state: AgentState) -> AgentState:
    state.setdefault("events", []).append({"node": "handle_result", "ok": True})
    return state


def decide_after_result(state: AgentState) -> str:
    # For now always continue; later honor fail-fast or user policy
    return "next_task"


def summarize_and_finish(state: AgentState) -> AgentState:
    # Summarize minimal info
    tasks = ((state.get("plan") or {}).get("tasks") or [])
    results = state.get("results") or {}
    summary = {
        "tasks": [t.get("type") for t in tasks],
        "ok_count": sum(1 for r in results.values() if r.get("ok")),
    }
    state["summary"] = summary
    state.setdefault("events", []).append({"node": "summarize_and_finish", "ok": True})
    return state


def build_graph():
    g = StateGraph(AgentState)

    # Core nodes
    g.add_node("intake", RunnableLambda(intake))
    g.add_node("plan_tasks", RunnableLambda(plan_tasks))
    g.add_node("clarify_params", RunnableLambda(clarify_params))
    g.add_node("ensure_workspace", RunnableLambda(ensure_workspace))
    g.add_node("init_subgraph", RunnableLambda(init_subgraph))
    g.add_node("next_task", RunnableLambda(next_task))
    g.add_node("handle_result", RunnableLambda(handle_result))
    g.add_node("summarize_and_finish", RunnableLambda(summarize_and_finish))

    # Subgraph stubs
    g.add_node("block_subgraph", RunnableLambda(block_subgraph))
    g.add_node("mob_subgraph", RunnableLambda(mob_subgraph))
    g.add_node("biome_subgraph", RunnableLambda(biome_subgraph))
    g.add_node("weather_subgraph", RunnableLambda(weather_subgraph))
    g.add_node("qa_subgraph", RunnableLambda(qa_subgraph))

    # Edges
    g.add_conditional_edges(START, lambda s: "intake")
    g.add_edge("intake", "plan_tasks")
    g.add_conditional_edges("plan_tasks", route_after_plan, {"ensure_workspace": "ensure_workspace"})
    g.add_edge("clarify_params", "ensure_workspace")  # currently unused path

    g.add_conditional_edges("ensure_workspace", route_workspace, {
        "init_subgraph": "init_subgraph",
        "next_task": "next_task",
    })
    g.add_edge("init_subgraph", "next_task")

    g.add_conditional_edges("next_task", route_next_task, {
        "block_subgraph": "block_subgraph",
        "mob_subgraph": "mob_subgraph",
        "biome_subgraph": "biome_subgraph",
        "weather_subgraph": "weather_subgraph",
        "qa_subgraph": "qa_subgraph",
        "summarize_and_finish": "summarize_and_finish",
        "handle_result": "handle_result",
    })

    for sub in ("block_subgraph", "mob_subgraph", "biome_subgraph", "weather_subgraph", "qa_subgraph"):
        g.add_edge(sub, "handle_result")

    g.add_conditional_edges("handle_result", decide_after_result, {
        "next_task": "next_task",
    })

    g.add_edge("summarize_and_finish", END)
    return g.compile()
