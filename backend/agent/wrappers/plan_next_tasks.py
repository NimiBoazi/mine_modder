from __future__ import annotations

from typing import Dict, Any, List
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
import json

# Default allowed task types (can be overridden per-call via payload['available_tasks'])
ALLOWED_TASK_TYPES = [
    "add_custom_item",
]

def make_next_tasks_planner(model: BaseChatModel) -> Runnable[Dict[str, Any], Dict[str, Any]]:
    """
    Returns a Runnable that takes:
      {
        "user_prompt": str,                  # the user's mod description/request
        "available_tasks": [str],            # optional override of allowed task types
        "max_tasks": int (optional)          # default: 5
      }

    and returns STRICT JSON:
      {
        "tasks": [ {"type": str, "title": str, "description": str, "params": dict} ]
      }

    Notes:
    - If `available_tasks` is provided, it replaces ALLOWED_TASK_TYPES for this call.
    - Planner must use ONLY allowed task types.
    """
    system = SystemMessage(content=(
        "You are a task planner for a Minecraft mod agent.\n"
        "Your job: given the USER PROMPT and a list of ALLOWED TASK TYPES, plan executable tasks and list them in an order that advances the mod.\n"
        "Do NOT invent new task types; only use the allowed ones.\n"
        "The tasks will be executed iteratively; each task's output may inform subsequent tasks, so order matters.\n\n"
        "Task type explanations (what each does):\n"
        "- add_custom_item: Complete workflow to add a new item to the mod. Steps:\n"
        "  1) Extract item schema: infer an item specification from the user's request (id, display name, class name, model type, creative tab, tags, tooltip, recipe hints).\n"
        "  2) Generate custom item class: create the Java class that implements the item's behavior.\n"
        "  3) Register the item: add a registration entry in the ModItems class so the game recognizes the item.\n"
        "  4) Creative tab: add the item to the chosen creative inventory tab so it appears in creative mode.\n"
        "  5) Model data generator: update the item model data generator (ModItemModelProvider) so data generation emits the item's model JSON (e.g., basicItem or handheld).\n"
        "  6) Tags: update the item tag data generator (ModItemTagProvider) so the item belongs to relevant tags (e.g., minecraft:ingredients).\n"
        "  7) Recipes: update the recipe data generator (ModRecipeProvider) with crafting/smelting definitions so players can obtain the item.\n"
        "  8) Language entries: add localization keys for the item name and tooltip (e.g., in en_us.json).\n"
        "  9) Texture: place or generate a 16x16 item texture under assets/<modid>/textures/item/.\n"
        "  10) Persist schema: store the item's schema in agent state for future steps and cross-references.\n\n"
        "Return STRICT JSON with the schema:\n"
        "{\n"
        "  \"tasks\": [\n"
        "    {\n"
        "      \"type\": string,       // MUST be one of the allowed types\n"
        "      \"title\": string,      // short actionable label\n"
        "      \"description\": string,// optional longer explanation (use the explanations above)\n"
        "      \"params\": object      // optional parameters for the executor\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Only use allowed task types.\n"
        "- Prefer a minimal set of concrete tasks the agent can execute now.\n"
        "- If nothing is actionable with the allowed types, return an empty tasks array.\n"
        "- Output MUST be valid JSON and nothing else.\n"
    ))

    def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
        print("[ENTER] wrapper:plan_next_tasks")

        user_prompt = payload.get("user_prompt", "") or ""
        if not user_prompt.strip():
            raise ValueError("Planner requires non-empty 'user_prompt'.")

        allowed_types: List[str] = list(payload.get("available_tasks") or ALLOWED_TASK_TYPES)
        max_tasks = int(payload.get("max_tasks", 5))

        msg = HumanMessage(content=(
            "User prompt:\n" + str(user_prompt) + "\n\n"
            "Allowed task types (use ONLY these):\n" + json.dumps(allowed_types, ensure_ascii=False) + "\n\n"
            f"Plan up to {max_tasks} executable tasks that progress the mod described above.\n"
            "Respond with STRICT JSON matching the specified schema."
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
            t.setdefault("title", t.get("type", "task"))
            t.setdefault("description", "")
            t.setdefault("params", {})

        # Trim to max_tasks (allow 0 if planner returned none)
        if max_tasks >= 0:
            data["tasks"] = data["tasks"][: max(0, max_tasks)]

        return data

    return RunnableLambda(lambda x: _run(x))
