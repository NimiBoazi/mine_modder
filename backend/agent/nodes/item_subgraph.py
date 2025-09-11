from __future__ import annotations
import re
from pathlib import Path
from typing import List
from backend.agent.state import AgentState
from backend.agent.wrappers.storage import STORAGE as storage
from backend.agent.providers.paths import (
    templates_dir,
    main_class_file,
    mod_items_file,
    lang_file,
    model_file,
    texture_file,
)

# Anchor constants colocated here for clarity
REG_BEGIN = "// ==MM:ITEM_REGISTRATIONS_BEGIN=="
REG_END   = "// ==MM:ITEM_REGISTRATIONS_END=="
CRE_BEGIN = "// ==MM:CREATIVE_ACCEPT_BEGIN=="
CRE_END   = "// ==MM:CREATIVE_ACCEPT_END=="

def _render(text: str, ctx: dict) -> str:
    for k, v in ctx.items():
        text = text.replace(f"{{{{{k}}}}}", str(v))
    return text

def _insert_between_anchors(path: Path, begin: str, end: str, snippet: str) -> bool:
    """Idempotent insert of snippet inside [begin, end] if not already present."""
    s = storage.read_text(path)
    if snippet.strip() in s:
        return False
    start = s.find(begin)
    stop = s.find(end, start + len(begin))
    if start == -1 or stop == -1:
        raise RuntimeError(f"Anchor block not found in {path}: [{begin}..{end}]")
    new = s[:start+len(begin)] + "\n" + snippet.rstrip() + "\n" + s[stop:]
    storage.write_text(path, new)
    return True

def _json_lang_update(path: Path, key: str, value: str) -> bool:
    import json
    data = {}
    if path.exists():
        data = json.loads(storage.read_text(path) or "{}")
    if data.get(key) == value:
        return False
    data[key] = value
    storage.ensure_dir(path.parent)
    storage.write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
    return True

def item_subgraph(state: AgentState) -> AgentState:
    ws = Path(state["workspace_path"])
    framework = state["framework"]

    task = state.get("current_task") or {}
    item_id = ((task.get("params") or {}).get("item_id") or "").strip()
    if not item_id:
        raise RuntimeError("item_subgraph: task.params.item_id is required")

    items = state.get("items") or {}
    base_schema = items.get(item_id)
    if not isinstance(base_schema, dict):
        raise RuntimeError(f"item_subgraph: no schema found in state['items'] for '{item_id}'")

    # derive deterministic ctx from mod state + schema
    modid = state["modid"]
    base_package = state["package"]
    main_class_name = "".join(p.capitalize() for p in modid.split("_") if p)
    registry_constant = re.sub(r'[^A-Za-z0-9]+', '_', item_id).upper().strip('_')

    item = dict(base_schema)  # don’t mutate registry
    item.setdefault("add_to_creative", True)
    item.setdefault("model_parent", "minecraft:item/generated")

    ctx = {
        "base_package": base_package,
        "main_class_name": main_class_name,
        "modid": modid,
        "creative_tab_key": item["creative_tab_key"],
        "registry_constant": registry_constant,
        "item_id": item_id,
        "display_name": item["display_name"],
        "model_parent": item["model_parent"],
    }

    # Workspace paths (via provider)
    main_class_path = main_class_file(ws, item["base_package"], item["main_class_name"])
    mod_items_path  = mod_items_file(ws, item["base_package"])
    lang_path       = lang_file(ws, item["modid"])
    model_path      = model_file(ws, framework, ctx)     # STRICT path templates
    texture_png     = texture_file(ws, framework, ctx)   # STRICT path templates

    changed: List[str] = []
    notes: List[str] = []

    # Content templates dir (per framework; STRICT existence)
    td = templates_dir(framework, domain="item")

    # 1) Insert registration line (between anchors, idempotent)
    reg_tmpl = td / "mod_items_registration_line.java.tmpl"
    if not reg_tmpl.exists():
        raise FileNotFoundError(f"Missing template: {reg_tmpl}")
    reg_line  = _render(reg_tmpl.read_text(encoding="utf-8"), ctx).rstrip()
    if _insert_between_anchors(mod_items_path, REG_BEGIN, REG_END, reg_line):
        changed.append(str(mod_items_path))

    # 2) Insert creative tab accept (if requested)
    if bool(item.get("add_to_creative", True)):
        cre_tmpl = td / "creative_tab_accept_line.java.tmpl"
        if not cre_tmpl.exists():
            raise FileNotFoundError(f"Missing template: {cre_tmpl}")
        cre_line  = _render(cre_tmpl.read_text(encoding="utf-8"), ctx).rstrip()
        if _insert_between_anchors(main_class_path, CRE_BEGIN, CRE_END, cre_line):
            changed.append(str(main_class_path))

    # 3) Lang merge
    if _json_lang_update(lang_path, f'item.{item["modid"]}.{item["item_id"]}', item["display_name"]):
        changed.append(str(lang_path))

    # 4) Model overwrite (deterministic)
    model_tmpl = td / "item_model.json.tmpl"
    if not model_tmpl.exists():
        raise FileNotFoundError(f"Missing template: {model_tmpl}")
    model_json = _render(model_tmpl.read_text(encoding="utf-8"), ctx)
    storage.ensure_dir(model_path.parent)
    prev = storage.read_text(model_path) if storage.exists(model_path) else None
    storage.write_text(model_path, model_json, encoding="utf-8")
    if prev != model_json:
        changed.append(str(model_path))

    # 5) Texture hint
    storage.ensure_dir(texture_png.parent)
    if not texture_png.exists():
        notes.append(f'Place texture at: {texture_png}')

    # Record
    state.setdefault("results", {})
    task = state.get("current_task") or {}
    state["results"][task.get("id", f'item:{item["item_id"]}')] = {
        "ok": True,
        "changed_files": changed,
        "notes": notes,
    }
    state.setdefault("events", []).append({"node": "item_subgraph", "ok": True, "item": item["item_id"]})
    return state
