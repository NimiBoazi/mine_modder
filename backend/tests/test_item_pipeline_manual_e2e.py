from __future__ import annotations

"""
Manual E2E for item pipeline:
- Runs the real init_subgraph to create an MDK workspace
- Skips planner/router/next_task (not implemented yet)
- Invokes item_entry -> items_init_guard -> item_subgraph directly
- Provides the item schema in state as expected by these nodes

Run from repo root:
  # run the whole file (NeoForge-only)
  pytest -s -q backend/tests/test_item_pipeline_manual_e2e.py

  # run just this test function
  pytest -s -q backend/tests/test_item_pipeline_manual_e2e.py::test_item_pipeline_manual

MDK workspace location:
  - Created under: runs/_test_workspaces (override with MM_TEST_WORKSPACES_ROOT)
  - Snapshots saved under: runs/_test_artifacts/<modid>_neoforge_1.21.1_manual_item/
      - after_mdk_download (downloads dir + zip)
      - after_init (workspace after init)
      - after_items_init_guard
      - after_item_subgraph
  - Override artifact root with MM_TEST_ARTIFACTS_ROOT

Requires GOOGLE_API_KEY in backend/.env (same as init E2E).
"""

import os
from pathlib import Path
import shutil
import re

import pytest
from dotenv import load_dotenv, find_dotenv

from backend.agent.graph import build_graph
from backend.agent.nodes.item_entry import item_entry
from backend.agent.nodes.item_init import items_init_guard
from backend.agent.nodes.item_subgraph import item_subgraph
from backend.agent.providers.paths import (
    mod_items_file, main_class_file, lang_file, model_file, texture_file
)


def _cap_modid(modid: str) -> str:
    return "".join(p.capitalize() for p in modid.split("_") if p)


def _registry_constant(item_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", item_id).upper().strip("_")



def _snapshot_tree(src: Path, dst: Path) -> None:
    """Copy the entire workspace tree to a stage-specific snapshot path."""
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"[artifact] Saved snapshot: {dst}")
    except Exception as e:
        print(f"[artifact] Failed to save snapshot {src} -> {dst}: {e}")


