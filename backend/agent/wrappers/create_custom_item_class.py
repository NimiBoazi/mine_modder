from __future__ import annotations

from typing import Dict, Any, List
from pathlib import Path
import json
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda

from backend.agent.wrappers.storage import STORAGE as storage
from backend.schemas.itemSchema import ItemSchema
from backend.agent.providers.paths import (
    custom_item_class_template,
    custom_item_class_tooltip_template,
    detect_neoforge_version,
    custom_item_class_example_template,
)
from backend.agent.wrappers.utils import (
    render_placeholders as _render_placeholders,
    insert_before_anchor as _insert_before_anchor,
    load_optional as _load_optional,
    normalize_import_block as _normalize_import_block,
)

# Constants for anchors in the template / generated file
EXTRA_IMPORTS_END = "// ==MM:EXTRA_IMPORTS_END=="
STATIC_FIELDS_END_ANCHOR = "// ===== END INSERT ANCHOR: STATIC_FIELDS ====="
CONSTRUCTOR_BODY_END_ANCHOR = "// ===== END INSERT ANCHOR: CONSTRUCTOR_BODY ====="
METHODS_END_ANCHOR = "// ===== END INSERT ANCHOR: METHODS ====="

def _strip_md_fences(s: str) -> str:
    s = str(s).strip()
    if s.startswith("```"):
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()

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

    SYSTEM_TEMPLATE = (
        "You are an expert Minecraft {mc_version} NeoForge mod developer.\n"
        "Task: Given a custom Item Java class template, generate ONLY the code to insert inside the anchor regions.\n"
        "Return ONLY a JSON object with string fields: extra_imports (optional), static_fields, constructor_body, methods.\n"
        "Each field may be an empty string if no code is needed for that section.\n"
        "Do not include markdown fences.\n"
        "Make sure that you use functions/methods that are compatable with Minecraft 1.21.1 and NeoForge, this is your most important rule.\n"
        "Make sure to override methods only if you are absolutly positive they exist\n"
        "Make sure to give the item class a unique name that is not already used by another item or file in the mod.\n"
        "Do not modify or repeat the template outside anchors; placeholders have already been filled deterministically.\n"
        "For Minecraft 1.21+, when creating a ResourceLocation, always use ResourceLocation.fromNamespaceAndPath(namespace, path) instead of the old constructor.\n"
        "Do not add Tooltip methods."
    )

    def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
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
        # Optional filled example class used as guidance only
        example_text = ""
        try:
            ex_path = custom_item_class_example_template(framework)
            if storage.exists(ex_path):
                example_text = storage.read_text(ex_path)
        except Exception:
            example_text = ""


        # Deterministically fill placeholders we can resolve before sending to the LLM
        ctx = {
            "base_package": base_package,
            "item_class_name": item_class_name,
            "modid": modid,
            "item_id": item_id,
        }
        filled_template_text = _render_placeholders(template_text, ctx)

        # Verify that required anchors exist in the pre-filled template to avoid silent appends
        required_anchors = [
            EXTRA_IMPORTS_END,
            STATIC_FIELDS_END_ANCHOR,
            CONSTRUCTOR_BODY_END_ANCHOR,
            METHODS_END_ANCHOR,
        ]
        for a in required_anchors:
            if a not in filled_template_text:
                raise RuntimeError(f"Anchor not found in custom item class template: {a}")

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

        # Build system prompt from template with mc_version and detected NeoForge version
        mc_version = (payload.get("mc_version") or "").strip()
        mv_text = mc_version if mc_version else "1.21+"
        nf_version = None
        try:
            if ws is not None:
                nf_version = detect_neoforge_version(ws)
        except Exception:
            nf_version = None
        neoforge_label = f"NeoForge {nf_version}" if nf_version else "NeoForge"
        system = SystemMessage(content=SYSTEM_TEMPLATE.format(mc_version=mv_text, neoforge_label=neoforge_label))

        # Build user message (placeholders already filled deterministically)
        user = HumanMessage(content=(
            "Use the CUSTOM ITEM CLASS TEMPLATE below to generate ONLY the code to insert inside the anchor regions.\n"
            "Implement the item's behavior ONLY inside the INSERT ANCHOR regions based on the DESCRIPTION.\n"
            "Do not modify code outside anchors (package/imports/class name/constructor signature are already set).\n"
            "IMPORTANT: Return ONLY JSON with keys: extra_imports (optional), static_fields, constructor_body, methods.\n"
            "Each field may be an empty string if no code is needed for that section.\n"
            "Do NOT emit template placeholders like {{base_package}}; all placeholders are already resolved.\n\n"
            f"BASE_PACKAGE = {base_package}\n"
            f"ITEM_CLASS_NAME = {item_class_name}\n"
            f"MOD_ID = {modid}\n"
            f"ITEM_ID = {item_id}\n"
            f"DESCRIPTION = {description}\n\n"
            "Anchors to target (insert BEFORE these lines):\n"
            f"- extra_imports -> {EXTRA_IMPORTS_END}\n"
            f"- static_fields -> {STATIC_FIELDS_END_ANCHOR}\n"
            f"- constructor_body -> {CONSTRUCTOR_BODY_END_ANCHOR}\n"
            f"- methods -> {METHODS_END_ANCHOR}\n\n"
            "CUSTOM_ITEM_CLASS_TEMPLATE:\n" + filled_template_text + "\n\n" +
            ("FILLED_CLASS_EXAMPLE (for guidance only):\n" + example_text + "\n\n" if example_text else "") +
            ("DEPENDENCY_FILES:\n" + "\n\n".join(dep_blobs) if dep_blobs else "") +
            "\nReturn JSON: {\"extra_imports\": \"...\", \"static_fields\": \"...\", \"constructor_body\": \"...\", \"methods\": \"...\"}"
        ))

        print(f"system prompt: {system}\n\nuser prompt: {user}")
        resp = model.invoke([system, user])
        print("response:", resp.content)
        raw = resp.content if hasattr(resp, "content") else str(resp)
        raw = _strip_md_fences(raw)

        try:
            data = json.loads(raw)
        except Exception as e:
            raise ValueError(f"LLM did not return valid JSON for custom item class anchors: {e}\nRAW=\n{raw}")

        # Extract required sections
        extra_imports = str(data.get("extra_imports") or "").strip()
        static_fields = str(data.get("static_fields") or "").strip()
        constructor_body = str(data.get("constructor_body") or "").strip()
        methods = str(data.get("methods") or "").strip()
        # Allow all sections to be empty; wrapper will still insert tooltip helper and write the file.

        # Start from the pre-filled template and insert sections before anchor markers
        updated = filled_template_text

        if extra_imports:
            block = _normalize_import_block(extra_imports)
            updated = _insert_before_anchor(updated, EXTRA_IMPORTS_END, block)

        if static_fields:
            block = static_fields.rstrip("\n")
            updated = _insert_before_anchor(updated, STATIC_FIELDS_END_ANCHOR, block)

        if constructor_body:
            block = constructor_body.rstrip("\n")
            updated = _insert_before_anchor(updated, CONSTRUCTOR_BODY_END_ANCHOR, block)

        if methods:
            block = methods.rstrip("\n")
            updated = _insert_before_anchor(updated, METHODS_END_ANCHOR, block)

        # Post-process: ensure tooltip method insertion above METHODS_END anchor
        tooltip_tpl_path = custom_item_class_tooltip_template(framework)
        tooltip_tpl = storage.read_text(tooltip_tpl_path)
        tooltip_code = _render_placeholders(tooltip_tpl, {"modid": modid, "item_id": item_id})
        updated = _insert_before_anchor(updated, METHODS_END_ANCHOR, tooltip_code)

        # Write to target path inside the workspace
        if ws is None:
            raise ValueError("create_custom_item_class requires 'workspace' to write output file")
        target_path = ws / ItemSchema.custom_class_relpath_for(base_package, item_class_name)
        storage.ensure_dir(target_path.parent)
        storage.write_text(target_path, updated, encoding="utf-8")
        return {"updated_files": [str(target_path)]}

    return RunnableLambda(lambda x: _run(x))

