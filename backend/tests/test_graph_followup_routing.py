from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from backend.agent.graph import build_graph


@pytest.fixture()
def tmp_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def test_graph_routes_directly_to_respond_on_followup(monkeypatch: pytest.MonkeyPatch, tmp_ws: Path):
    # Stub respond_to_user node to capture followup and avoid hitting LLM/providers
    captured: Dict[str, Any] = {}

    def stub_respond_node(state: Dict[str, Any]) -> Dict[str, Any]:
        captured["entered"] = True
        captured["followup"] = (state.get("followup_user_input") or "").strip()
        # Simulate answering and returning to await_user_input
        return {
            "last_user_response": f"echo: {captured['followup']}",
            "route_after_respond": "await_user_input",
            # Clear followup to avoid loops
            "followup_user_input": "",
        }

    # Patch the symbol used by build_graph (imported into graph module)
    import backend.agent.graph as graph_mod
    monkeypatch.setattr(graph_mod, "respond_to_user", stub_respond_node)

    # Also patch planner to avoid requiring user_input in this routing test
    def stub_planner(state: Dict[str, Any]) -> Dict[str, Any]:
        return state
    monkeypatch.setattr(graph_mod, "next_task_planner_node", stub_planner)

    g = build_graph()

    state: Dict[str, Any] = {
        # Key for START router to jump straight to respond_to_user
        "followup_user_input": "hello from chat",
        # Minimal fields to satisfy nodes that might look for them
        "workspace_path": str(tmp_ws),
    }

    out = g.invoke(state)

    assert captured.get("entered") is True, "respond_to_user should be invoked when followup is present at START"
    assert captured.get("followup") == "hello from chat"
    # Our stub sends us back to await_user_input and clears followup, so the graph should end
    assert out.get("last_user_response", "").startswith("echo: hello from chat")


def test_graph_awaits_when_no_followup(monkeypatch: pytest.MonkeyPatch, tmp_ws: Path):
    # Ensure our respond_to_user stub is NOT invoked in this case
    # Patch the symbol used by build_graph
    import backend.agent.graph as graph_mod

    def fail_if_called(state: Dict[str, Any]):
        raise AssertionError("respond_to_user should not be called when there is no followup input")

    monkeypatch.setattr(graph_mod, "respond_to_user", fail_if_called)

    g = build_graph()

    # Start in a state that indicates we are awaiting input but have none
    state: Dict[str, Any] = {
        "awaiting_user_input": True,
        "followup_user_input": "   ",
        "workspace_path": str(tmp_ws),
    }

    out = g.invoke(state)

    # Graph should go to await_user_input then END without calling respond_to_user
    assert out.get("last_user_response") in (None, ""), "There should be no chat response when there is no followup"