@pytest.mark.slow
@pytest.mark.parametrize("framework,mc_version", [
    ("neoforge", "1.21.1"),
])
def test_item_pipeline_manual(framework: str, mc_version: str):
    # --- Ensure env is loaded ---
    root_env = find_dotenv(usecwd=True)
    if root_env:
        load_dotenv(root_env, override=False)
    backend_env = Path(__file__).resolve().parents[1] / ".env"
    if backend_env.exists():
        load_dotenv(backend_env, override=False)
    assert os.getenv("GOOGLE_API_KEY"), "GOOGLE_API_KEY not found; set it in backend/.env"

    # Use persistent roots so the MDK is inspectable after the test
    artifacts_root = Path(os.getenv("MM_TEST_ARTIFACTS_ROOT", "runs/_test_artifacts"))
    workspaces_root = Path(os.getenv("MM_TEST_WORKSPACES_ROOT", "runs/_test_workspaces"))
    runs_root = workspaces_root
    downloads_root = Path(os.getenv("MM_DOWNLOADS_ROOT", "runs/_downloads"))

    # ---- 1) Run init pipeline via the main graph (like test_graph_init_e2e) ----
    g = build_graph()
    init_state = {
        "user_input": "Create a sapphire block.",  # avoid the word 'item' to not schedule item tasks
        "framework": framework,
        "mc_version": mc_version,
        "author": "TestAuthor",
        "runs_root": str(runs_root),
        "downloads_root": str(downloads_root),
        "timeout": int(os.getenv("MM_GRADLE_TIMEOUT", "1800")),
    }

    result = g.invoke(init_state, config={"recursion_limit": 200})

    ws = Path(result["workspace_path"])
    smoke = (result.get("artifacts") or {}).get("gradle_smoke") or {}

    # Check that init populated required fields (we don't set them here)
    assert result.get("framework") == framework
    assert result.get("workspace_path")
    assert result.get("modid")
    assert result.get("package")
    assert ws.exists() and ws.is_dir(), f"workspace not created: {ws}"
    assert smoke.get("ok") is True, f"Gradle smoke failed: {smoke}"

    # ---- 2) Prepare minimal item schema in state and skip planner/router ----
    modid = result["modid"]
    base_package = result["package"]
    main_class_name = _cap_modid(modid)

    # Stage snapshots base
    dest_base = artifacts_root / f"{modid}_{framework}_{mc_version}_manual_item"

    # Snapshot immediately after MDK download (downloads folder + raw zip)
    dl_dir = Path((result.get("artifacts") or {}).get("mdk_download_dir") or (downloads_root / framework / mc_version))
    _snapshot_tree(dl_dir, dest_base / "after_mdk_download")
    zip_path = Path((result.get("artifacts") or {}).get("mdk_zip_path") or "")
    if zip_path and zip_path.exists():
        (dest_base / "after_mdk_download").mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(zip_path, (dest_base / "after_mdk_download" / zip_path.name))
        except Exception as e:
            print(f"[artifact] Failed to copy mdk zip: {e}")

    # Snapshot the workspace right after init
    _snapshot_tree(ws, dest_base / "after_init")

    item_id = "alexandrite"
    schema = {
        "base_package": base_package,
        "main_class_name": main_class_name,
        "modid": modid,
        "item_id": item_id,
        "display_name": "Alexandrite Gem",
        "creative_tab_key": "CreativeModeTabs.INGREDIENTS",
        "registry_constant": _registry_constant(item_id),
        "model_parent": "minecraft:item/generated",
    }

    # Start from init result; do not override framework/modid/package/workspace_path
    state = dict(result)
    # Set/augment only what the item pipeline needs
    state["items_initialized"] = False
    state["items"] = {item_id: schema}
    state["current_task"] = {"id": "t_item_1", "type": "add_custom_item", "params": {"item_id": item_id, "item": schema}}
    state["item"] = schema

    # ---- 3) Run item pipeline nodes directly ----
    state = item_entry(state)
    state = items_init_guard(state)
    _snapshot_tree(ws, dest_base / "after_items_init_guard")
    state = item_subgraph(state)
    _snapshot_tree(ws, dest_base / "after_item_subgraph")

    # ---- 4) Assertions on outputs ----
    # Check files exist
    mod_items = mod_items_file(ws, base_package)
    main_class = main_class_file(ws, base_package, main_class_name)
    lang = lang_file(ws, modid)
    model = model_file(ws, framework, {
        "base_package": base_package,
        "main_class_name": main_class_name,
        "modid": modid,
        "creative_tab_key": schema["creative_tab_key"],
        "registry_constant": schema["registry_constant"],
        "item_id": item_id,
        "display_name": schema["display_name"],
        "model_parent": schema["model_parent"],
    })
    texture = texture_file(ws, framework, {
        "base_package": base_package,
        "main_class_name": main_class_name,
        "modid": modid,
        "creative_tab_key": schema["creative_tab_key"],
        "registry_constant": schema["registry_constant"],
        "item_id": item_id,
        "display_name": schema["display_name"],
        "model_parent": schema["model_parent"],
    })

    assert mod_items.exists(), f"ModItems.java missing: {mod_items}"
    assert main_class.exists(), f"Main class missing: {main_class}"
    assert lang.exists(), f"Lang file missing: {lang}"
    assert model.exists(), f"Model file missing: {model}"
    # Texture is a hint; may not be created. Ensure directory exists at least.
    assert texture.parent.exists(), f"Texture directory missing: {texture.parent}"

    # Check anchor insertions by string match
    mod_items_txt = mod_items.read_text(encoding="utf-8")
    assert f"ITEMS.register(\"{item_id}\")" in mod_items_txt or schema["registry_constant"] in mod_items_txt

    main_txt = main_class.read_text(encoding="utf-8")
    assert "addCreative(BuildCreativeModeTabContentsEvent event)" in main_txt

    # Stage snapshots were saved at:
    print(f"[artifact] after_init: {dest_base / 'after_init'}")
    print(f"[artifact] after_items_init_guard: {dest_base / 'after_items_init_guard'}")
    print(f"[artifact] after_item_subgraph: {dest_base / 'after_item_subgraph'}")

