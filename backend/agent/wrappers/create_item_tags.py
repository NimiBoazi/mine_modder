from __future__ import annotations

from typing import Dict, Any, List
from pathlib import Path
from langchain_core.runnables import Runnable, RunnableLambda

from backend.agent.wrappers.storage import STORAGE as storage
from backend.agent.providers.paths import (
    mod_item_tag_provider_file,
    item_tag_line_template,
)
from backend.agent.wrappers.utils import (
    render_placeholders,
    insert_before_anchor,
)

# Anchor in ModItemTagProvider.java
TAGS_END_ANCHOR = "// ==MM:ITEM_TAGS_END=="


def make_create_item_tags() -> Runnable[Dict[str, Any], Dict[str, Any]]:
    """Return a Runnable that inserts item tag lines into ModItemTagProvider.

    For each tag in item_schema["tags"], fills tag_line.java.tmpl with
    {tag, registry_constant} and inserts the line just above TAGS_END_ANCHOR.

    Input payload:
      - item_schema: Dict (must include tags: List[str], registry_constant: str)
      - mod_context: {base_package: str, modid: str}
      - framework: str (e.g., "neoforge") for template resolution
      - workspace: str (path to workspace root)

    Side-effect: updates ModItemTagProvider.java in place.
    Output: {"updated_files": [<path>]} for diagnostics.
    """

    def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
        print("[ENTER] wrapper:create_item_tags")

        item_schema: Dict[str, Any] = dict(payload.get("item_schema") or {})
        mod_context: Dict[str, Any] = dict(payload.get("mod_context") or {})
        framework = (payload.get("framework") or "").strip().lower()
        ws_str = payload.get("workspace") or ""
        if not mod_context or not framework or not ws_str:
            raise ValueError("create_item_tags requires mod_context, framework, and workspace")

        tags: List[str] = list(item_schema.get("tags") or [])
        registry_constant = (item_schema.get("registry_constant") or "").strip()
        if not registry_constant:
            raise ValueError("item_schema.registry_constant is required")
        if not tags:
            # Nothing to do; return empty update
            return {"updated_files": []}

        base_package = (mod_context.get("base_package") or "").strip()
        if not base_package:
            raise ValueError("mod_context.base_package is required")

        ws = Path(ws_str)
        target_path = mod_item_tag_provider_file(ws, base_package)
        if not storage.exists(target_path):
            raise FileNotFoundError(f"ModItemTagProvider not found at {target_path}")

        src = storage.read_text(target_path, encoding="utf-8", errors="ignore")
        if TAGS_END_ANCHOR not in src:
            raise RuntimeError(f"Item tag END anchor not found: {TAGS_END_ANCHOR}")

        # Render all candidate lines (assume tags are already valid for ItemTags.<TAG>)
        tpl_path = item_tag_line_template(framework)
        tpl = storage.read_text(tpl_path)

        rendered_lines: List[str] = []
        seen: set[str] = set()
        for tag in tags:
            tag_str = str(tag).strip()
            if not tag_str:
                continue
            line = render_placeholders(tpl, {
                "tag": tag_str,
                "registry_constant": registry_constant,
            }).rstrip("\n")
            if line not in seen:
                rendered_lines.append(line)
                seen.add(line)

        if not rendered_lines:
            return {"updated_files": []}

        # Idempotence: only insert lines not already present verbatim
        missing = [ln for ln in rendered_lines if ln not in src]
        if not missing:
            return {"updated_files": []}

        block = "\n".join(missing)
        updated = insert_before_anchor(src, TAGS_END_ANCHOR, block)
        if updated != src:
            storage.write_text(target_path, updated, encoding="utf-8")
        return {"updated_files": [str(target_path)]}

    return RunnableLambda(lambda x: _run(x))

