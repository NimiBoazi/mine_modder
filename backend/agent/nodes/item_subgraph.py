from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Dict, Any
from backend.agent.state import AgentState
from backend.agent.wrappers.storage import STORAGE as storage
from backend.agent.providers.paths import (
    lang_file,
    texture_file,
)
# Optional codegen wrapper builders (implemented later)
try:
    from backend.agent.providers.create_custom_item_class import build_create_custom_item_class
except Exception:  # pragma: no cover
    build_create_custom_item_class = None  # type: ignore
try:
    from backend.agent.providers.create_registry_line import build_create_registry_line
except Exception:  # pragma: no cover
    build_create_registry_line = None  # type: ignore
try:
    from backend.agent.providers.create_item_model import build_create_item_model
except Exception:  # pragma: no cover
    build_create_item_model = None  # type: ignore
try:
    from backend.agent.providers.create_item_tags import build_create_item_tags
except Exception:  # pragma: no cover
    build_create_item_tags = None  # type: ignore
try:
    from backend.agent.providers.create_item_recipe import build_create_item_recipe
except Exception:  # pragma: no cover
    build_create_item_recipe = None  # type: ignore
try:
    from backend.agent.providers.update_creative_tab_item import build_update_creative_tab_item
except Exception:  # pragma: no cover
    build_update_creative_tab_item = None  # type: ignore
try:
    from backend.agent.providers.update_food_properties import build_update_food_properties
except Exception:  # pragma: no cover
    build_update_food_properties = None  # type: ignore

