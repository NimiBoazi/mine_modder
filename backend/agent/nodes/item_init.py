from __future__ import annotations

from pathlib import Path
from backend.agent.state import AgentState
from backend.agent.wrappers.storage import STORAGE as storage
from backend.agent.providers.paths import (
    templates_dir,
    main_class_file,
    mod_items_file,
    java_base_package_dir,
)

def _render(text: str, ctx: dict) -> str:
    for k, v in ctx.items():
        text = text.replace(f"{{{{{k}}}}}", str(v))
    return text

def items_init_guard(state: AgentState) -> AgentState:
    """
    Ensure ModItems.java and the main mod class (with anchor blocks) exist.
    Runs ONCE per workspace: controlled via state['items_initialized'].
    STRICT: requires the content templates to exist in templates_dir(framework, "item").
    """
    if state.get("items_initialized"):
        state.setdefault("events", []).append({"node": "items_init_guard", "ok": True, "skipped": True})
        return state

    ws = Path(state["workspace_path"])
    framework = state["framework"]

    # use the current item as placeholder source
    item = (state.get("current_task", {}) or {}).get("params", {}).get("item") or state.get("item")
    if not item:
        raise RuntimeError("items_init_guard requires an 'item' payload for placeholders")

    ctx = {
        "base_package": item["base_package"],
        "main_class_name": item["main_class_name"],
        "modid": item["modid"],
        "creative_tab_key": item["creative_tab_key"],
        "registry_constant": item["registry_constant"],
        "item_id": item["item_id"],
        "display_name": item["display_name"],
        "model_parent": item["model_parent"],
    }

    # Paths from provider
    base_pkg_dir = java_base_package_dir(ws, item["base_package"])
    main_class_path = main_class_file(ws, item["base_package"], item["main_class_name"])
    mod_items_path = mod_items_file(ws, item["base_package"])

    storage.ensure_dir(base_pkg_dir)
    storage.ensure_dir(mod_items_path.parent)

    # Templates (content) location — STRICT
    td = templates_dir(framework, domain="item")
    tmpl_mod_items = td / "mod_items_class.java.tmpl"
    tmpl_main = td / "main_class.java.tmpl"
    if not tmpl_mod_items.exists():
        raise FileNotFoundError(f"Missing template: {tmpl_mod_items}")
    if not tmpl_main.exists():
        raise FileNotFoundError(f"Missing template: {tmpl_main}")

    # Write-if-missing (do not overwrite user edits on init)
    if not storage.exists(mod_items_path):
        storage.write_text(mod_items_path, _render(tmpl_mod_items.read_text(encoding="utf-8"), ctx), encoding="utf-8")
    if not storage.exists(main_class_path):
        storage.write_text(main_class_path, _render(tmpl_main.read_text(encoding="utf-8"), ctx), encoding="utf-8")

    state["items_initialized"] = True
    state.setdefault("events", []).append({"node": "items_init_guard", "ok": True})
    return state
