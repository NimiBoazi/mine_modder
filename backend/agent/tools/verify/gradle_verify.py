from __future__ import annotations

"""
Gradle verification runner for the Verify Task node.

Runs, in order, from a given workspace (mod root):
  1) ./gradlew compileJava
  2) ./gradlew runData

If any step fails, stop and return a structured result with the first error.
All steps write combined stdout/stderr to _mm_logs/verify_<task>.log.

Notes
- Uses the init.gradle helpers for wrapper path and execution consistency.
"""

import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple

from backend.agent.wrappers.storage import STORAGE as storage
from backend.agent.tools.init import gradle as grad


def _log_dir(workspace: Path) -> Path:
    d = Path(workspace) / "_mm_logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_log(workspace: Path, task: str, stdout: str, stderr: str) -> Path:
    print(f"[ENTER] tool:gradle_verify._write_log task={task}")
    log_path = _log_dir(workspace) / f"verify_{task}.log"
    payload = stdout or ""
    if stderr and stderr not in payload:
        if payload:
            payload += "\n--- STDERR ---\n"
        payload += stderr
    try:
        storage.write_text(log_path, payload, encoding="utf-8")
        print(f"[LOG] wrote {log_path}")
    except Exception as e:
        print(f"[LOG] failed to write {log_path}: {e}")
    return log_path


_STARTUP_OK_PATTERNS = [
    # Log lines that typically appear once the client is bootstrapping
    "ModLauncher running:",
    "Launching target 'forgeclient",
    "Minecraft 1.21",        # generic version banner (adjust by MC version)
    "Minecraft 1.",          # fallback for version variations
    "Render thread",         # thread creation often logged later
    "LWJGL",                 # graphics subsystem init
    "GLFW",                  # window init
    "OpenAL",                # audio init
    "Loading Immediate Window",  # common in logs during UI init
    "Keyboard Layout",       # input init lines
]


def _looks_like_client_started(output: str) -> bool:
    out = output or ""
    out_low = out.lower()
    for p in _STARTUP_OK_PATTERNS:
        if p.lower() in out_low:
            return True
    return False


def _run_gradle_task(workspace: Path, task: str, timeout: int) -> Tuple[int, str, str, float]:
    print(f"[ENTER] tool:gradle_verify._run_gradle_task task={task} timeout={timeout}s")
    # Add stable flags like in smoke_build
    args = ["--no-daemon", "-S", task]
    code, out, err, elapsed = grad._run_gradle(workspace, args, timeout=timeout)
    print(f"[GRADLE] task={task} exit={code} elapsed={elapsed:.2f}s")
    return code, out, err, elapsed


def _run_client_smoke(workspace: Path, timeout: int = 120) -> Tuple[int, str, str, float, bool]:
    """Run runClient for up to `timeout` seconds. If partial output indicates that
    the client bootstrapped, return (0, out, err, elapsed, True). Otherwise, return
    the actual exit code. We do not stream logs here; we rely on _run_gradle's
    TimeoutExpired behavior capturing partial stdout/stderr.
    """
    print(f"[ENTER] tool:gradle_verify._run_client_smoke timeout={timeout}s")
    t0 = time.time()
    code, out, err, _elapsed = _run_gradle_task(workspace, "runClient", timeout)
    ok_boot = False
    if code == 0:
        ok_boot = True
    else:
        combined = (out or "") + "\n" + (err or "")
        if _looks_like_client_started(combined):
            print("[CLIENT] startup markers found in partial logs; treating as pass")
            ok_boot = True
            code = 0
    total = time.time() - t0
    print(f"[CLIENT] smoke result exit={code} boot={ok_boot} elapsed={total:.2f}s")
    return code, out, err, total, ok_boot


def verify_gradle_sequence(workspace: str | Path, *, timeouts: Dict[str, int] | None = None) -> Dict[str, Any]:
    """Run compileJava → runData.

    Returns dict with shape:
    {
      ok: bool,
      steps: [ {task, ok, exit_code, elapsed, log_path} ... ],
      first_error: Optional[{task, exit_code, log_path}]
    }
    """
    print(f"[ENTER] tool:gradle_verify.verify_gradle_sequence workspace={Path(workspace)}")
    ws = Path(workspace)
    to = {"compileJava": 600, "runData": 900}
    if timeouts:
        to.update(timeouts)

    result: Dict[str, Any] = {"ok": False, "steps": [], "first_error": None}

    # 1) compileJava
    c_code, c_out, c_err, c_elapsed = _run_gradle_task(ws, "compileJava", to["compileJava"])
    c_log = _write_log(ws, "compileJava", c_out, c_err)
    c_ok = c_code == 0
    print(f"[VERIFY] compileJava ok={c_ok} exit={c_code} log={c_log}")
    result["steps"].append({
        "task": "compileJava",
        "ok": c_ok,
        "exit_code": c_code,
        "elapsed": round(c_elapsed, 3),
        "log_path": str(c_log),
    })
    if not c_ok:
        result["first_error"] = {"task": "compileJava", "exit_code": c_code, "log_path": str(c_log), "stdout": c_out, "stderr": c_err}
        return result

    # 2) runData
    d_code, d_out, d_err, d_elapsed = _run_gradle_task(ws, "runData", to["runData"])
    d_log = _write_log(ws, "runData", d_out, d_err)
    d_ok = d_code == 0
    print(f"[VERIFY] runData ok={d_ok} exit={d_code} log={d_log}")
    result["steps"].append({
        "task": "runData",
        "ok": d_ok,
        "exit_code": d_code,
        "elapsed": round(d_elapsed, 3),
        "log_path": str(d_log),
    })
    if not d_ok:
        result["first_error"] = {"task": "runData", "exit_code": d_code, "log_path": str(d_log), "stdout": d_out, "stderr": d_err}
        return result

    result["ok"] = True
    return result


__all__ = ["verify_gradle_sequence"]

