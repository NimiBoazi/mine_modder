from __future__ import annotations

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableLambda
from dotenv import load_dotenv
from pathlib import Path

import os

# Progress logging + UI progress messages
# - File/console logging is gated by MM_PROGRESS_LOG
# - UI progress events are emitted (when on_event is provided) only for selected nodes

UI_PROGRESS_MESSAGES = {
    "intake": "Initializing workspace",
    "infer_init_params": "initializing mod file",
    "plan_next_tasks": "planning project outline",
    "item_subgraph": "creating {item display name} custom item",
    "verify_task": "checking for errors",
    "summarize_and_finish": "finalizing project",
    "respond_to_user": "understanding user request",
}

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
        f"milestones_queue_len: {len(mq)} current_milestone: {'id': %s, 'title': %s, 'order': %s}" % (cm.get('id'), cm.get('title'), cm.get('order')),
        f"task_queue_len: {len(tq)} current_task: {'type': %s, 'title': %s}" % (ct.get('type'), ct.get('title')),
        f"gradle_ok: {gradle_ok}",
    ]


def _maybe_wrap(name: str, fn, on_event=None):
    def _emit_ui_progress(state_like):
        if on_event is None:
            return
        if name not in UI_PROGRESS_MESSAGES:
            return
        msg = UI_PROGRESS_MESSAGES[name]
        try:
            text = str(msg)
            if "{item display name}" in text:
                # Prefer state['item']['display_name'] if available
                disp = ""
                try:
                    item = (state_like or {}).get("item") if isinstance(state_like, dict) else None
                    if isinstance(item, dict):
                        disp = (item.get("display_name") or "").strip()
                except Exception:
                    disp = ""
                if not disp:
                    # fallback to current task title or generic
                    try:
                        ct = (state_like or {}).get("current_task") if isinstance(state_like, dict) else None
                        if isinstance(ct, dict):
                            disp = (ct.get("title") or ct.get("name") or "").strip()
                    except Exception:
                        pass
                if not disp:
                    disp = "custom"
                text = text.replace("{item display name}", disp)
            minimal_state = {}
            try:
                if isinstance(state_like, dict):
                    minimal_state = {
                        k: state_like.get(k)
                        for k in ("workspace_path", "summary")
                        if k in state_like
                    }
            except Exception:
                minimal_state = {}
            on_event("progress", {"node": name, "message": text, "state": minimal_state})
        except Exception:
            pass

    def _wrapped(state):
        # Inject a transient UI emitter callback into state so nodes can emit mid-node
        try:
            if on_event is not None and isinstance(state, dict):
                state["_ui_emit"] = on_event
        except Exception:
            pass

        # Emit UI message before the node starts
        # Skip for item_subgraph (emits mid-node) and summarize_and_finish (we only want post-node)
        if name not in ("item_subgraph", "summarize_and_finish"):
            _emit_ui_progress(state)

        res = fn(state)

        # Cleanup transient emitter from state/res
        try:
            if isinstance(state, dict) and "_ui_emit" in state:
                state.pop("_ui_emit", None)
            if isinstance(res, dict) and "_ui_emit" in res:
                res.pop("_ui_emit", None)
        except Exception:
            pass

        # Emit UI message after the node (skip for item_subgraph to avoid duplicate)
        if name != "item_subgraph":
            _emit_ui_progress(res)

        # Optional debug logging to file/console
        try:
            flag = os.getenv("MM_PROGRESS_LOG")
            if flag and flag.strip().lower() in {"1", "true", "yes", "on"}:
                lines = _snapshot_lines(name, res if isinstance(res, dict) else {})
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
from .nodes.verify_task import simple_verify_task as verify_task
from .nodes.respond_to_user import respond_to_user
from .nodes.await_user_input import await_user_input

# Item Pipeline Imports
from .nodes.item_subgraph import item_subgraph

# Subgraph stubs
from .nodes.block_subgraph import block_subgraph
from .nodes.mob_subgraph import mob_subgraph
from .nodes.biome_subgraph import biome_subgraph
from .nodes.weather_subgraph import weather_subgraph
from .nodes.qa_subgraph import qa_subgraph

