from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from backend.agent.nodes.respond_to_user import respond_to_user as respond_node


class _StubRU:
    def __init__(self, plan_action: str = "PLAN_NEXT_TASKS", choose_files: list[dict] | None = None,
                 act_payload: Dict[str, Any] | None = None):
        self.plan_action = plan_action
        self.choose_files = choose_files or []
        self.act_payload = act_payload or {}
        self.calls: list[Dict[str, Any]] = []

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append(payload)
        stage = (payload.get("stage") or "").lower()
        if stage == "decide":
            return {"action": self.plan_action, "reason": "stub"}
        if stage == "choose":
            return {"files": self.choose_files}
        if stage == "act":
            return self.act_payload
        raise ValueError(f"Unexpected stage: {stage}")


@pytest.fixture()
def tmp_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def test_respond_to_user_errors_on_empty_followup(monkeypatch: pytest.MonkeyPatch, tmp_ws: Path):
    # Monkeypatch the provider builder to return our stub
    import backend.agent.nodes.respond_to_user as node_mod
    stub = _StubRU()
    monkeypatch.setattr(node_mod, "build_respond_to_user", lambda: stub)

    state: Dict[str, Any] = {
        "workspace_path": str(tmp_ws),
        "followup_user_input": "  ",
        "items": {},
    }

    with pytest.raises(RuntimeError):
        respond_node(state)


def test_respond_to_user_plan_next_tasks_path(monkeypatch: pytest.MonkeyPatch, tmp_ws: Path):
    import backend.agent.nodes.respond_to_user as node_mod
    stub = _StubRU(plan_action="PLAN_NEXT_TASKS")
    monkeypatch.setattr(node_mod, "build_respond_to_user", lambda: stub)

    state: Dict[str, Any] = {
        "workspace_path": str(tmp_ws),
        "followup_user_input": "add an alexandrite item",
        "items": {},
    }

    out = respond_node(state)
    assert out["route_after_respond"] == "plan_next_tasks"
    assert out.get("user_input") == "add an alexandrite item"
    assert out.get("followup_user_input") == "", "followup should be cleared to avoid loops"


def test_respond_to_user_view_files_path(monkeypatch: pytest.MonkeyPatch, tmp_ws: Path):
    # Prepare a file to view
    f = tmp_ws / "src/main/java/net/example/ModItems.java"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("public class ModItems {}\n", encoding="utf-8")

    import backend.agent.nodes.respond_to_user as node_mod
    stub = _StubRU(
        plan_action="VIEW_FILES",
        choose_files=[{"file_path": str(f.relative_to(tmp_ws)), "request_full_file": True}],
        act_payload={"answer": "Here is the info"},
    )
    monkeypatch.setattr(node_mod, "build_respond_to_user", lambda: stub)

    state: Dict[str, Any] = {
        "workspace_path": str(tmp_ws),
        "followup_user_input": "show me ModItems",
        "items": {},
    }

    out = respond_node(state)
    assert out["route_after_respond"] == "await_user_input"
    assert out.get("last_user_response") == "Here is the info"


def test_respond_to_user_edit_files_path(monkeypatch: pytest.MonkeyPatch, tmp_ws: Path):
    # Prepare a file with anchors
    f = tmp_ws / "src/main/java/net/example/ModItems.java"
    f.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join([
        "package net.example;",
        "import java.util.*;",
        "// ==MM:EXTRA_IMPORTS_END==",
        "public class ModItems {",
        "    // ==MM:ITEM_REGISTRATIONS_END==",
        "}",
        "",
    ])
    f.write_text(content, encoding="utf-8")

    import backend.agent.nodes.respond_to_user as node_mod
    stub = _StubRU(
        plan_action="EDIT_FILES",
        choose_files=[{"file_path": str(f.relative_to(tmp_ws)), "anchors": ["EXTRA_IMPORTS_END", "ITEM_REGISTRATIONS_END"]}],
        act_payload={"edits": {str(f.relative_to(tmp_ws)): {"EXTRA_IMPORTS_END": "import net.example.Item;", "ITEM_REGISTRATIONS_END": "// item reg"}}},
    )
    monkeypatch.setattr(node_mod, "build_respond_to_user", lambda: stub)

    state: Dict[str, Any] = {
        "workspace_path": str(tmp_ws),
        "followup_user_input": "insert imports and registry lines",
        "items": {},
    }

    out = respond_node(state)
    # Should route to verification after applying edits
    assert out["route_after_respond"] == "verify_task"
    # Verify edits were applied before anchors (insert_before_anchor)
    updated = f.read_text(encoding="utf-8")
    assert "import net.example.Item;\n// ==MM:EXTRA_IMPORTS_END==" in updated
    assert "// item reg\n    // ==MM:ITEM_REGISTRATIONS_END==" in updated

