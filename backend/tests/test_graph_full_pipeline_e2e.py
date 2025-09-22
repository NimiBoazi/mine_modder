from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import os
import shutil

import pytest

from backend.agent.graph import build_graph


@pytest.mark.slow
def test_full_graph_runs_with_only_prompt():
    """
    Drive the entire agent graph from START to END with only a natural-language prompt.
    No state priming: framework, mc_version, paths, and everything else must be
    inferred or defaulted by the graph itself.

    Run from repo root:

      pytest -s -q backend/tests/test_graph_full_pipeline_e2e.py

    This test executes the real initialization (downloads/extracts MDK, runs Gradle
    smoke task), real planning via providers, and the item subgraph. It requires
    network access and valid provider credentials (e.g., GOOGLE_API_KEY).
    """
    # Clean slate: delete and recreate the runs folder for each test execution
    runs_dir = Path("runs")
    if runs_dir.exists():
        shutil.rmtree(runs_dir, ignore_errors=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Enable per-node progress logging (also written to runs/test_logs/full_pipeline_run.log)
    os.environ["MM_PROGRESS_LOG"] = "1"
    g = build_graph()

    # Provide only the user's prompt
    initial_state: Dict[str, Any] = {
        "user_input": "create a cannabis item and a rolling paper item and a medical cannabis ciggarette. The ciggarette should be made from the cannabis item and the rolling paper item. When consuming the ciggerette make smoke come out and the whole screen's color get a semi transparent red tint for a couple seconds.",
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

