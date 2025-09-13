from __future__ import annotations

from typing import Dict, Any
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
import json


# Hardcoded allowed task types for the short-term planner
ALLOWED_TASK_TYPES = [
    "add_custom_item",
]


def make_next_tasks_planner(model: BaseChatModel) -> Runnable[Dict[str, Any], Dict[str, Any]]:
    """
    Returns a Runnable that takes {
      "user_prompt": str,
      "outline": {...},
      "max_tasks": int (optional)
    } and returns {
      "milestone_title": str,
      "tasks": [ {"type": str, "title": str, "params": dict} ]
    }
    Notes:
    - Allowed task types are hardcoded in this module (ALLOWED_TASK_TYPES).
    - Params should be minimal and executable by the agent without further planning.
    """
    system = SystemMessage(content=(
        "You are a short-term task planner for a Minecraft mod agent.\n"
        "Given: the user prompt, a high-level outline, and a list of ALLOWED TASK TYPES.\n"
        "You are GIVEN the CURRENT milestone; split this milestone into executable tasks using ONLY the allowed types.\n"
        "Return STRICT JSON only.\n\n"
        "Output schema:\n"
        "{\n"
        "  \"milestone_title\": string,\n"
        "  \"tasks\": [\n"
        "    {\n"
        "      \"type\": string,  // MUST be one of the allowed types\n"
        "      \"title\": string,\n"
        "      \"description\": string  // an optional, more detailed description\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Only use allowed task types.\n"
    ))


    def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
        user_prompt = payload.get("user_prompt", "")
        outline = payload.get("outline") or {}
        current_milestone = payload.get("current_milestone")
        max_tasks = int(payload.get("max_tasks", 3))

        # Select milestone: by index (int) or id/title (str); fallback to first
        milestones = list(outline.get("milestones") or [])
        selected = None
        if isinstance(current_milestone, int) and 0 <= current_milestone < len(milestones):
            selected = milestones[current_milestone]
        elif isinstance(current_milestone, str):
            for m in milestones:
                if isinstance(m, dict) and (m.get("id") == current_milestone or m.get("title") == current_milestone):
                    selected = m
                    break
        if selected is None:
            selected = milestones[0] if milestones else {}

        allowed_types = list(ALLOWED_TASK_TYPES)
        msg = HumanMessage(content=(
            "User prompt:\n" + str(user_prompt) + "\n\n"
            "High-level outline (JSON):\n" + json.dumps(outline, ensure_ascii=False) + "\n\n"
            "CURRENT milestone (JSON):\n" + json.dumps(selected, ensure_ascii=False) + "\n\n"
            "Allowed task types (must choose from these ONLY):\n" + json.dumps(allowed_types) + "\n\n"
            f"Plan up to {max_tasks} tasks that the agent can execute now. Respond with the specified JSON."
        ))
        resp = model.invoke([system, msg])
        text = resp.content if hasattr(resp, "content") else str(resp)
        data = json.loads(text)
        # Basic validation
        if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
            raise ValueError("Planner must return {'tasks': [...]} JSON")
        for t in data["tasks"]:
            if t.get("type") not in allowed_types:
                raise ValueError(f"Task type not allowed: {t.get('type')}")
            t.setdefault("title", t["type"])
            t.setdefault("params", {})
        # Trim to max_tasks
        data["tasks"] = data["tasks"][: max(1, max_tasks)]
        return data

    return RunnableLambda(lambda x: _run(x))