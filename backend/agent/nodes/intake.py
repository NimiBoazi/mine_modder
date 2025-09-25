from __future__ import annotations
from backend.agent.state import AgentState
import uuid

def intake(state: AgentState) -> AgentState:
    print("[ENTER] node:intake")

    # Hard reset of per-run, mutable collections to avoid cross-run bleed-through.
    # This node is only entered on new runs (chat turns route directly to respond_to_user),
    # so it is safe to clear these here without affecting follow-up conversations.
    state["items"] = {}
    state["created_objects"] = []
    state["verification"] = {}
    state["results"] = {}
    state["current_item_id"] = None
    state["item"] = None
    state["items_initialized"] = False
    # Attach a run UUID for tracing
    state["run_uuid"] = state.get("run_uuid") or uuid.uuid4().hex

    state.setdefault("events", []).append({"node": "intake", "ok": True})
    return state
