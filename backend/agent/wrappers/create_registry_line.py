from __future__ import annotations

from typing import Dict, Any
from pathlib import Path
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda

from backend.agent.wrappers.storage import STORAGE as storage
from backend.agent.providers.paths import (
    mod_items_file,
    item_template_file,
)
from backend.agent.wrappers.utils import (
    insert_between_anchors_text,
)

# Anchors in ModItems.java
REG_BEGIN = "// ==MM:ITEM_REGISTRATIONS_BEGIN=="
REG_END = "// ==MM:ITEM_REGISTRATIONS_END=="
IMPORT_BEGIN = "// ==MM:EXTRA_IMPORTS_BEGIN=="
IMPORT_END = "// ==MM:EXTRA_IMPORTS_END=="


def _strip_fences(s: str) -> str:
    s = str(s).strip()
    if s.startswith("```"):
        # remove first fenced line
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()


def make_create_registry_line(model: BaseChatModel) -> Runnable[Dict[str, Any], Dict[str, Any]]:
    """Build a Runnable that asks the LLM for the registry line, then returns the updated ModItems.java content.

    Input payload:
      - item_schema: Dict (must include item_id, registry_constant, item_class_name, description)
      - mod_context: {base_package: str, modid: str}
      - framework: str (e.g., "neoforge")
      - workspace: str (path to workspace root)

    Output (files bundle):
      { "files": [ {"path": <abs_path_to_ModItems.java>, "content": <new_content>} ] }
    """

    def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
        print("[ENTER] wrapper:create_registry_line")

        item_schema: Dict[str, Any] = dict(payload.get("item_schema") or {})
        mod_context: Dict[str, Any] = dict(payload.get("mod_context") or {})
        framework = (payload.get("framework") or "").strip().lower()
        ws_str = payload.get("workspace") or ""
        if not item_schema or not mod_context or not framework or not ws_str:
            raise ValueError("create_registry_line requires item_schema, mod_context, framework, and workspace")

        base_package = mod_context.get("base_package", "").strip()
        if not base_package:
            raise ValueError("mod_context.base_package is required")

        ws = Path(ws_str)
        mod_items_path = mod_items_file(ws, base_package)
        if not storage.exists(mod_items_path):
            raise FileNotFoundError(f"ModItems.java not found at {mod_items_path}")

        # Build the LLM prompt with the required fields and example for guidance
        example_path = item_template_file(framework, "mod_items_registration_line_example.java.tmpl")
        example_text = storage.read_text(example_path) if storage.exists(example_path) else ""

        registry_constant = item_schema.get("registry_constant", "").strip()
        item_id = item_schema.get("item_id", "").strip()
        item_class_name = item_schema.get("item_class_name", "").strip()
        description = (item_schema.get("description") or "").strip()

        system = SystemMessage(content=(
            "You are an expert NeoForge Minecraft mod developer.\n"
            "Task: produce exactly one Java registry line for the ModItems class.\n"
            "Return ONLY the single Java line (no markdown, no comments around it)."
        ))
        user = HumanMessage(content=(
            "Create the item registration line for the ModItems class. Use the inputs below.\n\n"
            f"REGISTRY_CONSTANT = {registry_constant}\n"
            f"ITEM_ID = {item_id}\n"
            f"ITEM_CLASS_NAME = {item_class_name}\n"
            f"DESCRIPTION = {description}\n\n"
            + ("EXAMPLE (for guidance only):\n" + example_text if example_text else "")
        ))

        resp = model.invoke([system, user])
        reg_line = resp.content if hasattr(resp, "content") else str(resp)
        reg_line = _strip_fences(reg_line)
        reg_line = reg_line.strip()
        if not reg_line:
            raise ValueError("LLM returned empty registry line")

        # Load current ModItems.java, insert registry line and import, then write if changed
        src = storage.read_text(mod_items_path, encoding="utf-8", errors="ignore")
        updated = insert_between_anchors_text(src, REG_BEGIN, REG_END, reg_line)
        import_line = f"import {base_package}.item.custom.{item_class_name};"
        if import_line not in updated:
            updated = insert_between_anchors_text(updated, IMPORT_BEGIN, IMPORT_END, import_line)
        if updated != src:
            storage.write_text(mod_items_path, updated, encoding="utf-8")
        return {"updated_files": [str(mod_items_path)]}

    return RunnableLambda(lambda x: _run(x))

