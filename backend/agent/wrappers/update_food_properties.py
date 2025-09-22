from __future__ import annotations

from typing import Dict, Any
from pathlib import Path
import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda

from backend.agent.wrappers.storage import STORAGE as storage
from backend.agent.providers.paths import (
    mod_food_properties_file,
    item_template_file,
)
from backend.agent.wrappers.utils import insert_before_anchor

# Anchors in ModFoodProperties.java
EXTRA_IMPORTS_END = "// ==MM:EXTRA_IMPORTS_END=="
FOOD_PROPERTIES_END = "// ==MM:FOOD_PROPERTIES_END=="


def _strip_md_fences(s: str) -> str:
    s = str(s).strip()
    if s.startswith("```"):
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def make_update_food_properties(model: BaseChatModel) -> Runnable[Dict[str, Any], Dict[str, Any]]:
    """Ask GPT-5 for FoodProperties code sections and update ModFoodProperties.java.

    The model must return a JSON object with keys:
      - extra_imports: string with one or more import lines (optional)
      - food_properties: string with one or more static FoodProperties definitions

    Input payload:
      - item_schema: Dict (must include item_id, registry_constant, description, item_class_name)
      - mod_context: {base_package: str}
      - framework: str (e.g., "neoforge") for template resolution
      - workspace: str (path to workspace root)

    Side-effect: updates ModFoodProperties.java in place.
    Output: {"updated_files": [<path>]} when modified; otherwise empty list.
    """

    def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
        print("[ENTER] wrapper:update_food_properties")

        item_schema: Dict[str, Any] = dict(payload.get("item_schema") or {})
        mod_context: Dict[str, Any] = dict(payload.get("mod_context") or {})
        framework = (payload.get("framework") or "").strip().lower()
        ws_str = payload.get("workspace") or ""

        if not item_schema or not mod_context or not framework or not ws_str:
            raise ValueError("update_food_properties requires item_schema, mod_context, framework, and workspace")

        base_package = (mod_context.get("base_package") or "").strip()
        if not base_package:
            raise ValueError("mod_context.base_package is required")

        item_id = (item_schema.get("item_id") or "").strip()
        registry_constant = (item_schema.get("registry_constant") or "").strip()
        description = (item_schema.get("description") or "").strip()
        item_class_name = (item_schema.get("item_class_name") or "").strip()
        if not item_id or not registry_constant or not item_class_name:
            raise ValueError("item_schema.item_id, registry_constant, and item_class_name are required")

        # Load the ModFoodProperties template (for context to the LLM)
        tpl_path = item_template_file(framework, "ModFoodProperties.java.tmpl")
        tpl_text = storage.read_text(tpl_path) if storage.exists(tpl_path) else ""

        # Build the LLM prompt
        system = SystemMessage(content=(
            "You are an expert NeoForge Minecraft mod developer.\n"
            "Task: Generate FoodProperties constants for ModFoodProperties.java.\n"
            "Return ONLY a JSON object with two string fields: extra_imports and food_properties.\n"
            "The extra_imports must be valid Java import lines, if needed.\n"
            "The food_properties must define one or more public static final FoodProperties constants appropriate for the item.\n"
        ))
        user = HumanMessage(content=(
            "Create FoodProperties for a consumable item.\n\n"
            f"ITEM_ID = {item_id}\n"
            f"REGISTRY_CONSTANT = {registry_constant}  // use this as the constant name in ModFoodProperties\n"
            f"ITEM_CLASS_NAME = {item_class_name}\n"
            f"BASE_PACKAGE = {base_package}\n"
            f"DESCRIPTION = {description}\n\n"
            "ModFoodProperties TEMPLATE (for context; observe the anchors):\n"
            + tpl_text + "\n\n"
            "Anchors to target:\n"
            "- EXTRA IMPORTS: // ==MM:EXTRA_IMPORTS_END==\n"
            "- FOOD PROPERTIES: // ==MM:FOOD_PROPERTIES_END==\n\n"
            "Return JSON: {\"extra_imports\": \"...\", \"food_properties\": \"...\"}"
        ))

        resp = model.invoke([system, user])
        raw = resp.content if hasattr(resp, "content") else str(resp)
        raw = _strip_md_fences(raw)

        # Parse JSON response
        extra_imports = ""
        food_props = ""
        try:
            data = json.loads(raw)
            extra_imports = str(data.get("extra_imports") or "").strip()
            food_props = str(data.get("food_properties") or "").strip()
        except Exception:
            extra_imports = ""
            food_props = ""

        # Load target file
        ws = Path(ws_str)
        target_path = mod_food_properties_file(ws, base_package)
        if not storage.exists(target_path):
            raise FileNotFoundError(f"ModFoodProperties.java not found at {target_path}")
        src = storage.read_text(target_path, encoding="utf-8", errors="ignore")

        changed = False
        updated = src

        # Insert extra imports if any and not already present
        if extra_imports:
            block = extra_imports.rstrip("\n")
            if block not in updated:
                if EXTRA_IMPORTS_END not in updated:
                    raise RuntimeError(f"Anchor not found: {EXTRA_IMPORTS_END}")
                updated = insert_before_anchor(updated, EXTRA_IMPORTS_END, block)
                changed = True

        # Insert food properties if any and not already present
        if food_props:
            block = food_props.rstrip("\n")
            if block not in updated:
                if FOOD_PROPERTIES_END not in updated:
                    raise RuntimeError(f"Anchor not found: {FOOD_PROPERTIES_END}")
                updated = insert_before_anchor(updated, FOOD_PROPERTIES_END, block)
                changed = True

        if changed and updated != src:
            storage.write_text(target_path, updated, encoding="utf-8")
            return {"updated_files": [str(target_path)]}
        return {"updated_files": []}

    return RunnableLambda(lambda x: _run(x))

