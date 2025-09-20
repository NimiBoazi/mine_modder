from __future__ import annotations

from typing import Dict, Any
from pathlib import Path
from langchain_core.runnables import Runnable, RunnableLambda

from backend.agent.wrappers.storage import STORAGE as storage
from backend.agent.providers.paths import (
    java_src_root,
    java_base_package_dir,
    item_creative_tab_accept_line_template,
)
from backend.agent.wrappers.utils import (
    render_placeholders,
    insert_before_anchor,
)



def make_update_creative_tab_item() -> Runnable[Dict[str, Any], Dict[str, Any]]:
    """Return a Runnable that inserts the item accept line into the main class.

    It fills the item_creative_tab_accept_line.java.tmpl with the item's registry_constant
    and inserts it just above the dynamic anchor "// =={creative_tab_key}_ACCEPT_END==".

    Input payload:
      - item_schema: Dict (must include registry_constant, creative_tab_key)
      - mod_context: {base_package: str, modid: str}
      - framework: str (e.g., "neoforge") for template resolution
      - workspace: str (path to workspace root)

    Side-effect: updates the Java file containing the dynamic creative-tab anchor in place.
    Output: {"updated_files": [<path>]} for diagnostics.
    """

    def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
        print("[ENTER] wrapper:update_creative_tab_item")

        item_schema: Dict[str, Any] = dict(payload.get("item_schema") or {})
        mod_context: Dict[str, Any] = dict(payload.get("mod_context") or {})
        framework = (payload.get("framework") or "").strip().lower()
        ws_str = payload.get("workspace") or ""
        if not item_schema or not mod_context or not framework or not ws_str:
            raise ValueError("update_creative_tab_item requires item_schema, mod_context, framework, and workspace")

        base_package = (mod_context.get("base_package") or "").strip()
        if not base_package:
            raise ValueError("mod_context.base_package is required")

        registry_constant = (item_schema.get("registry_constant") or "").strip()
        if not registry_constant:
            raise ValueError("item_schema.registry_constant is required")

        ws = Path(ws_str)

        # Load template and render
        tpl_path = item_creative_tab_accept_line_template(framework)
        tpl = storage.read_text(tpl_path)
        line = render_placeholders(tpl, {"registry_constant": registry_constant}).rstrip("\n")

        # Build dynamic END anchor from creative_tab_key
        creative_tab_key = (item_schema.get("creative_tab_key") or "").strip()
        if not creative_tab_key:
            raise ValueError("item_schema.creative_tab_key is required for creative tab insertion")
        end_anchor = f"// =={creative_tab_key}_ACCEPT_END=="

        # Search for the Java file containing the anchor, preferring within the base package
        search_dirs = []
        try:
            bp_dir = java_base_package_dir(ws, base_package)
            if storage.exists(bp_dir):
                search_dirs.append(bp_dir)
        except Exception:
            pass
        root_dir = java_src_root(ws)
        if storage.exists(root_dir) and (not search_dirs or root_dir != search_dirs[0]):
            search_dirs.append(root_dir)

        target_path = None
        target_src = None
        for d in search_dirs:
            for p in storage.rglob(d, "*.java"):
                src = storage.read_text(p, encoding="utf-8", errors="ignore")
                if end_anchor in src:
                    target_path = p
                    target_src = src
                    break
            if target_path is not None:
                break

        if target_path is None or target_src is None:
            raise RuntimeError(f"Creative tab anchor not found under {search_dirs}: {end_anchor}")

        updated = insert_before_anchor(target_src, end_anchor, line)
        if updated != target_src:
            storage.write_text(target_path, updated, encoding="utf-8")
        return {"updated_files": [str(target_path)]}

    return RunnableLambda(lambda x: _run(x))

