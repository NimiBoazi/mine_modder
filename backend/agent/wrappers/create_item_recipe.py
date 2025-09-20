from __future__ import annotations

from typing import Dict, Any, Optional, List
from pathlib import Path
import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda

from backend.agent.wrappers.storage import STORAGE as storage
from backend.agent.providers.paths import (
    mod_recipe_provider_file,
    item_template_file,
)
from backend.agent.wrappers.utils import (
    insert_before_anchor,
)

# Anchors in ModRecipeProvider.java
EXTRA_IMPORTS_END = "// ==MM:EXTRA_IMPORTS_END=="
RECIPE_DEFS_END = "// ==MM:RECIPE_DEFINITIONS_END=="


def _strip_md_fences(s: str) -> str:
    s = str(s).strip()
    if s.startswith("```"):
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def make_create_item_recipe(model: BaseChatModel) -> Runnable[Dict[str, Any], Dict[str, Any]]:
    """Ask GPT-5 for recipe code sections and update ModRecipeProvider.java.

    The model must return a JSON object with keys:
      - extra_imports: string with one or more import lines
      - recipe_definitions: string with one or more recipe builder calls

    Input payload:
      - item_schema: Dict (must include item_id, registry_constant, description)
      - mod_context: {base_package: str}
      - framework: str (e.g., "neoforge") for template resolution
      - workspace: str (path to workspace root)
      - items_index: Optional[Dict[str, Dict]] (to derive previously created item_ids)

    Side-effect: updates ModRecipeProvider.java in place.
    Output: {"updated_files": [<path>]} when modified; otherwise empty list.
    """

    def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
        print("[ENTER] wrapper:create_item_recipe")

        item_schema: Dict[str, Any] = dict(payload.get("item_schema") or {})
        mod_context: Dict[str, Any] = dict(payload.get("mod_context") or {})
        framework = (payload.get("framework") or "").strip().lower()
        ws_str = payload.get("workspace") or ""
        items_index: Dict[str, Any] = dict(payload.get("items_index") or {})

        if not item_schema or not mod_context or not framework or not ws_str:
            raise ValueError("create_item_recipe requires item_schema, mod_context, framework, and workspace")

        base_package = (mod_context.get("base_package") or "").strip()
        if not base_package:
            raise ValueError("mod_context.base_package is required")

        item_id = (item_schema.get("item_id") or "").strip()
        registry_constant = (item_schema.get("registry_constant") or "").strip()
        description = (item_schema.get("description") or "").strip()
        if not item_id or not registry_constant:
            raise ValueError("item_schema.item_id and item_schema.registry_constant are required")

        prev_item_ids: List[str] = []
        try:
            prev_item_ids = [str(k) for k in items_index.keys() if str(k) != item_id]
        except Exception:
            prev_item_ids = []

        # Load the ModRecipeProvider template (for context to the LLM)
        recipe_tpl_path = item_template_file(framework, "datagen/ModRecipeProvider.java.tmpl")
        recipe_tpl_text = storage.read_text(recipe_tpl_path) if storage.exists(recipe_tpl_path) else ""

        # Build the LLM prompt
        system = SystemMessage(content=(
            "You are an expert NeoForge Minecraft mod developer.\n"
            "Task: Generate recipe code for a ModRecipeProvider.java file.\n"
            "Return ONLY a JSON object with two string fields: extra_imports and recipe_definitions.\n"
            "Do not wrap in markdown fences unless the JSON requires escaping.\n"
            "The extra_imports must be valid Java import lines (if any).\n"
            "The recipe_definitions should be the Java builder calls added to the provider (e.g., ShapedRecipeBuilder, ShapelessRecipeBuilder, Smelting, etc.).\n"
        ))
        user = HumanMessage(content=(
            "Use the following inputs to craft appropriate recipes for the item.\n\n"
            f"ITEM_ID = {item_id}\n"
            f"REGISTRY_CONSTANT = {registry_constant}\n"
            f"DESCRIPTION = {description}\n"
            f"OTHER_ITEM_IDS = {prev_item_ids}\n\n"
            "ModRecipeProvider TEMPLATE (for context; observe the anchors):\n"
            + recipe_tpl_text + "\n\n"
            "Anchors to target:\n"
            "- EXTRA IMPORTS: // ==MM:EXTRA_IMPORTS_END==\n"
            "- RECIPE DEFINITIONS: // ==MM:RECIPE_DEFINITIONS_END==\n\n"
            "Return JSON: {\"extra_imports\": \"...\", \"recipe_definitions\": \"...\"}"
        ))

        resp = model.invoke([system, user])
        raw = resp.content if hasattr(resp, "content") else str(resp)
        raw = _strip_md_fences(raw)

        # Parse JSON response
        extra_imports = ""
        recipe_defs = ""
        try:
            data = json.loads(raw)
            extra_imports = str(data.get("extra_imports") or "").strip()
            recipe_defs = str(data.get("recipe_definitions") or "").strip()
        except Exception:
            # If not valid JSON, attempt to recover by simple heuristics (optional)
            # Here we just keep both as empty to avoid inserting garbage
            extra_imports = ""
            recipe_defs = ""

        # Load target file
        ws = Path(ws_str)
        target_path = mod_recipe_provider_file(ws, base_package)
        if not storage.exists(target_path):
            raise FileNotFoundError(f"ModRecipeProvider.java not found at {target_path}")
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

        # Insert recipe definitions if any and not already present
        if recipe_defs:
            block = recipe_defs.rstrip("\n")
            if block not in updated:
                if RECIPE_DEFS_END not in updated:
                    raise RuntimeError(f"Anchor not found: {RECIPE_DEFS_END}")
                updated = insert_before_anchor(updated, RECIPE_DEFS_END, block)
                changed = True

        if changed and updated != src:
            storage.write_text(target_path, updated, encoding="utf-8")
            return {"updated_files": [str(target_path)]}
        return {"updated_files": []}

    return RunnableLambda(lambda x: _run(x))

