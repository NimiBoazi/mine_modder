from __future__ import annotations

from pathlib import Path
from typing import List

from backend.agent.state import AgentState
from backend.agent.wrappers.storage import STORAGE as storage
from backend.agent.providers.paths import (
    templates_dir,
    main_class_file,
    mod_items_file,
    java_base_package_dir,
    assets_dir,
)


def _render(text: str, ctx: dict) -> str:
    for k, v in ctx.items():
        text = text.replace(f"{{{{{k}}}}}", str(v))
    return text


def template_init(state: AgentState) -> AgentState:
    """
    Generic templates bootstrap (framework-specific). This node will gradually
    become the place to insert non-item-specific templates and perform placeholder
    replacement for already-known variables. For now, we copy/insert folders and
    files per the provided specification.

    This is safe/idempotent where possible and only relies on:
    - state['workspace_path']
    - state['framework']
    - state['modid']
    - state['package']
    """
    ws = Path(state["workspace_path"]).resolve()
    framework = state["framework"]
    modid = state["modid"]
    base_package = state["package"]

    # Derive a deterministic main class name (same logic as item_subgraph)
    main_class_name = "".join(p.capitalize() for p in modid.split("_") if p)

    # Context for lightweight rendering; unknown placeholders stay as-is
    ctx = {
        "base_package": base_package,
        "main_class_name": main_class_name,
        "modid": modid,
    }

    # Resolve key paths
    base_pkg_dir = java_base_package_dir(ws, base_package)
    main_class_path = main_class_file(ws, base_package, main_class_name)
    mod_items_path = mod_items_file(ws, base_package)

    main_class_dir = main_class_path.parent
    mod_items_dir = mod_items_path.parent

    # Templates root for this framework/domain
    td = templates_dir(framework, domain="item")

    changed: List[str] = []
    # A) Core creates previously handled in item_init/item_subgraph
    #    - Ensure base package & item dirs
    storage.ensure_dir(base_pkg_dir)
    storage.ensure_dir(mod_items_dir)

    #    - Create main mod class and ModItems.java if missing, with placeholder rendering
    tmpl_mod_items = td / "mod_items_class.java.tmpl"
    tmpl_main = td / "main_class.java.tmpl"
    if not tmpl_mod_items.exists():
        raise FileNotFoundError(f"Missing template: {tmpl_mod_items}")
    if not tmpl_main.exists():
        raise FileNotFoundError(f"Missing template: {tmpl_main}")

    if not storage.exists(mod_items_path):
        storage.write_text(mod_items_path, _render(tmpl_mod_items.read_text(encoding="utf-8"), ctx))
        changed.append(str(mod_items_path))
    if not storage.exists(main_class_path):
        storage.write_text(main_class_path, _render(tmpl_main.read_text(encoding="utf-8"), ctx))
        changed.append(str(main_class_path))

    #    - Ensure assets/lang and textures dirs
    assets_root = assets_dir(ws, modid)
    lang_dir = assets_root / "lang"
    textures_block_dir = assets_root / "textures" / "block"
    textures_item_dir = assets_root / "textures" / "item"
    for d in (lang_dir, textures_block_dir, textures_item_dir):
        storage.ensure_dir(d)
        changed.append(str(d))

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
    else:
        raise FileNotFoundError(f"Missing template: {cfg_tmpl}")


    # 1) block folder + ModBlocks.java + empty custom subfolder
    block_dir = main_class_dir / "block"
    storage.ensure_dir(block_dir)
    block_custom_dir = block_dir / "custom"
    storage.ensure_dir(block_custom_dir)

    modblocks_tmpl = td / "block" / "ModBlocks.java.tmpl"
    if modblocks_tmpl.exists():
        storage.write_text(block_dir / "ModBlocks.java", _render(modblocks_tmpl.read_text("utf-8"), ctx))
        changed.append(str(block_dir / "ModBlocks.java"))
    else:
        raise FileNotFoundError(f"Missing template: {modblocks_tmpl}")

    # 2) datagen folder under main_class_dir: render all *.tmpl -> *.java (or strip .tmpl), replace placeholders
    datagen_src = td / "datagen"
    if datagen_src.exists() and datagen_src.is_dir():
        datagen_dst = main_class_dir / "datagen"
        storage.ensure_dir(datagen_dst)
        for src in datagen_src.rglob("*"):
            rel = src.relative_to(datagen_src)
            dst = datagen_dst / rel
            if src.is_dir():
                storage.ensure_dir(dst)
                continue
            # File: if it's a template, strip .tmpl suffix; always render placeholders
            dst_path = dst
            name = src.name
            if name.endswith(".tmpl"):
                dst_path = dst.with_name(name[:-5])  # remove trailing ".tmpl"
            content = src.read_text(encoding="utf-8")
            storage.write_text(dst_path, _render(content, ctx))
            changed.append(str(dst_path))
    else:
        raise FileNotFoundError(f"Missing folder: {datagen_src}")

    # 3) custom folder under ModItems directory + FuelItem.java
    items_custom_dir = mod_items_dir / "custom"
    storage.ensure_dir(items_custom_dir)
    fuel_tmpl = td / "FuelItem.java.tmpl"
    if fuel_tmpl.exists():
        storage.write_text(items_custom_dir / "FuelItem.java", _render(fuel_tmpl.read_text("utf-8"), ctx))
        changed.append(str(items_custom_dir / "FuelItem.java"))
    else:
        raise FileNotFoundError(f"Missing template: {fuel_tmpl}")

    # 4) ModFoodProperties.java in ModItems directory
    food_props_tmpl = td / "ModFoodProperties.java.tmpl"
    if food_props_tmpl.exists():
        storage.write_text(mod_items_dir / "ModFoodProperties.java", _render(food_props_tmpl.read_text("utf-8"), ctx))
        changed.append(str(mod_items_dir / "ModFoodProperties.java"))
    else:
        raise FileNotFoundError(f"Missing template: {food_props_tmpl}")

    # 5) util folder under main_class_dir + ModTags.java
    util_dir = main_class_dir / "util"
    storage.ensure_dir(util_dir)
    modtags_tmpl = td / "util" / "ModTags.java.tmpl"
    if modtags_tmpl.exists():
        storage.write_text(util_dir / "ModTags.java", _render(modtags_tmpl.read_text("utf-8"), ctx))
        changed.append(str(util_dir / "ModTags.java"))
    else:
        raise FileNotFoundError(f"Missing template: {modtags_tmpl}")

    state["templates_initialized"] = True
    state.setdefault("events", []).append({
        "node": "template_init",
        "ok": True,
        "changed": changed,
    })
    return state

