from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List

from backend.agent.state import AgentState
from backend.agent.tools.verify.gradle_verify import verify_gradle_sequence
from backend.agent.tools.verify.error_parsing import triage_for_task
from backend.agent.tools.verify.code_context import extract_snippet
from backend.agent.tools.verify.apply_patch import apply_edits
from backend.agent.providers.verify_error_fixer import build_error_fixer
from backend.agent.tools.verify.verify_logger import log_text, log_json, log_exception


def verify_task(state: AgentState) -> AgentState:
    """Verify the generated project by running Gradle commands and attempt auto-fixes.

    Steps (stop on first failure):
      1) ./gradlew compileJava
      2) ./gradlew runData
      3) ./gradlew runClient (smoke: detect startup in logs, then stop)

    On failure: prepare a compact triage payload, extract code snippets, ask GPT‑5
    for minimal edits, apply them, and retry. Up to 3 GPT‑5 calls; on persistent
    failure, summarize and stop.
    """
    print("[ENTER] node:verify_task")
    try:
        log_text(ws := Path(state.get("workspace_path") or "").resolve(), "ENTER verify_task")
    except Exception:
        pass

    ws = Path(state.get("workspace_path") or "").resolve()
    task = state.get("current_task") or {}
    tid = task.get("id", "unknown")

    # Guard: require workspace
    if not str(ws) or not ws.exists():
        v = state.setdefault("verification", {})
        v["ok"] = False
        v.setdefault("by_task", {})[tid] = {"ok": False, "reason": "workspace missing"}
        state.setdefault("events", []).append({"node": "verify_task", "ok": False, "task_id": tid, "reason": "no_workspace"})
        return state

    fixer = build_error_fixer()
    try:
        log_text(ws, "Built error fixer runnable" if fixer is not None else "Error fixer unavailable")
    except Exception:
        pass
    total_calls = 0
    attempts = 0
    v = state.setdefault("verification", {})

    while attempts < 3:
        attempts += 1
        seq = verify_gradle_sequence(ws)
        try:
            log_json(ws, "VERIFY_SEQUENCE_RESULT", seq)
        except Exception:
            pass
        v["ok"] = bool(seq.get("ok"))
        v.setdefault("by_task", {})[tid] = seq
        if seq.get("ok"):
            state.setdefault("events", []).append({"node": "verify_task", "ok": True, "task_id": tid, "attempts": attempts, "api_calls": total_calls})
            return state

        # First error from this run
        first = seq.get("first_error") or {}
        failed_task = str(first.get("task", ""))
        stdout = first.get("stdout", "")
        stderr = first.get("stderr", "")

        triage = triage_for_task(failed_task, stdout, stderr)
        try:
            log_json(ws, "TRIAGE", {"task": failed_task, **triage})
        except Exception:
            pass

        # Extract code around compile errors (first per file)
        code_snippets: List[Dict[str, Any]] = []
        if triage.get("type") == "compile":
            for err in (triage.get("errors") or [])[:3]:
                path = str(err.get("path", ""))
                line = int(err.get("line", 1) or 1)
                # Normalize to workspace-relative if absolute
                try:
                    p = Path(path)
                    if p.is_absolute():
                        try:
                            path = str(p.relative_to(ws))
                        except Exception:
                            path = str(p)
                except Exception:
                    pass
                snippet = extract_snippet(ws, path, line, context=6)
                code_snippets.append(snippet)

        # If no fixer available, break with summary
        if fixer is None:
            try:
                log_text(ws, "Fixer unavailable; aborting auto-fix loop")
            except Exception:
                pass
            break

        payload = {
            "command": f"./gradlew {failed_task}",
            "error_type": triage.get("type", "unknown"),
            "mc_version": state.get("mc_version") or "1.21.1",
            "neoforge_version": None,
            "java_version": "21",
            "errors": triage.get("errors") or [],
            "stack_head": triage.get("stack_head") or [],
            "caused_by": triage.get("caused_by") or [],
            "resource_lines": triage.get("resource_lines") or [],
            "code_snippets": code_snippets,
        }

        try:
            log_json(ws, "LLM_FIX_PAYLOAD", payload)
        except Exception:
            pass
        try:
            fix_out: Dict[str, Any] = fixer.invoke(payload)  # {'explanation': str, 'edits': [..]}
            total_calls += 1
            try:
                log_json(ws, "LLM_FIX_RESPONSE", fix_out)
            except Exception:
                pass
        except Exception as e:
            fix_out = {"explanation": "", "edits": []}
            try:
                log_exception(ws, "LLM_FIX_INVOKE", e)
            except Exception:
                pass

        edits = list(fix_out.get("edits") or [])
        if not edits:
            # No edits proposed; cannot proceed further
            break

        # Apply edits
        apply_res = apply_edits(ws, edits)
        try:
            log_json(ws, "APPLY_EDITS_RESULT", apply_res)
        except Exception:
            pass
        v.setdefault("applied_fixes", []).append({
            "attempt": attempts,
            "edits": edits,
            "apply_result": apply_res,
        })
        # Loop will retry verification after applying edits

    # If we reach here, still failing after attempts
    # Prepare a concise summary for the agent to show
    seq = v.get("by_task", {}).get(tid, {})
    first = seq.get("first_error") or {}
    failed_task = str(first.get("task", ""))
    stdout = first.get("stdout", "")
    stderr = first.get("stderr", "")
    triage = triage_for_task(failed_task, stdout, stderr)

    summary_lines: List[str] = []
    summary_lines.append(f"Verification failed on {failed_task} after {attempts} attempt(s) and {total_calls} GPT-5 call(s).")
    etype = triage.get("type", "unknown")
    summary_lines.append(f"Type: {etype}")
    if etype == "compile":
        errs = triage.get("errors") or []
        for e in errs[:2]:
            summary_lines.append(f"{e.get('path')}:{e.get('line')} - {e.get('message')}")
    else:
        for ln in (triage.get("stack_head") or [])[:5]:
            summary_lines.append(ln)
        for ln in (triage.get("caused_by") or [])[:3]:
            summary_lines.append(ln)

    state["summary"] = "\n".join(summary_lines)
    try:
        log_json(ws, "FINAL_SUMMARY", {"failed_task": failed_task, "summary": state["summary"]})
    except Exception:
        pass
    state.setdefault("events", []).append({"node": "verify_task", "ok": False, "task_id": tid, "failed_task": failed_task, "attempts": attempts, "api_calls": total_calls})
    return state
