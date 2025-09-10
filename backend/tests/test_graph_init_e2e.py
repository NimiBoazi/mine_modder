from __future__ import annotations

import os
from pathlib import Path
import shutil

import pytest
from dotenv import load_dotenv, find_dotenv

from backend.agent.graph import build_graph


@pytest.mark.slow
@pytest.mark.parametrize("framework,mc_version", [
    ("forge", "1.21.1"),
    ("fabric", "1.21.1"),
    ("neoforge", "1.21.1"),
])
def test_graph_init_end_to_end_all_frameworks(tmp_path: Path, framework: str, mc_version: str):
    """
    End-to-end test of the init subgraph via the LangGraph orchestration.
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

    g = build_graph()

    runs_root = tmp_path / "runs"
    downloads_root = tmp_path / "_downloads"

    state = {
        "user_input": "A mod with a sapphire block and green rain weather.",
        "framework": framework,
        "mc_version": mc_version,
        "author": "TestAuthor",
        # Use temp roots so we don't pollute repo paths
        "runs_root": str(runs_root),
        "downloads_root": str(downloads_root),
        # Keep a reasonable timeout; CI environments can be slower
        "timeout": int(os.getenv("MM_GRADLE_TIMEOUT", "1800")),
    }

    # Execute the graph (increase recursion limit to be safe for multi-node flow)
    result = g.invoke(state, config={"recursion_limit": 100})

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
