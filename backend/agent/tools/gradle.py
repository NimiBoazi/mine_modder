"""
Gradle runner (headless smoke builds)

Purpose
-------
Run the minimal Gradle task(s) to validate a freshly‑initialized workspace
without launching the game. This captures logs to disk and returns a
structured result so the agent can decide next steps.

Dev vs Prod
-----------
In dev, logs are written under the workspace folder. In production, replace the
log writer with a storage gateway that uploads logs to object storage and
returns a URI (keep the public API unchanged).

Public API
----------
- smoke_build(framework: str, workspace: Path | str, *, task_override: str | None = None,
              timeout: int = 1800, extra_args: list[str] | None = None) -> dict
    Chooses a suitable task based on framework (or uses override), runs via the
    Gradle wrapper, and returns { ok, exit_code, task, log_path, elapsed_seconds }.

Notes
-----
- Uses the project's Gradle wrapper (`gradlew` / `gradlew.bat`).
- Sets `--no-daemon` to reduce background processes.
- Adds `-S` (`--stacktrace`) to capture readable failures in logs.
- Falls back (Forge/NeoForge) from `:runData` to `build` if the first task is unknown.
"""
from __future__ import annotations

import os
import sys
import time
import platform
import subprocess
from pathlib import Path
from typing import Optional, Iterable

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


# -------------------------
# Framework → default task candidates
# -------------------------

_DEFAULT_TASKS: dict[str, list[str]] = {
    "forge": [":runData", "build"],
    "neoforge": [":runData", "build"],
    "fabric": ["build"],
}


def _config_dir() -> Path:
    env = os.environ.get("MINEMODDER_CONFIG_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "config"


def _load_task_candidates(framework: str) -> list[str]:
    """Try to read smoke task(s) from project_matrix.yaml; fallback to defaults."""
    cfg = _config_dir() / "project_matrix.yaml"
    if not cfg.exists() or yaml is None:
        return _DEFAULT_TASKS.get(framework, ["build"]).copy()
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        mapping = data.get("smoke_tasks", {})
        val = mapping.get(framework)
        if isinstance(val, str):
            return [val]
        if isinstance(val, list) and val:
            return [str(x) for x in val]
    except Exception:
        pass
    return _DEFAULT_TASKS.get(framework, ["build"]).copy()


# -------------------------
# Core execution
# -------------------------

def _gradlew_path(workspace: Path) -> Path:
    bat = workspace / "gradlew.bat"
    sh = workspace / "gradlew"
    # Always return absolute to avoid cwd+relative path issues
    return (bat if (platform.system().lower().startswith("win") and bat.exists()) else sh).resolve()



def _ensure_executable(p: Path) -> None:
    try:
        mode = p.stat().st_mode
        p.chmod(mode | 0o111)
    except Exception:
        pass


def _log_dir(workspace: Path) -> Path:
    d = workspace / "_mm_logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_gradle(workspace: Path, args: list[str], *, timeout: int) -> tuple[int, str, str, float]:
    gradlew = _gradlew_path(workspace)
    if not gradlew.exists():
        listing = "\n".join(p.name for p in workspace.iterdir())
        raise FileNotFoundError(f"Gradle wrapper not found at {gradlew}\nWorkspace listing:\n{listing}")

    _ensure_executable(gradlew)

    # Environment: make Gradle non‑interactive and stable for headless
    env = os.environ.copy()
    env.setdefault("CI", "true")

    # Windows needs shell=True for .bat sometimes; use list invocation everywhere else
    is_windows = platform.system().lower().startswith("win")
    cmd: list[str] = [str(gradlew)] + args

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workspace),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            shell=False if not is_windows else True,
        )
        elapsed = time.time() - t0
        return proc.returncode, proc.stdout, proc.stderr, elapsed
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - t0
        out = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", errors="ignore")
        err = e.stderr if isinstance(e.stderr, str) else (e.stderr or b"").decode("utf-8", errors="ignore")
        return 124, out, err + "\n[MineModder] TimeoutExpired", elapsed


# -------------------------
# Public API
# -------------------------

def smoke_build(
    framework: str,
    workspace: Path | str,
    *,
    task_override: Optional[str] = None,
    timeout: int = 1800,
    extra_args: Optional[list[str]] = None,
) -> dict:
    """Run a minimal Gradle task to validate the project.

    Returns a dict: {
        ok: bool,
        exit_code: int,
        task: str,
        tried_tasks: list[str],
        log_path: str,
        elapsed_seconds: float,
    }
    """
    ws = Path(workspace)
    fw = framework.strip().lower()

    tried: list[str] = []
    tasks = [task_override] if task_override else _load_task_candidates(fw)

    # Always include minimal flags to improve debuggability and determinism
    base_args = ["--no-daemon", "-S"]  # include stacktraces on failure
    if extra_args:
        base_args += list(extra_args)

    last_exit = 1
    last_out = ""
    last_err = ""
    elapsed = 0.0
    chosen_task = tasks[0] if tasks else "build"

    for task in tasks:
        tried.append(task)
        exit_code, out, err, elapsed = _run_gradle(ws, base_args + [task], timeout=timeout)
        last_exit, last_out, last_err = exit_code, out, err
        chosen_task = task
        # If task not found, continue to next candidate
        task_missing = "Task '" in (out + err) and "not found" in (out + err)
        if exit_code != 0 and task_missing and len(tasks) > 1:
            continue
        break

    # Write combined log
    log_dir = _log_dir(ws)
    log_path = log_dir / f"smoke_{fw}_{chosen_task.strip(':').replace(':','_')}.log"
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            if last_out:
                f.write(last_out)
            if last_err and last_err not in last_out:
                if last_out:
                    f.write("\n--- STDERR ---\n")
                f.write(last_err)
    except Exception:
        pass

    ok = last_exit == 0
    return {
        "ok": ok,
        "exit_code": last_exit,
        "task": chosen_task,
        "tried_tasks": tried,
        "log_path": str(log_path),
        "elapsed_seconds": round(elapsed, 3),
    }


__all__ = ["smoke_build"]
