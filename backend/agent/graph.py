from __future__ import annotations

from typing import Any, Dict, List, Optional
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableLambda

from .state import AgentState
import os
from dotenv import load_dotenv, find_dotenv
from pathlib import Path
from backend.core.models import Framework
from .tools.providers import resolve_url, download
from .tools.archive import extract_archive
from .tools.workspace import create as ws_create, copy_from_extracted
from .tools.placeholders import apply_placeholders
from .tools.java_toolchain import java_for, patch_toolchain
from .tools.repositories import (
    patch_settings_repositories,
    patch_forge_build_gradle_for_lwjgl_macos_patch,
)
from .tools.gradle import smoke_build
from .tools.storage_layer import STORAGE as storage
from .utils.infer import slugify_modid, derive_group_from_authors, make_package, truncate_desc
from .providers.llm import build_name_desc_extractor



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


def make_infer_init_params_node(name_desc_chain=None):
    def infer_init_params(state: AgentState) -> AgentState:
        """Infer name/description via injected chain, then derive modid/group/package/version/timeout.
        Expects framework, mc_version, and authors from frontend.
        """

        user_prompt = state.get("user_input") or ""
        name = state.get("display_name")
        desc = state.get("description")

        # Normalize authors: accept single string or list
        authors_val = state.get("authors") or state.get("author")
        if isinstance(authors_val, str):
            authors = [authors_val.strip()] if authors_val.strip() else []
            state["authors"] = authors
        elif isinstance(authors_val, list):
            state["authors"] = [str(a).strip() for a in authors_val if str(a).strip()]
        else:
            state["authors"] = []

        # LLM inference only if missing
        if not name or not desc:
            try:
                if name_desc_chain is not None:
                    out = name_desc_chain.invoke(user_prompt)
                    name = name or out.get("name")
                    desc = desc or out.get("description")
                else:
                    raise RuntimeError("No name/desc chain configured")
            except Exception:
                # Safe fallbacks if model unavailable
                name = name or "My Mod"
                desc = desc or "A Minecraft mod."

        desc = truncate_desc(desc or "")
        state["display_name"] = name
        state["description"] = desc

        # Derived
        modid = slugify_modid(name)
        authors = state.get("authors") or []
        group = derive_group_from_authors(authors)
        package = make_package(group, modid)

        state["modid"] = modid
        state["group"] = group
        state["package"] = package
        state.setdefault("version", "0.1.0")
        state.setdefault("timeout", 1800)

        state.setdefault("events", []).append({"node": "infer_init_params", "ok": True, "modid": modid, "group": group, "package": package})
        return state
    return infer_init_params


def route_after_clarify(state: AgentState) -> str:
    return "await_user" if state.get("_halt") else "ensure_workspace"


def await_user(state: AgentState) -> AgentState:
    qs = (state.get("awaiting_user") or {}).get("questions", [])
    state["summary"] = {"awaiting": qs}
    state.setdefault("events", []).append({"node": "await_user", "ok": True, "questions": qs})
    return state



def init_subgraph(state: AgentState) -> AgentState:
    """Run the real initialization pipeline using inferred params."""

    framework = state.get("framework")
    mc_version = state.get("mc_version")
    modid = state.get("modid")
    group = state.get("group")
    package = state.get("package")
    display_name = state.get("display_name")
    description = state.get("description")
    authors = state.get("authors") or []
    timeout = int(state.get("timeout", 1800))

    runs_root = Path(state.get("runs_root") or "runs")
    downloads_root = Path(state.get("downloads_root") or "runs/_downloads")

    # 1) Resolve + download
    fw_enum = Framework[framework.upper()]
    pr = resolve_url(fw_enum, mc_version)
    dl_dir = downloads_root / framework / mc_version
    from .tools.storage_layer import STORAGE as storage
    storage.ensure_dir(dl_dir)
    dest_zip = dl_dir / pr.filename
    download(pr.url, dest_zip)

    # 2) Extract
    extracted_dir = dl_dir / "extracted"
    root = extract_archive(dest_zip, extracted_dir)

    # 3) Create workspace and copy
    ws = ws_create(runs_root, modid=modid, framework=framework, mc_version=mc_version)
    copy_from_extracted(root, ws)

    # 4) Placeholders
    apply_placeholders(
        ws, framework,
        modid=modid,
        group=group,
        package=package,
        mc_version=mc_version,
        display_name=display_name,
        description=description,
        authors=authors or None,
    )

    # 5) Toolchain
    jv = java_for(mc_version)
    patch_toolchain(ws, jv, group=group)

    # 6) Repositories patch (idempotent)
    # Matches backend/tests/init_e2e.py behavior
    patch_settings_repositories(ws)

    # 6b) Forge-only LWJGL macOS patch on build.gradle (idempotent)
    if framework == "forge":
        patch_forge_build_gradle_for_lwjgl_macos_patch(ws)

    # 7) Gradle smoke build
    res = smoke_build(framework, ws, task_override=None, timeout=timeout)

    state["workspace_path"] = str(ws)
    state.setdefault("artifacts", {})["gradle_smoke"] = res
    state.setdefault("events", []).append({"node": "init_subgraph", "ok": bool(res.get("ok")), "workspace_path": str(ws)})
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
    # Continue if tasks remain; otherwise finish
    plan = state.get("plan") or {}
    tasks = plan.get("tasks") or []
    cursor = int(plan.get("cursor", 0))
    no_more = state.get("_no_tasks_left") or (cursor >= len(tasks))
    return "summarize_and_finish" if no_more else "next_task"


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

    # Load .env (repo root or backend/.env)
    BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"  # points to backend/.env
    load_dotenv(BACKEND_ENV, override=False)

    g = StateGraph(AgentState)

    # Build providers once (composition root)
    name_desc_extractor = build_name_desc_extractor()

    # Core nodes
    g.add_node("intake", RunnableLambda(intake))
    g.add_node("plan_tasks", RunnableLambda(plan_tasks))
    g.add_node("clarify_params", RunnableLambda(clarify_params))
    g.add_node("await_user", RunnableLambda(await_user))
    g.add_node("ensure_workspace", RunnableLambda(ensure_workspace))
    g.add_node("infer_init_params", RunnableLambda(make_infer_init_params_node(name_desc_extractor)))
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
    g.add_conditional_edges(START, lambda _s: "intake")
    g.add_edge("intake", "plan_tasks")
    g.add_conditional_edges("plan_tasks", route_after_plan, {
        "clarify_params": "clarify_params",
        "ensure_workspace": "ensure_workspace",
    })
    g.add_conditional_edges("clarify_params", route_after_clarify, {
        "await_user": "await_user",
        "ensure_workspace": "ensure_workspace",
    })

    # After we know required frontend params, infer init params from prompt
    g.add_edge("ensure_workspace", "infer_init_params")

    g.add_conditional_edges("infer_init_params", route_workspace, {
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
        "summarize_and_finish": "summarize_and_finish",
    })

    g.add_edge("summarize_and_finish", END)
    return g.compile()
