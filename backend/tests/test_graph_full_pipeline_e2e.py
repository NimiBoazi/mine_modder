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
        "user_input": "Add sapphire and alexandrite items to my mod.",
    }

    def _print_snapshot(tag: str, s: Dict[str, Any]) -> None:
        # Summarize key fields to keep logs readable during long runs
        cm = (s.get("current_milestone") or {})
        ct = (s.get("current_task") or {})
        mq = s.get("milestones_queue") or []
        tq = s.get("task_queue") or []
        last_ev = (s.get("events") or [{}])[-1] if s.get("events") else {}
        artifacts = s.get("artifacts") or {}
        gradle_ok = (artifacts.get("gradle_smoke") or {}).get("ok")
        lines = [
            f"===== {tag} =====",
            f"node: {last_ev.get('node')}",
            f"workspace: {s.get('workspace_path')}",
            f"effective_mc_version: {s.get('effective_mc_version')}",
            f"items_initialized: {s.get('items_initialized')}",
            f"milestones_queue_len: {len(mq)} current_milestone: {{'id': {cm.get('id')}, 'title': {cm.get('title')}, 'order': {cm.get('order')}}}",
            f"task_queue_len: {len(tq)} current_task: {{'type': {ct.get('type')}, 'title': {ct.get('title')}}}",
            f"gradle_ok: {gradle_ok}",
        ]
        # Print to stdout (note: pytest captures unless run with -s)
        for ln in lines:
            print(ln, flush=True)
        # Also mirror to a log file that you can tail -f during the run
        try:
            log_dir = Path("runs/test_logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "full_pipeline_run.log").open("a", encoding="utf-8") as fh:
                for ln in lines:
                    fh.write(ln + "\n")
                fh.flush()
        except Exception:
            pass

    # Stream the graph and print a snapshot after each node update
    out: Dict[str, Any] | None = None
    try:
        for update in g.stream(initial_state, stream_mode="updates"):
            # update is a dict keyed by node name or special keys; merge to build state
            # We rely on the compiled graph to accumulate state internally; just print snapshot
            # We can extract any dict from update to inspect
            any_delta = next(iter(update.values())) if isinstance(update, dict) and update else None
            if isinstance(any_delta, dict):
                _print_snapshot("update", any_delta)
        # Final state is returned by .stream() generator when it finishes; re-invoke to get it
        out = g.invoke(initial_state)
    except Exception:
        # Fallback: if streaming unsupported, just invoke once
        out = g.invoke(initial_state)
        _print_snapshot("final", out)

    # Ensure we reached the end with a summary
    assert out is not None and out.get("summary") is not None, "Expected a final summary from summarize_and_finish"
    events = out.get("events", [])
    assert any(e.get("node") == "summarize_and_finish" for e in events), "Expected to reach summarize_and_finish"

    # Basic sanity on initialization outputs
    ws = out.get("workspace_path")
    assert ws and Path(ws).exists(), "Workspace should exist after init_subgraph"
    gradle = out.get("artifacts", {}).get("gradle_smoke", {})
    assert gradle.get("ok") is not False, "Gradle smoke build should not report failure"

