from __future__ import annotations

import os
from pathlib import Path
import shutil

import pytest
from dotenv import load_dotenv, find_dotenv

from backend.agent.nodes.init_subgraph import init_subgraph


@pytest.mark.slow
@pytest.mark.parametrize("framework,mc_version", [
    ("neoforge", "1.21.1"),
])
def test_graph_init_end_to_end_all_frameworks(tmp_path: Path, framework: str, mc_version: str):
    """
    End-to-end test of the init subgraph via the LangGraph orchestration.

    How to run this test (NeoForge only):
        pytest backend/tests/test_graph_init_e2e.py -k test_graph_init_end_to_end_all_frameworks -s

    Notes:
    - Requires GOOGLE_API_KEY in env; backend/.env is auto-loaded if present.
    - Saves workspace and smoke logs to runs/_test_artifacts/<modid>_neoforge_1.21.1

    Always persists a copy of the workspace and smoke log to test artifacts, even on failure.
    """

    # --- Ensure env is loaded (root .env if present, plus backend/.env) ---
    root_env = find_dotenv(usecwd=True)
    if root_env:
        load_dotenv(root_env, override=False)

    backend_env = Path(__file__).resolve().parents[1] / ".env"  # backend/.env
    if backend_env.exists():
        load_dotenv(backend_env, override=False)

    has_key = bool(os.getenv("GOOGLE_API_KEY"))
    print(f"GOOGLE_API_KEY present? {has_key}")
    assert has_key, "GOOGLE_API_KEY not found in process env. Did you create backend/.env and load it?"

    runs_root = tmp_path / "runs"
    downloads_root = tmp_path / "_downloads"

    # Directly invoke init_subgraph to test initialization only (avoid item_subgraph)
    state = {
        "framework": framework,
        "mc_version": mc_version,
        "author": "TestAuthor",
        "authors": ["TestAuthor"],
        "modid": "testmod",
        "group": "io.testauthor",
        "package": "io.testauthor.testmod",
        "display_name": "Test Mod",
        "description": "A test mod for NeoForge.",
        # Use temp roots so we don't pollute repo paths
        "runs_root": str(runs_root),
        "downloads_root": str(downloads_root),
        # Keep a reasonable timeout; CI environments can be slower
        "timeout": int(os.getenv("MM_GRADLE_TIMEOUT", "1800")),
    }

    result = init_subgraph(state)

    # Prepare artifact paths ASAP so we can save even if assertions fail later
    ws_path = Path(result.get("workspace_path") or "")
    smoke = (result.get("artifacts") or {}).get("gradle_smoke") or {}
    log_path = Path(smoke.get("log_path") or "")
    modid = (result.get("modid") or "mod").strip() or "mod"
    artifacts_root = Path(os.getenv("MM_TEST_ARTIFACTS_ROOT", "runs/_test_artifacts"))
    dest = artifacts_root / f"{modid}_{framework}_{mc_version}"

    try:
        # Log major outputs for transparency (run with -s to see prints)
        print("\n=== INIT GRAPH RESULT (framework=", framework, ") ===", sep="")
        print("Display name:", result.get("display_name"))
        print("Description:", result.get("description"))
        print("ModID:", result.get("modid"))
        print("Group:", result.get("group"))
        print("Package:", result.get("package"))
        print("Version:", result.get("version"))
        print("Authors:", result.get("authors"))
        print("Paths: runs_root=", result.get("runs_root"), " downloads_root=", result.get("downloads_root"), sep="")
        evt_tail = (result.get("events") or [])[-10:]
        print("Events (last 10):", evt_tail)
        print("Plan:", result.get("plan"))

        # Basic required fields are set/derived
        assert result.get("framework") == framework
        assert result.get("mc_version") == mc_version
        # Authors normalized to list
        assert isinstance(result.get("authors"), list)

        # Workspace created
        assert ws_path.exists() and ws_path.is_dir(), f"workspace_path missing: {ws_path}"

        # Gradle smoke result present and successful or, at minimum, contains structured info
        assert "task" in smoke and isinstance(smoke.get("task"), str)
        assert "log_path" in smoke and isinstance(smoke.get("log_path"), str)
        assert log_path.exists(), f"Gradle smoke log missing: {log_path}"

        # Must succeed. On failure, include helpful tail.
        if not smoke.get("ok"):
            tail = ""
            try:
                txt = log_path.read_text(encoding="utf-8")
                # show a longer tail for easier diagnosis
                tail = "\n\n--- LOG TAIL ---\n" + "\n".join(txt.splitlines()[-500:])
            except Exception:
                pass
            pytest.fail(
                f"Gradle smoke failed: framework={framework} "
                f"exit={smoke.get('exit_code')} task={smoke.get('task')} log={log_path}{tail}"
            )

        assert smoke.get("ok") is True
        # Verify template_init created expected files/folders for NeoForge
        package = (result.get("package") or "").strip()
        assert package, "package missing from result"
        base_pkg_dir = ws_path / "src" / "main" / "java" / Path(package.replace(".", "/"))
        main_class_name = "".join(p.capitalize() for p in (result.get("modid") or "mod").split("_") if p)
        main_class_path = base_pkg_dir / f"{main_class_name}.java"
        mod_items_path = base_pkg_dir / "item" / "ModItems.java"
        main_class_dir = main_class_path.parent
        mod_items_dir = mod_items_path.parent

        # Core Java files
        assert main_class_path.exists(), f"Main class not created: {main_class_path}"
        assert mod_items_path.exists(), f"ModItems.java not created: {mod_items_path}"

        # Block dir + ModBlocks + custom/
        block_dir = main_class_dir / "block"
        assert block_dir.exists() and block_dir.is_dir(), f"Missing block dir: {block_dir}"
        assert (block_dir / "ModBlocks.java").exists(), f"Missing ModBlocks.java: {block_dir / 'ModBlocks.java'}"
        assert (block_dir / "custom").exists(), f"Missing block/custom dir: {block_dir / 'custom'}"

        # Datagen folder under main class dir
        assert (main_class_dir / "datagen").exists(), f"Missing datagen dir: {main_class_dir / 'datagen'}"

        # util/ModTags.java
        assert (main_class_dir / "util" / "ModTags.java").exists(), f"Missing util/ModTags.java"

        # ModItems side: custom/FuelItem.java and ModFoodProperties.java
        assert (mod_items_dir / "custom" / "FuelItem.java").exists(), f"Missing custom/FuelItem.java"
        assert (mod_items_dir / "ModFoodProperties.java").exists(), f"Missing ModFoodProperties.java"

        # Resource dirs: assets/<modid>/lang and textures/{block,item}
        assets_root = ws_path / "src" / "main" / "resources" / "assets" / modid
        assert (assets_root / "lang").exists(), f"Missing assets lang dir: {assets_root / 'lang'}"
        assert (assets_root / "textures" / "block").exists(), f"Missing textures/block dir"
        assert (assets_root / "textures" / "item").exists(), f"Missing textures/item dir"


    finally:

        # Persist artifacts even if assertions failed above
        try:
            artifacts_root.mkdir(parents=True, exist_ok=True)
            if ws_path.exists():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(ws_path, dest)
                print(f"[artifact] Saved workspace snapshot to: {dest}")
            else:
                print(f"[artifact] Workspace path does not exist, nothing to copy: {ws_path}")

            # Save the smoke log for convenience (also lives inside workspace, but duplicate here)
            if log_path and log_path.exists():
                dest_logs = dest / "_mm_logs"
                dest_logs.mkdir(parents=True, exist_ok=True)
                shutil.copy2(log_path, dest_logs / log_path.name)
                print(f"[artifact] Saved smoke log to: {dest_logs / log_path.name}")
            else:
                print(f"[artifact] No smoke log to copy: {log_path}")

            # Also dump a tiny run manifest for quick context
            manifest = dest / "_run_info.txt"
            with open(manifest, "w", encoding="utf-8") as fh:
                fh.write(
                    f"framework={framework}\n"
                    f"mc_version={mc_version}\n"
                    f"modid={modid}\n"
                    f"workspace_path={ws_path}\n"
                    f"log_path={log_path}\n"
                    f"smoke_ok={bool(smoke.get('ok'))}\n"
                    f"task={smoke.get('task')}\n"
                    f"exit_code={smoke.get('exit_code')}\n"
                )
            print(f"[artifact] Wrote manifest: {manifest}")
        except Exception as e:
            print(f"[artifact] Failed to save artifacts: {e}")
