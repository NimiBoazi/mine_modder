from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import pytest

from backend.agent.graph import build_graph


def _has_google_key() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY"))


@pytest.mark.skipif(not _has_google_key(), reason="GOOGLE_API_KEY not set; this test exercises real LLM providers.")
def test_graph_user_prompt_end_to_end(tmp_path: Path):
    """
    E2E test that drives the graph with a real user prompt and real providers.
    - Skips MDK init by providing minimal init params and _needs_init=False
    - Expects the graph to complete with summarize_and_finish and not raise.
    - Uses a temporary workspace; item_subgraph writes generated files into it.
    """
    g = build_graph()

    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)

    state: Dict[str, Any] = {
        "user_input": "Create a small mod that adds one custom item and prepares the project.",
        "framework": "neoforge",
        "workspace_path": str(workspace),
        "modid": "examplemod",
        "package": "net.example.examplemod",
        "_needs_init": False,  # route directly to plan_high_level
        # Optional: locations (defaulted in init path, but harmless here)
        "runs_root": str(tmp_path / "runs"),
        "downloads_root": str(tmp_path / "_downloads"),
        # Router/planner optional knobs
        "max_tasks": 3,
    }

    out = g.invoke(state)

    # Should produce a summary and reach END through summarize_and_finish
    assert out.get("summary") is not None, "Expected a summary at the end of the run"
    events = out.get("events", [])
    assert any(e.get("node") == "summarize_and_finish" for e in events), "Expected to reach summarize_and_finish"

    # Basic queue invariants (not strict, but should exist)
    assert "task_queue" in out
    assert "milestones_queue" in out or (out.get("milestones_queue") is None)

