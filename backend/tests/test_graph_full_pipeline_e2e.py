from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import os
import pytest

from backend.agent.graph import build_graph


@pytest.mark.slow
def test_full_graph_runs_with_only_prompt():
    """
    Drive the entire agent graph from START to END with only a natural-language prompt.
    No state priming: framework, mc_version, paths, and everything else must be
    inferred or defaulted by the graph itself.

    Run from repo root:
    
    pytest -q backend/tests/test_graph_full_pipeline_e2e.py

    This test executes the real initialization (downloads/extracts MDK, runs Gradle
    smoke task), real planning via providers, and the item subgraph. It requires
    network access and valid provider credentials (e.g., GOOGLE_API_KEY).
    """
    # Enable per-node progress logging (also written to runs/test_logs/full_pipeline_run.log)
    os.environ["MM_PROGRESS_LOG"] = "1"
    g = build_graph()

    # Provide only the user's prompt
    initial_state: Dict[str, Any] = {
        "user_input": "Add a sapphire and alexandrite item to my mod.",
    }

    # Single invoke; per-node logging is handled by the graph wrappers via MM_PROGRESS_LOG
    out: Dict[str, Any] = g.invoke(initial_state)

    # Ensure we reached the end with a summary
    assert out is not None and out.get("summary") is not None, "Expected a final summary from summarize_and_finish"
    events = out.get("events", [])
    assert any(e.get("node") == "summarize_and_finish" for e in events), "Expected to reach summarize_and_finish"

    # Basic sanity on initialization outputs
    ws = out.get("workspace_path")
    assert ws and Path(ws).exists(), "Workspace should exist after init_subgraph"
    gradle = out.get("artifacts", {}).get("gradle_smoke", {})
    assert gradle.get("ok") is not False, "Gradle smoke build should not report failure"

