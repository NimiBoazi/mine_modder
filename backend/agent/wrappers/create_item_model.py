from __future__ import annotations

from typing import Dict, Any
from pathlib import Path
from langchain_core.runnables import Runnable, RunnableLambda

from backend.agent.wrappers.storage import STORAGE as storage
from backend.agent.providers.paths import (
    mod_item_model_provider_file,
    item_model_line_template,
)
from backend.agent.wrappers.utils import (
    render_placeholders,
    insert_before_anchor,
)

# Anchor in ModItemModelProvider.java
MODEL_REG_END = "// ==MM:ITEM_MODEL_REGISTRATIONS_END=="


def make_create_item_model() -> Runnable[Dict[str, Any], Dict[str, Any]]:
    """Return a Runnable that inserts an item model registration line.

    Deterministically fills item_model_line.java.tmpl with {model_type, registry_constant}
    from item_schema and inserts it just above MODEL_REG_END in ModItemModelProvider.java.

    Input payload:
      - item_schema: Dict (must include model_type, registry_constant)
      - mod_context: {base_package: str, modid: str}
      - framework: str (e.g., "neoforge") for template resolution
      - workspace: str (path to workspace root)

    Side-effect: updates ModItemModelProvider.java in place.
    Output: {"updated_files": [<path>]} for diagnostics.
    """

    def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
        print("[ENTER] wrapper:create_item_model")

        item_schema: Dict[str, Any] = dict(payload.get("item_schema") or {})
        mod_context: Dict[str, Any] = dict(payload.get("mod_context") or {})
        framework = (payload.get("framework") or "").strip().lower()
        ws_str = payload.get("workspace") or ""
        if not item_schema or not mod_context or not framework or not ws_str:
            raise ValueError("create_item_model requires item_schema, mod_context, framework, and workspace")

        base_package = (mod_context.get("base_package") or "").strip()
        if not base_package:
            raise ValueError("mod_context.base_package is required")

        model_type = (item_schema.get("model_type") or "").strip()
        registry_constant = (item_schema.get("registry_constant") or "").strip()
        if not model_type or not registry_constant:
            raise ValueError("item_schema.model_type and item_schema.registry_constant are required")

        ws = Path(ws_str)
        target_path = mod_item_model_provider_file(ws, base_package)
        if not storage.exists(target_path):
            raise FileNotFoundError(f"ModItemModelProvider not found at {target_path}")

        # Render the single line from template
        tpl_path = item_model_line_template(framework)
        tpl = storage.read_text(tpl_path)
        line = render_placeholders(tpl, {
            "model_type": model_type,
            "registry_constant": registry_constant,
        }).rstrip("\n")

        # Insert above END anchor and write if changed
        src = storage.read_text(target_path, encoding="utf-8", errors="ignore")
        if MODEL_REG_END not in src:
            raise RuntimeError(f"Model provider END anchor not found: {MODEL_REG_END}")
        updated = insert_before_anchor(src, MODEL_REG_END, line)
        if updated != src:
            storage.write_text(target_path, updated, encoding="utf-8")
        return {"updated_files": [str(target_path)]}

    return RunnableLambda(lambda x: _run(x))

