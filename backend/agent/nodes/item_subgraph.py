from __future__ import annotations
import re
from pathlib import Path
from typing import List, Dict, Any, Dict, Any
from backend.agent.state import AgentState
from backend.agent.wrappers.storage import STORAGE as storage
from backend.agent.providers.paths import (
    templates_dir,
    main_class_file,
    mod_items_file,
    lang_file,
    model_file,
    texture_file,
    java_base_package_dir,
)
# NEW: LLM provider for item schema
from backend.agent.providers.item_schema import build_item_schema_extractor

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
    """Append snippet on the line before the end anchor.

    Behaviors:
    - Matches indentation of the END anchor line.
    - Idempotent: if the fully-indented snippet already exists, does nothing.
    - Preserves existing content between anchors; appends just above END.
    - Ensures exactly one empty line above the END anchor after insertion.
    """
    s = storage.read_text(path, encoding="utf-8", errors="ignore")

    start = s.find(begin)
    stop = s.find(end, start + len(begin))
    if start == -1 or stop == -1:
        raise RuntimeError(f"Anchor block not found in {path}: [{begin}..{end}]")

    # Identify the start of the END anchor line and its indentation
    line_start = s.rfind("\n", 0, stop)
    if line_start == -1:
        line_start = 0
    end_line_start = line_start + 1
    end_line = s[end_line_start : s.find("\n", stop) if s.find("\n", stop) != -1 else len(s)]

    import re as _re
    end_indent = _re.match(r"[\t ]*", end_line).group(0)

    # Prepare indented snippet (multi-line safe)
    rendered = snippet.rstrip("\n")
    indented = "\n".join((end_indent + ln if ln else ln) for ln in rendered.splitlines())

    # Idempotence check against fully-indented payload
    if indented and indented in s:
        return False

    # Compose: keep the indentation of END line intact
    before_end_line = s[:end_line_start]
    end_and_after = s[end_line_start:]

    # Ensure exactly one blank line before END anchor
    before_end_line = before_end_line.rstrip(" \t\n") + "\n\n"

    new = before_end_line + indented + "\n" + end_indent + end_and_after
    storage.write_text(path, new, encoding="utf-8")
    return True


