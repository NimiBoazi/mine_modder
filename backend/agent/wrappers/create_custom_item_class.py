from __future__ import annotations

from typing import Dict, Any, List
from pathlib import Path
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda

from backend.agent.wrappers.storage import STORAGE as storage
from backend.schemas.itemSchema import ItemSchema
from backend.agent.providers.paths import (
    custom_item_class_template,
    custom_item_class_example_template,
    custom_item_class_tooltip_template,
)
from backend.agent.wrappers.utils import (
    render_placeholders as _render_placeholders,
    insert_before_anchor as _insert_before_anchor,
    load_optional as _load_optional,
)

# Constants for anchors in the example template / generated file
METHODS_END_ANCHOR = "// ===== END INSERT ANCHOR: METHODS ====="

def make_create_custom_item_class(model: BaseChatModel) -> Runnable[Dict[str, Any], Dict[str, Any]]:
    """Return a Runnable that generates and writes the custom item class Java file.

    Input payload:
      - item_schema: Dict with at least item_id, item_class_name, description
      - mod_context: {base_package, modid}
      - framework: str (e.g., "neoforge") used to resolve template directory via paths.py
      - workspace: optional str path to workspace root for loading context files
      - items_index: optional dict of item_id -> item_schema (to resolve dependency source paths)

    Side-effect: writes <base_package>/item/custom/<MainClassName>.java to workspace.
    Output: {"updated_files": [<path>]} for diagnostics.
    """

    system = SystemMessage(content=(
        "You are an expert Minecraft 1.21 (NeoForge) mod developer.\n"
        "Your task: produce a full custom Item Java class, starting from an example template,\n"
        "by replacing placeholders and writing custom logic ONLY inside clearly-marked anchors.\n"
        "Make sure that all methods are compatible for Minecraft 1.21\n"
        "Make sure there are not naming conflicts with other classes or the mod_id\n"
        "Do not add or modify code outside anchors except to replace placeholders like package, imports, class name.\n"
        "Do Not add Tooltip methods\n"
        "Return ONLY the final Java file content (no markdown)."
    ))

    def _run(payload: Dict[str, Any]) -> str:
        print("[ENTER] wrapper:create_custom_item_class")

        item_schema: Dict[str, Any] = dict(payload.get("item_schema") or {})
        mod_context: Dict[str, Any] = dict(payload.get("mod_context") or {})
        base_package = mod_context.get("base_package", "").strip()
        modid = mod_context.get("modid", "").strip()
        item_id = item_schema.get("item_id", "").strip()
        if not item_schema or not base_package or not modid:
            raise ValueError("create_custom_item_class requires item_schema and mod_context with base_package, modid")

        item_class_name: str = item_schema.get("item_class_name")
        description: str = (item_schema.get("description") or "").strip()

        # Resolve template via paths.py
        framework = (payload.get("framework") or "").strip().lower()
        if not framework:
            raise ValueError("create_custom_item_class requires 'framework' in payload")
        # The fillable template to be completed by the LLM
        template_path = custom_item_class_template(framework)
        template_text = storage.read_text(template_path)
        # An example of a filled-out class used as guidance only
        example_path = custom_item_class_example_template(framework)
        example_text = storage.read_text(example_path) if storage.exists(example_path) else ""

        # Load optional dependency class files referred by the schema
        wants: List[str] = []
        for key in ("needs_object_files_for_context", "object_ids_for_context"):
            v = item_schema.get(key)
            if isinstance(v, list):
                wants = [str(x) for x in v if isinstance(x, (str, bytes))]
                break
        dep_blobs: List[str] = []
        ws_str = payload.get("workspace")
        items_index: Dict[str, Any] = payload.get("items_index") or {}
        ws = Path(ws_str) if isinstance(ws_str, str) and ws_str else None
        if ws is not None and wants:
            for obj_id in wants:
                other_schema = items_index.get(obj_id)
                if not isinstance(other_schema, dict):
                    continue
                try:
                    other_icn = (other_schema.get("item_class_name") or "").strip()
                    if other_icn:
                        dep_rel = ItemSchema.custom_class_relpath_for(base_package, other_icn)
                        dep_path = ws / dep_rel
                        src = _load_optional(dep_path)
                        if src:
                            dep_blobs.append(f"// --- BEGIN CONTEXT: {obj_id} ---\n" + src + "\n// --- END CONTEXT: {obj_id} ---\n")
                except Exception:
                    continue

        # Build user message
        user = HumanMessage(content=(
            "Fill the placeholders in the CUSTOM ITEM CLASS TEMPLATE using BASE_PACKAGE, ITEM_CLASS_NAME, and MOD_ID.\n"
            "Implement the item's behavior in the INSERT ANCHOR regions based on the DESCRIPTION below.\n"
            "Do not modify code outside anchors except to replace placeholders.\n\n"
            f"BASE_PACKAGE = {base_package}\n"
            f"ITEM_CLASS_NAME = {item_class_name}\n"
            f"MOD_ID = {modid}\n"
            f"ITEM_ID = {item_id}\n"
            f"DESCRIPTION = {description}\n\n"
            "CUSTOM_ITEM_CLASS_TEMPLATE (to fill):\n" + template_text + "\n\n" +
            ("FILLED_CLASS_EXAMPLE (for guidance only):\n" + example_text + "\n\n" if example_text else "") +
            ("DEPENDENCY_FILES:\n" + "\n\n".join(dep_blobs) if dep_blobs else "")
        ))

        resp = model.invoke([system, user])
        out = resp.content if hasattr(resp, "content") else str(resp)
        if not isinstance(out, str) or not out.strip():
            raise ValueError("LLM returned empty content for custom item class")

        # Post-process: ensure tooltip method insertion above METHODS_END anchor
        tooltip_tpl_path = custom_item_class_tooltip_template(framework)
        tooltip_tpl = storage.read_text(tooltip_tpl_path)
        tooltip_code = _render_placeholders(tooltip_tpl, {"modid": modid, "item_id": item_id})
        out2 = _insert_before_anchor(out, METHODS_END_ANCHOR, tooltip_code)

        # Write to target path inside the workspace
        if ws is None:
            raise ValueError("create_custom_item_class requires 'workspace' to write output file")
        target_path = ws / ItemSchema.custom_class_relpath_for(base_package, item_class_name)
        storage.ensure_dir(target_path.parent)
        storage.write_text(target_path, out2, encoding="utf-8")
        return {"updated_files": [str(target_path)]}

    return RunnableLambda(lambda x: _run(x))

