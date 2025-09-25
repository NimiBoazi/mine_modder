from __future__ import annotations

from backend.agent.state import AgentState
from langgraph.types import interrupt


def await_user_input(state: AgentState) -> AgentState:
    """Gate node that represents waiting for a user's follow-up input.
    - If no followup is present, mark awaiting_user_input=True and return.
    - If present, normalize to followup_user_input, clear awaiting flag and return.
    """
    print("[ENTER] node:await_user_input")
    # Accept either followup_message (preferred) or followup_user_input (legacy)
    raw_followup = (state.get("followup_message") or state.get("followup_user_input") or "")
    followup = raw_followup.strip()
    if followup:
        # Normalize to followup_user_input and clear the alias to avoid ambiguity
        state["followup_user_input"] = followup
        state["followup_message"] = ""
        state["awaiting_user_input"] = False
        state.setdefault("events", []).append({"node": "await_user_input", "ok": True, "status": "received_input"})
    else:
        state["awaiting_user_input"] = True
        state.setdefault("events", []).append({"node": "await_user_input", "ok": True, "status": "awaiting"})
        # Interrupt here to pause the graph until a follow-up message arrives
        return interrupt("await_user_input")
    return state

