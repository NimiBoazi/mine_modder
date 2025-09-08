from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv, find_dotenv

from backend.agent.graph import build_graph


@pytest.mark.slow
@pytest.mark.parametrize("framework,mc_version", [
    ("forge", "1.21"),
    ("fabric", "1.21"),
    ("neoforge", "1.21"),
])
def test_graph_init_end_to_end_all_frameworks(tmp_path: Path, framework: str, mc_version: str):
    """
    End-to-end test of the init subgraph via the LangGraph orchestration.
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
    # If you prefer to continue even without a key, replace the assert with:
    # if not has_key: pytest.skip("GOOGLE_API_KEY not set; skipping LLM-inference verification")
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
    ws_path = Path(result.get("workspace_path") or "")
    assert ws_path.exists() and ws_path.is_dir(), f"workspace_path missing: {ws_path}"

    # Gradle smoke result present and successful or, at minimum, contains structured info
    smoke = (result.get("artifacts") or {}).get("gradle_smoke") or {}
    assert "task" in smoke and isinstance(smoke.get("task"), str)
    assert "log_path" in smoke and isinstance(smoke.get("log_path"), str)
    # Log written
    log_path = Path(smoke.get("log_path"))
    assert log_path.exists(), f"Gradle smoke log missing: {log_path}"

    # Must succeed. On failure, include helpful tail.
    if not smoke.get("ok"):
        tail = ""
        try:
            txt = log_path.read_text(encoding="utf-8")
            tail = "\n\n--- LOG TAIL ---\n" + "\n".join(txt.splitlines()[-120:])
        except Exception:
            pass
        pytest.fail(
            f"Gradle smoke failed: framework={framework} "
            f"exit={smoke.get('exit_code')} task={smoke.get('task')} log={log_path}{tail}"
        )
    assert smoke.get("ok") is True
