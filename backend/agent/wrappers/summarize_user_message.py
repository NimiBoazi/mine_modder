from __future__ import annotations

from typing import Dict, Any, List
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
import json


def make_summarize_user_message(model: BaseChatModel) -> Runnable[Dict[str, Any], str]:
    """
    Build a Runnable that takes a payload with mod + items + events and returns a
    concise, friendly user-facing summary string (plain text, no code fences).

    Expected input shape (keys optional but recommended):
      {
        "mod_name": str,
        "mod_description": str,
        "modid": str,
        "items": [
          {
            "item_id": str,
            "display_name": str,
            "description": str,
            "recipe_ingredients": list[str] | None,
            "is_consumable": bool | None,
            "tags": list[str] | None,
            "tooltip_text": str | None,
          }, ...
        ],
        "events": list[dict]  # will be provided for additional context
      }
    """

    system = SystemMessage(content=(
        "You are a helpful customer-support style assistant for a Minecraft modding app. "
        "Given structured JSON describing the final mod state and created items, "
        "write a concise, warm summary for the user.\n\n"
        "Requirements:\n"
        "- Return PLAIN TEXT only (no JSON, no markdown fences).\n"
        "- First line: a friendly one-liner naming the mod.\n"
        "- Then a short paragraph describing the mod.\n"
        "- Then bullet points for each created item with: display name, what it does, recipe (if present), and any special effects/consumable notes.\n"
        "- Keep tone positive and service oriented; avoid technical jargon.\n"
        "- Be accurate; if data is missing, omit that part.\n"
    ))

    def _run(payload: Dict[str, Any]) -> str:
        mod_name = str(payload.get("mod_name") or "Your Mod").strip()
        mod_desc = str(payload.get("mod_description") or "").strip()
        modid = str(payload.get("modid") or "").strip()
        items = payload.get("items") or []
        events = payload.get("events") or []  # Not required to include verbatim; used as context

        # Prepare compact JSON context for the model
        ctx = {
            "mod": {
                "name": mod_name,
                "id": modid or None,
                "description": mod_desc or None,
            },
            "items": [
                {
                    "item_id": i.get("item_id"),
                    "display_name": i.get("display_name"),
                    "description": i.get("description"),
                    "recipe_ingredients": i.get("recipe_ingredients"),
                    "is_consumable": i.get("is_consumable"),
                    "tags": i.get("tags"),
                    "tooltip_text": i.get("tooltip_text"),
                }
                for i in items if isinstance(i, dict)
            ],
            # Provide a minimal projection of events (node + ok) to help with phrasing if needed
            "events": [
                {k: ev.get(k) for k in ("node", "ok", "action", "task_id", "reason") if k in ev}
                for ev in events if isinstance(ev, dict)
            ],
        }

        user = HumanMessage(content=(
            "Here is the final mod data in JSON. Please produce the final user-facing summary as plain text.\n\n"
            + json.dumps(ctx, ensure_ascii=False, indent=2)
        ))

        resp = model.invoke([system, user])
        text = resp.content if hasattr(resp, "content") else str(resp)
        return str(text).strip()

    return RunnableLambda(lambda x: _run(x))

