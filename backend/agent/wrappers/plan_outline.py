from __future__ import annotations

from typing import Dict, Any
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
import json


def make_high_level_outline_wrapper(model: BaseChatModel) -> Runnable[Dict[str, str], Dict[str, Any]]:
    """
    Returns a Runnable that takes {"user_prompt": str} and returns a structured outline:
      {
        "project_summary": str,
        "milestones": [
          {"id": str, "title": str, "objective": str, "deliverables": [str, ...]}
        ]
      }
    """
    system = SystemMessage(content=(
        "You are a senior software planner for a Minecraft mod project.\n"
        "Produce a concise high-level outline with major milestones to complete the project.\n"
        "Creating a single item should be considered a single milestone.\n"
        "Return STRICT JSON only (no code fences, no extra text).\n\n"
        "Schema:\n"
        "{\n"
        "  \"project_summary\": string,\n"
        "  \"milestones\": [\n"
        "    {\n"
        "      \"id\": string,  // short identifier like M1, M2\n"
        "      \"title\": string,\n"
        "      \"objective\": string,\n"
        "      \"deliverables\": [string]\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules: keep it focused; 3-6 milestones; avoid implementation details but keep details describing the milestone."
    ))

    def _run(payload: Dict[str, str]) -> Dict[str, Any]:
        user_prompt = payload.get("user_prompt", "").strip()
        msg = HumanMessage(content=(
            "User prompt describing the desired Minecraft mod:\n\n" + user_prompt + "\n\n"
            "Respond with JSON matching the specified schema."
        ))
        resp = model.invoke([system, msg])
        text = resp.content if hasattr(resp, "content") else str(resp)
        data = json.loads(text)
        # Minimal validation
        if not isinstance(data, dict):
            raise ValueError("Outline must be a JSON object")
        if "milestones" not in data or not isinstance(data["milestones"], list):
            raise ValueError("Outline must contain a 'milestones' array")
        # Ensure milestones have an explicit order index based on list order (1-based)
        try:
            for i, m in enumerate(data.get("milestones", [])):
                if isinstance(m, dict) and "order" not in m:
                    m["order"] = i + 1
        except Exception:
            pass
        return data

    return RunnableLambda(lambda x: _run(x))