# NEW: LLM provider for item schema
from backend.agent.providers.item_schema import build_item_schema_extractor
from backend.agent.providers.image_gen import build_item_texture_generator

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
    print("[ENTER] node:item_subgraph")

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

    # Provide existing objects for dependency-aware prompting
    prev_items = list((state.get("items") or {}).keys())
    created_objects = list(state.get("created_objects") or [])
    available_objects = list(dict.fromkeys([*(created_objects or []), *(prev_items or [])]))

    # Will raise if the wrapper/model returns invalid JSON or lacks item_id (no fallbacks in wrapper)
    item_schema: Dict[str, Any] = extractor.invoke({
        "task": task_text,
        "user_prompt": user_prompt,
        "available_objects": available_objects,
    })

    item_id = item_schema["item_id"].strip()

    # Use the LLM-provided field from item_schema (do not derive here)
    item_class_name = item_schema["item_class_name"]

    # Persist a full schema for this item_id inside state["items"] (include mod context here)
    items = state.get("items") or {}
    # copy to avoid mutating provider output
    persisted = dict(item_schema)
    persisted.update({
        "modid": modid,
        "base_package": base_package,
        "item_class_name": item_class_name,
        # Back-compat: keep 'main_class_name' alias for any legacy consumers expecting this key
        "main_class_name": item_class_name,
    })
    items[item_id] = persisted
    state["items"] = items
    state["current_item_id"] = item_id
    state["item"] = persisted
    # Track created objects globally for dependency-aware prompts
    co = list(state.get("created_objects") or [])
    if item_id not in co:
        co.append(item_id)
    state["created_objects"] = co

    # === Continue with deterministic file updates using provided schema ===
    ctx = {
        "base_package": base_package,
        "item_class_name": item_class_name,
        "modid": modid,
        "creative_tab_key": item_schema["creative_tab_key"],
        "registry_constant": item_schema["registry_constant"],
        "item_id": item_id,
        "display_name": item_schema["display_name"],
        "model_type": item_schema["model_type"],
    }


    lang_path       = lang_file(ws, modid)
    texture_png     = texture_file(ws, framework, ctx)   # STRICT path templates

    changed: List[str] = []
    notes: List[str] = []


    # 1) Create the custom class via wrapper. Wrapper writes the file; subgraph assumes success.
    if build_create_custom_item_class is None:
        raise RuntimeError("Missing provider: create_custom_item_class (build_create_custom_item_class)")
    _ = build_create_custom_item_class().invoke({
        "item_schema": item_schema,
        "mod_context": {"base_package": base_package, "modid": modid},
        "framework": framework,
        "workspace": str(ws),
        "items_index": state.get("items") or {},
    })

    # 2) Registry update via wrapper. Wrapper updates ModItems.java; subgraph assumes success.
    if build_create_registry_line is None:
        raise RuntimeError("Missing provider: create_registry_line (build_create_registry_line)")
    _ = build_create_registry_line().invoke({
        "item_schema": item_schema,
        "mod_context": {"base_package": base_package, "modid": modid},
        "framework": framework,
        "workspace": str(ws),
    })

    # 3) Update creative tab via wrapper; subgraph assumes success
    if bool(item_schema.get("add_to_creative", True)):
        if build_update_creative_tab_item is None:
            raise RuntimeError("Missing provider: update_creative_tab_item (build_update_creative_tab_item)")
        _ = build_update_creative_tab_item().invoke({
            "item_schema": item_schema,
            "mod_context": {"base_package": base_package, "modid": modid},
            "framework": framework,
            "workspace": str(ws),
        })

    # 4) ModItemModelProvider update via wrapper. Wrapper updates file; subgraph assumes success.
    if build_create_item_model is None:
        raise RuntimeError("Missing provider: create_item_model (build_create_item_model)")
    _ = build_create_item_model().invoke({
        "item_schema": item_schema,
        "mod_context": {"base_package": base_package, "modid": modid},
        "framework": framework,
        "workspace": str(ws),
    })

    # 4.5) ModFoodProperties update via wrapper; only if consumable
    if bool(item_schema.get("is_consumable", False)):
        if build_update_food_properties is None:
            raise RuntimeError("Missing provider: update_food_properties (build_update_food_properties)")
        _ = build_update_food_properties().invoke({
            "item_schema": item_schema,
            "mod_context": {"base_package": base_package, "modid": modid},
            "framework": framework,
            "workspace": str(ws),
        })

    # 5) ModItemTagProvider update via wrapper; subgraph assumes success (only if tags present)
    tags = item_schema.get("tags") or []
    if tags:
        if build_create_item_tags is None:
            raise RuntimeError("Missing provider: create_item_tags (build_create_item_tags)")
        _ = build_create_item_tags().invoke({
            "item_schema": item_schema,
            "mod_context": {"base_package": base_package, "modid": modid},
            "framework": framework,
            "workspace": str(ws),
        })

    # 6) ModRecipeProvider update via wrapper; subgraph assumes success (only if ingredients present)
    ingredients = item_schema.get("recipe_ingredients") or []
    if ingredients:
        if build_create_item_recipe is None:
            raise RuntimeError("Missing provider: create_item_recipe (build_create_item_recipe)")
        _ = build_create_item_recipe().invoke({
            "item_schema": item_schema,
            "mod_context": {"base_package": base_package, "modid": modid},
            "framework": framework,
            "workspace": str(ws),
        })


    # 8) Lang merge
    if _json_lang_update(lang_path, f'item.{modid}.{item_id}', item_schema["display_name"]):
        changed.append(str(lang_path))

    # Tooltip entries (both keys use the same tooltip_text value)
    tooltip_text = item_schema.get("tooltip_text")
    if isinstance(tooltip_text, str) and tooltip_text.strip():
        if _json_lang_update(lang_path, f'tooltip.{modid}.{item_id}', tooltip_text):
            changed.append(str(lang_path))
        if _json_lang_update(lang_path, f'tooltip.{modid}.{item_id}.shift_down', tooltip_text):
            changed.append(str(lang_path))

    # 9) Texture generation (optional)
    texture_prompt = item_schema.get("texture_prompt")
    texture_prompt = texture_prompt.strip() if isinstance(texture_prompt, str) else ""
    gen = build_item_texture_generator()
    if gen is not None and texture_prompt:
        try:
            if storage.exists(texture_png):
                notes.append(f"Texture already exists, skipped generation: {texture_png}")
            else:
                result = gen.invoke({
                    "prompt": texture_prompt,
                    "width": 16,
                    "height": 16,
                    "num_images": 1,
                    "prompt_style": "rd_fast__mc_item",
                })
                img_bytes = result.get("image_bytes") if isinstance(result, dict) else None
                if isinstance(img_bytes, (bytes, bytearray)):
                    storage.write_bytes(texture_png, bytes(img_bytes))
                    changed.append(str(texture_png))
                else:
                    notes.append("Texture generator returned no image bytes; skipping save.")
        except Exception as e:
            notes.append(f"Texture generation failed: {e}")

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
