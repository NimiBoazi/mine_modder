from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import pytest
from langchain_core.runnables import RunnableLambda

from backend.agent.graph import build_graph


@pytest.mark.parametrize("framework", ["neoforge"])  # expand later if needed
def test_graph_runs_start_to_finish(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, framework: str):
    """
    End-to-end smoke test of the new planning + routing flow using stubs.
    - Stubs the LLM providers and the item_subgraph so we don't hit external services or disk-heavy ops.
    - Verifies the graph reaches END and produces a summary without errors.
    """

    # --- Stub providers ---
    # High-level outline: single milestone
    def stub_build_high_level_outline():
        def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "project_summary": "Test outline",
                "milestones": [
                    {"id": "M1", "title": "Add item", "objective": "Add a custom item", "deliverables": []}
                ],
            }
        return RunnableLambda(lambda x: _run(x))

    # Next tasks planner: one add_custom_item task
    def stub_build_next_tasks_planner():
        def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "milestone_title": "Add item",
                "tasks": [
                    {"type": "add_custom_item", "title": "Add custom item", "params": {}}
                ],
            }
        return RunnableLambda(lambda x: _run(x))

    # Item schema extractor: minimal deterministic schema
    def stub_build_item_schema_extractor():
        def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "item_id": "test_item",
                "display_name": "Test Item",
                "add_to_creative": True,
                "creative_tab_key": "CreativeModeTabs.INGREDIENTS",
                "model_type": "basicItem",
                "registry_constant": "TEST_ITEM",
            }
        return RunnableLambda(lambda x: _run(x))

    # Item subgraph: stub do-nothing but mark success
    def stub_item_subgraph(state):
        state.setdefault("results", {}).setdefault("t_add_item", {"ok": True})
        state.setdefault("events", []).append({"node": "item_subgraph", "ok": True})
        return state

    # Apply monkeypatches
    monkeypatch.setenv("GOOGLE_API_KEY", "stub")  # ensure provider gates don't abort early
    import backend.agent.providers.plan_outline as pov
    import backend.agent.providers.plan_next_tasks as pnt
    import backend.agent.providers.item_schema as pis
    import backend.agent.nodes.item_subgraph as n_item

    monkeypatch.setattr(pov, "build_high_level_outline", stub_build_high_level_outline)
    monkeypatch.setattr(pnt, "build_next_tasks_planner", stub_build_next_tasks_planner)
    monkeypatch.setattr(pis, "build_item_schema_extractor", stub_build_item_schema_extractor)
    monkeypatch.setattr(n_item, "item_subgraph", stub_item_subgraph)

    # Build graph
    g = build_graph()

    # Minimal state to skip init_subgraph path and allow planning
    runs_root = tmp_path / "runs"
    downloads_root = tmp_path / "_downloads"
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)

    state: Dict[str, Any] = {
        "user_input": "Please add a custom item.",
        "framework": framework,
        "workspace_path": str(workspace),
        "modid": "examplemod",
        "package": "net.example.examplemod",
        "_needs_init": False,  # route directly to plan_high_level
        "runs_root": str(runs_root),
        "downloads_root": str(downloads_root),
    }

    out = g.invoke(state)

    # Assertions: reached summary and no errors raised
    assert out.get("summary") is not None, "Graph should produce a summary at the end"
    assert any(ev.get("node") == "summarize_and_finish" for ev in out.get("events", [])), "Should reach summarize_and_finish"
    # Router invariants: queues progressed
    assert isinstance(out.get("task_queue"), list)
    assert isinstance(out.get("milestones_queue"), list) or out.get("milestones_queue") is None