def _normalize_anchor_block(path: Path, begin: str, end: str) -> bool:
    """Ensure BEGIN and END lines share the same indentation and enforce one blank line above END.

    Returns True if a change was made.
    """
    s = storage.read_text(path, encoding="utf-8", errors="ignore")
    start = s.find(begin)
    stop = s.find(end, start + len(begin))
    if start == -1 or stop == -1:
        return False

    import re as _re

    # Compute begin/end line starts and indents
    begin_ls = s.rfind("\n", 0, start)
    begin_ls = 0 if begin_ls == -1 else begin_ls + 1
    end_ls = s.rfind("\n", 0, stop)
    end_ls = 0 if end_ls == -1 else end_ls + 1

    begin_line = s[begin_ls : s.find("\n", start) if s.find("\n", start) != -1 else len(s)]
    end_line = s[end_ls : s.find("\n", stop) if s.find("\n", stop) != -1 else len(s)]

    begin_indent = _re.match(r"[\t ]*", begin_line).group(0)
    end_indent = _re.match(r"[\t ]*", end_line).group(0)

    changed = False

    # If end indent differs, replace it
    if begin_indent != end_indent:
        # Replace only the leading whitespace of the END line
        end_line_no_ws = end_line[len(end_indent):]
        s = s[:end_ls] + begin_indent + end_line_no_ws + s[end_ls + len(end_line):]
        changed = True
        # Recompute positions after mutation
        stop = s.find(end, begin_ls + len(begin))
        end_ls = s.rfind("\n", 0, stop)
        end_ls = 0 if end_ls == -1 else end_ls + 1

    # Enforce exactly one blank line before END line
    head = s[:end_ls]
    head = head.rstrip(" \t\n") + "\n\n"
    s = head + s[end_ls:]
    storage.write_text(path, s, encoding="utf-8")
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
    modid = state["modid"]
    base_package = state["package"]

    if not ws or not framework or not modid or not base_package:
        raise RuntimeError("item_subgraph: missing required state (workspace_path/framework/modid/package).")

    # === NEW: derive the item schema from the LLM based on current task + user prompt ===
    task_obj: Dict[str, Any] = state.get("current_task") or {}
    # Prefer human-readable fields; fallback to serialized task for context
    task_text = (
        task_obj.get("title")
        or task_obj.get("name")
        or task_obj.get("desc")
        or task_obj.get("description")
        or task_obj.get("text")
        or task_obj.get("prompt")
        or task_obj.get("spec")
        or task_obj.get("type")
        or ""
    )
    if not task_text:
        # provide full task dict as last-resort context (not an LLM fallback—just input)
        import json as _json
        task_text = _json.dumps(task_obj, ensure_ascii=False)

    user_prompt = state.get("user_input", "") or ""

    extractor = build_item_schema_extractor()
    if extractor is None:
        raise RuntimeError("item_subgraph: item schema provider unavailable or misconfigured.")

    # Will raise if the wrapper/model returns invalid JSON or lacks item_id (no fallbacks in wrapper)
    item_schema: Dict[str, Any] = extractor.invoke({"task": task_text, "user_prompt": user_prompt})

    item_id = item_schema["item_id"].strip()

    # Minimal, derivable fields to keep the rest of the pipeline deterministic
    main_class_name = "".join(p.capitalize() for p in modid.split("_") if p)

    # Persist a full schema for this item_id inside state["items"] (include mod context here)
    items = state.get("items") or {}
    # copy to avoid mutating provider output
    persisted = dict(item_schema)
    persisted.update({
        "modid": modid,
        "base_package": base_package,
        "main_class_name": main_class_name,
    })
    items[item_id] = persisted
    state["items"] = items
    state["current_item_id"] = item_id
    state["item"] = persisted

    # === Continue with deterministic file updates using provided schema ===
    ctx = {
        "base_package": base_package,
        "main_class_name": main_class_name,
        "modid": modid,
        "creative_tab_key": item_schema["creative_tab_key"],
        "registry_constant": item_schema.get("registry_constant") or re.sub(r'[^A-Za-z0-9]+', '_', item_id).upper().strip('_'),
        "item_id": item_id,
        "display_name": item_schema["display_name"],
        "model_parent": item_schema["model_parent"],
    }

    # Workspace paths (via provider) — use derived values to avoid schema drift
    main_class_path = main_class_file(ws, base_package, main_class_name)
    mod_items_path  = mod_items_file(ws, base_package)
    lang_path       = lang_file(ws, modid)
    model_path      = model_file(ws, framework, ctx)     # STRICT path templates
    texture_png     = texture_file(ws, framework, ctx)   # STRICT path templates

    changed: List[str] = []
    notes: List[str] = []

    # Content templates dir (per framework; STRICT existence)
    td = templates_dir(framework, domain="item")

    # 0) Ensure Config.java from template (written as a normal class, no anchors)
    cfg_tmpl = td / "config.java.tmpl"
    if cfg_tmpl.exists():
        cfg_dst_dir = java_base_package_dir(ws, base_package)
        cfg_dst = cfg_dst_dir / "Config.java"
        cfg_src = _render(cfg_tmpl.read_text(encoding="utf-8"), ctx)
        prev_cfg = storage.read_text(cfg_dst) if storage.exists(cfg_dst) else None
        storage.ensure_dir(cfg_dst_dir)
        storage.write_text(cfg_dst, cfg_src, encoding="utf-8")
        if prev_cfg != cfg_src:
            changed.append(str(cfg_dst))

    # 1) Insert registration line (between anchors, idempotent)
    reg_tmpl = td / "mod_items_registration_line.java.tmpl"
    if not reg_tmpl.exists():
        raise FileNotFoundError(f"Missing template: {reg_tmpl}")
    reg_line  = _render(reg_tmpl.read_text(encoding="utf-8"), ctx).rstrip()
    if _insert_between_anchors(mod_items_path, REG_BEGIN, REG_END, reg_line):
        changed.append(str(mod_items_path))

    # 2) Insert creative tab accept (if requested)
    if bool(item_schema.get("add_to_creative", True)):
        cre_tmpl = td / "creative_tab_accept_line.java.tmpl"
        if not cre_tmpl.exists():
            raise FileNotFoundError(f"Missing template: {cre_tmpl}")
        cre_line  = _render(cre_tmpl.read_text(encoding="utf-8"), ctx).rstrip()
        if _insert_between_anchors(main_class_path, CRE_BEGIN, CRE_END, cre_line):
            changed.append(str(main_class_path))

    # 2.5) Normalize indentation and spacing of anchor blocks
    if _normalize_anchor_block(mod_items_path, REG_BEGIN, REG_END):
        if str(mod_items_path) not in changed:
            changed.append(str(mod_items_path))
    if _normalize_anchor_block(main_class_path, CRE_BEGIN, CRE_END):
        if str(main_class_path) not in changed:
            changed.append(str(main_class_path))

    # 3) Lang merge
    if _json_lang_update(lang_path, f'item.{modid}.{item_id}', item_schema["display_name"]):
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
    task_id = (task_obj.get("id") or f'item:{item_id}')
    state["results"][task_id] = {
        "ok": True,
        "changed_files": changed,
        "notes": notes,
    }
    state.setdefault("events", []).append({"node": "item_subgraph", "ok": True, "item": item_id})
    return state