# Routing Imports
from .nodes.router import route_task, route_after_handle_result, route_after_verify, route_after_respond, route_after_await

def build_graph(on_event=None, checkpointer=None):
    BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(BACKEND_ENV, override=False)
    g = StateGraph(AgentState)

    name_desc_extractor = build_name_desc_extractor()

    # Register nodes (optionally wrapped for progress logging)
    g.add_node("intake", RunnableLambda(_maybe_wrap("intake", intake, on_event)))
    g.add_node("ensure_workspace", RunnableLambda(_maybe_wrap("ensure_workspace", ensure_workspace, on_event)))
    g.add_node("infer_init_params", RunnableLambda(_maybe_wrap("infer_init_params", make_infer_init_params_node(name_desc_extractor), on_event)))
    g.add_node("init_subgraph", RunnableLambda(_maybe_wrap("init_subgraph", init_subgraph, on_event)))
    g.add_node("plan_next_tasks", RunnableLambda(_maybe_wrap("plan_next_tasks", next_task_planner_node, on_event)))
    g.add_node("handle_result", RunnableLambda(_maybe_wrap("handle_result", handle_result, on_event)))
    g.add_node("summarize_and_finish", RunnableLambda(_maybe_wrap("summarize_and_finish", summarize_and_finish, on_event)))
    g.add_node("verify_task", RunnableLambda(_maybe_wrap("verify_task", verify_task, on_event)))
    g.add_node("respond_to_user", RunnableLambda(_maybe_wrap("respond_to_user", respond_to_user, on_event)))
    g.add_node("await_user_input", RunnableLambda(_maybe_wrap("await_user_input", await_user_input, on_event)))

    # Item pipeline
    g.add_node("item_subgraph", RunnableLambda(_maybe_wrap("item_subgraph", item_subgraph, on_event)))

    # Task subgraphs
    g.add_node("block_subgraph", RunnableLambda(block_subgraph))
    g.add_node("mob_subgraph", RunnableLambda(mob_subgraph))
    g.add_node("biome_subgraph", RunnableLambda(biome_subgraph))
    g.add_node("weather_subgraph", RunnableLambda(weather_subgraph))
    g.add_node("qa_subgraph", RunnableLambda(qa_subgraph))

    # Define edges
    def _start_router(s):
        try:
            state = s or {}
            # If resuming with follow-up text, only jump to respond_to_user when the workspace has been initialized
            followup = (((state.get("followup_message") or state.get("followup_user_input")) or "").strip())
            if followup:
                has_ws = bool(state.get("workspace_path"))
                has_core = bool(state.get("framework")) and bool(state.get("modid")) and bool(state.get("package"))
                if has_ws and has_core:
                    return "respond_to_user"
                # Otherwise, ensure we go through initialization first
                return "intake"
            # Otherwise, if we are awaiting input, show the await gate
            awaiting = bool(state.get("awaiting_user_input"))
            if awaiting:
                return "await_user_input"
        except Exception:
            pass
        return "intake"

    g.add_conditional_edges(START, _start_router)
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
        "respond_to_user": "respond_to_user",
    })

    # After handling result, route based on queues
    g.add_conditional_edges("handle_result", route_after_handle_result, {
        "item_subgraph": "item_subgraph",
        "summarize_and_finish": "summarize_and_finish",
    })
    # After summarize, directly go to awaiting user input
    g.add_edge("summarize_and_finish", "await_user_input")
    # From await_user_input: either proceed to respond_to_user or keep waiting
    g.add_conditional_edges("await_user_input", route_after_await, {
        "respond_to_user": "respond_to_user",
        "await_user_input": END,
    })
    # From respond_to_user: plan next tasks, verify, or back to await input
    g.add_conditional_edges("respond_to_user", route_after_respond, {
        "plan_next_tasks": "plan_next_tasks",
        "verify_task": "verify_task",
        "await_user_input": "await_user_input",
    })

    return g.compile(checkpointer=checkpointer) if checkpointer is not None else g.compile()