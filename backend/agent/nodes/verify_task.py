from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
import re
import json

from langchain_core.runnables import Runnable

from backend.agent.state import AgentState
from backend.agent.tools.verify.gradle_verify import verify_gradle_sequence
from backend.agent.tools.verify.apply_patch import apply_edits
from backend.agent.wrappers.utils import insert_between_anchors_text, normalize_import_block
from backend.agent.providers.verify_simple_fixers import (
    build_import_line_fixer,
    build_line_replacement_fixer,
)
from backend.agent.providers.paths import detect_neoforge_version, java_src_root

from backend.agent.tools.verify.verify_logger import log_text, log_json, log_exception
from backend.agent.wrappers.storage import STORAGE as storage


def verify_task(state: AgentState) -> AgentState:
    """Delegate to the simplified verifier implementation below."""
    return simple_verify_task(state)

# --- Simple reworked verify node (does not use old analyzer/fixer) ---

def _extract_first_java_error_path(stdout: str, stderr: str) -> tuple[str | None, int | None]:
    text = (stderr or "") + "\n" + (stdout or "")
    # Allow spaces and broader characters in paths (e.g., "/Users/.../Year C/.../File.java:123: error:")
    m = re.search(r"(.+?\.java):\s*(\d+):\s*error:", text)
    if m:
        return m.group(1), int(m.group(2))
    return None, None


def _is_import_error(stdout: str, stderr: str) -> bool:
    s = (stdout or "") + "\n" + (stderr or "")
    s_low = s.lower()
    if "package" in s_low and "does not exist" in s_low:
        return True
    if "cannot find symbol" in s_low:
        return True
    if "cannot be resolved to a type" in s_low:
        return True
    return False


def _build_error_excerpt_simple(stdout: str, stderr: str, max_chars: int = 3000) -> str:
    lines_err = (stderr or "").splitlines()
    lines_out = (stdout or "").splitlines()
    sections: list[str] = []
    # Compiler lines first
    comp_re = re.compile(r".+\.java:\s*\d+:\s*error:\s*.+")
    comp_lines = [ln for ln in lines_err if comp_re.search(ln)] or [ln for ln in lines_out if comp_re.search(ln)]
    if comp_lines:
        sections.append("[Compiler Errors]")
        sections.extend(comp_lines[:50])
    # What went wrong
    def _what(lines: list[str]) -> list[str]:
        try:
            i = next(j for j, ln in enumerate(lines) if ln.strip().lower().startswith("* what went wrong"))
        except StopIteration:
            return []
        return ["[What went wrong]"] + lines[i:i+40]
    blk = _what(lines_err) or _what(lines_out)
    if blk:
        sections.extend(blk)
    # Tail of stderr
    tail_err = lines_err[-50:]
    if tail_err:
        sections.append("[Stderr Tail]")
        sections.extend(tail_err)
    txt = "\n".join(sections)
    return txt[:max_chars]


def simple_verify_task(state: AgentState) -> AgentState:
    print("[ENTER] node:simple_verify_task")
    ws = Path(state.get("workspace_path") or "").resolve()
    task = state.get("current_task") or {}
    tid = task.get("id", "unknown")

    # Guard
    if not str(ws) or not ws.exists():
        v = state.setdefault("verification", {})
        v["ok"] = False
        v.setdefault("by_task", {})[tid] = {"ok": False, "reason": "workspace missing"}
        state.setdefault("events", []).append({"node": "verify_task", "ok": False, "task_id": tid, "reason": "no_workspace"})
        return state
    # Build environment context for LLM fixers
    framework = (state.get("framework") or "").strip().lower()
    eff_mc = (state.get("effective_mc_version") or state.get("mc_version") or "").strip()
    nf_version = None
    try:
        if framework == "neoforge":
            nf_version = detect_neoforge_version(ws)
    except Exception:
        nf_version = None
    parts: list[str] = []
    if eff_mc:
        parts.append(f"Minecraft {eff_mc}")
    if framework:
        parts.append(framework.capitalize())
    if framework == "neoforge":
        parts.append(f"NeoForge {nf_version}" if nf_version else "NeoForge")
    env_context = ", ".join(parts) if parts else "Minecraft (version unknown)"


    # Build minimal fixers
    import_fixer: Optional[Runnable] = build_import_line_fixer()
    line_fixer: Optional[Runnable] = build_line_replacement_fixer()

    v = state.setdefault("verification", {})
    attempts = 0

    try:
        log_text(ws, f"SIMPLE_VERIFY_START task={tid}")
        log_json(ws, "ENV_CONTEXT", {"env_context": env_context})
    except Exception:
        pass

    while attempts <= 2:  # 0 = initial run, 1..2 = fix attempts
        try:
            log_text(ws, f"SIMPLE_VERIFY_ATTEMPT {attempts}")
        except Exception:
            pass
        seq = verify_gradle_sequence(ws)
        try:
            log_json(ws, "SIMPLE_VERIFY_SEQUENCE_RESULT", seq)
        except Exception:
            pass
        v["ok"] = bool(seq.get("ok"))
        v.setdefault("by_task", {})[tid] = seq
        if seq.get("ok"):
            try:
                log_text(ws, f"SIMPLE_VERIFY_SUCCESS attempts={attempts}")
            except Exception:
                pass
            state.setdefault("events", []).append({"node": "verify_task", "ok": True, "task_id": tid, "attempts": attempts})
            return state

        if attempts == 2:
            try:
                log_text(ws, "SIMPLE_VERIFY_MAX_ATTEMPTS_REACHED")
            except Exception:
                pass
            break  # reached max fix attempts

        # Get first failure info
        first = seq.get("first_error") or {}
        stdout = first.get("stdout", "")
        stderr = first.get("stderr", "")

        # Attempt to locate a Java file path, using strict, transparent rules
        rel_path, _ = _extract_first_java_error_path(stdout, stderr)
        search_root = java_src_root(ws)
        resolution_notes: list[str] = []
        target: Path | None = None
        try:
            if rel_path:
                rp = str(rel_path).strip().strip('"').strip("'")
                p = Path(rp)
                if p.is_absolute():
                    resolution_notes.append("strategy=absolute_path_from_gradle")
                    try:
                        # Prefer workspace-relative if under ws
                        rel_to_ws = p.relative_to(ws)
                        target = ws / rel_to_ws
                        resolution_notes.append(f"relativized_to_ws={rel_to_ws}")
                    except Exception:
                        target = p
                        resolution_notes.append("kept_absolute_outside_ws")
                else:
                    # Relative path from Gradle. Normalize against ws or java src root.
                    if rp.startswith(str(Path("src") / "main" / "java")):
                        target = ws / p
                        resolution_notes.append("strategy=ws_join_src_main_java_path")
                    else:
                        # Treat as path relative to the java source root (handles package subdirs)
                        candidate = search_root / p
                        if storage.exists(candidate):
                            target = candidate
                            resolution_notes.append("strategy=java_src_root_relative")
                        else:
                            # If only a filename was provided (no dirs), do a strict filename search under java src
                            if len(p.parts) == 1:
                                matches = list(storage.rglob(search_root, f"**/{rp}"))
                                if len(matches) == 1:
                                    target = matches[0]
                                    resolution_notes.append("strategy=filename_recursive_unique_match")
                                elif len(matches) == 0:
                                    resolution_notes.append("filename_recursive_no_match")
                                else:
                                    # Ambiguous; report and fail
                                    sample = ", ".join(str(m.relative_to(ws)) for m in matches[:5])
                                    msg = (
                                        f"[ERROR] Ambiguous filename match for verification fix.\n"
                                        f"- workspace: {ws}\n"
                                        f"- extracted_path: {rp}\n"
                                        f"- search_root: {search_root}\n"
                                        f"- matches({len(matches)}): {sample}{'...' if len(matches)>5 else ''}"
                                    )
                                    print(msg)
                                    try:
                                        log_text(ws, msg)
                                    except Exception:
                                        pass
                                    raise FileNotFoundError(msg)
                            else:
                                resolution_notes.append("java_src_root_relative_missing")
        except Exception:
            target = None
        target_exists = storage.exists(target) if (target is not None) else False
        # Keep a clean, printable relative path for logs/payloads
        rel_path = (str(Path(str(rel_path).strip().strip('"').strip("'"))) if rel_path else None)
        if target_exists:
            try:
                log_text(ws, f"SIMPLE_VERIFY_TARGET path={rel_path} notes={'|'.join(resolution_notes)}")
            except Exception:
                pass
        else:
            msg = (
                f"[ERROR] Target file not found for verification fix.\n"
                f"- workspace: {ws}\n"
                f"- extracted_path: {rel_path or '(unknown)'}\n"
                f"- resolved_path: {str(target) if target is not None else '(None)'}\n"
                f"- search_root: {search_root}\n"
                f"- notes: {'|'.join(resolution_notes) or '(none)'}\n"
            )
            print(msg)
            try:
                log_text(ws, msg)
            except Exception:
                pass
            raise FileNotFoundError(msg)

        applied_fix = False

        # Always attempt line-by-line LLM fix for any error
        try:
            if (target is None) or (not target_exists):
                msg = (
                    f"[ERROR] Cannot read target file for fixer.\n"
                    f"- workspace: {ws}\n"
                    f"- extracted_path: {rel_path or '(unknown)'}\n"
                    f"- resolved_path: {str(target) if target is not None else '(None)'}\n"
                    f"No fallback resolution attempted."
                )
                print(msg)
                try:
                    log_text(ws, msg)
                except Exception:
                    pass
                raise FileNotFoundError(msg)
            file_content = storage.read_text(target, encoding="utf-8", errors="ignore")
            payload2 = {
                "env_context": env_context,
                "error_excerpt": _build_error_excerpt_simple(stdout, stderr),
                "file_path": str(rel_path or "(unknown)"),
                "file_content": file_content,
            }
            try:
                log_json(ws, "LINE_FIXER_REQUEST", payload2)
            except Exception:
                pass
            raw = str(line_fixer.invoke(payload2) or "").strip()
            try:
                log_text(ws, f"LINE_FIXER_RESPONSE_RAW: {raw[:1200]}")
                log_json(ws, "LINE_FIXER_RESPONSE", {"raw": raw})
            except Exception:
                pass
            # Expect JSON array
            edits_list: List[Dict[str, Any]] = []
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    for obj in parsed:
                        if not isinstance(obj, dict):
                            continue
                        old_l = obj.get("old line")
                        new_l = obj.get("new line")
                        if isinstance(old_l, str) and isinstance(new_l, str):
                            edits_list.append({
                                "path": str(rel_path or ""),
                                "action": "replace_line",
                                "old_line": old_l,
                                "new_line": new_l,
                            })
            except Exception:
                # Not valid JSON -> skip
                edits_list = []
            if edits_list:
                try:
                    log_json(ws, "LINE_FIXER_PARSED_EDITS", edits_list)
                except Exception:
                    pass
                if target_exists:
                    res = apply_edits(ws, edits_list)
                    try:
                        log_json(ws, "SIMPLE_APPLY_EDITS", res)
                    except Exception:
                        pass
                    if res.get("applied", 0) > 0:
                        v.setdefault("applied_fixes", []).append({
                            "attempt": attempts + 1,
                            "edits": edits_list,
                            "apply_result": res,
                        })
                        applied_fix = True
                else:
                    try:
                        log_text(ws, "SIMPLE_NO_TARGET_FILE_TO_APPLY")
                    except Exception:
                        pass
        except Exception as e:
            try:
                log_exception(ws, "SIMPLE_LINE_FIX", e)
            except Exception:
                pass

        # Continue with attempts
        if (not applied_fix):
            if line_fixer is None:
                try:
                    log_text(ws, "SIMPLE_LINE_FIXER_NOT_AVAILABLE")
                except Exception:
                    pass
            else:
                try:
                    if (target is None) or (not storage.exists(target)):
                        msg = (
                            f"[ERROR] Cannot read target file for fixer (second attempt).\n"
                            f"- workspace: {ws}\n"
                            f"- extracted_path: {rel_path or '(unknown)'}\n"
                            f"- resolved_path: {str(target) if target is not None else '(None)'}\n"
                            f"No fallback resolution attempted."
                        )
                        print(msg)
                        try:
                            log_text(ws, msg)
                        except Exception:
                            pass
                        raise FileNotFoundError(msg)
                    file_content = storage.read_text(target, encoding="utf-8", errors="ignore")
                    payload2 = {
                        "env_context": env_context,
                        "error_excerpt": _build_error_excerpt_simple(stdout, stderr),
                        "file_path": str(rel_path or "(unknown)"),
                        "file_content": file_content,
                    }
                    try:
                        log_json(ws, "LINE_FIXER_REQUEST", payload2)
                    except Exception:
                        pass
                    raw = str(line_fixer.invoke(payload2) or "").strip()
                    try:
                        log_text(ws, f"LINE_FIXER_RESPONSE_RAW: {raw[:1200]}")
                        log_json(ws, "LINE_FIXER_RESPONSE", {"raw": raw})
                    except Exception:
                        pass
                    # Expect JSON array
                    edits_list: List[Dict[str, Any]] = []
                    try:
                        parsed = json.loads(raw)
                        if isinstance(parsed, list):
                            for obj in parsed:
                                if not isinstance(obj, dict):
                                    continue
                                old_l = obj.get("old line")
                                new_l = obj.get("new line")
                                if isinstance(old_l, str) and isinstance(new_l, str):
                                    edits_list.append({
                                        "path": str(rel_path),
                                        "action": "replace_line",
                                        "old_line": old_l,
                                        "new_line": new_l,
                                    })
                    except Exception:
                        # Not valid JSON -> skip
                        edits_list = []
                    if edits_list:
                        try:
                            log_json(ws, "LINE_FIXER_PARSED_EDITS", edits_list)
                        except Exception:
                            pass
                        res = apply_edits(ws, edits_list)
                        try:
                            log_json(ws, "SIMPLE_APPLY_EDITS", res)
                        except Exception:
                            pass
                        if res.get("applied", 0) > 0:
                            v.setdefault("applied_fixes", []).append({
                                "attempt": attempts + 1,
                                "edits": edits_list,
                                "apply_result": res,
                            })
                            applied_fix = True
                except Exception as e:
                    try:
                        log_exception(ws, "SIMPLE_LINE_FIX", e)
                    except Exception:
                        pass

        attempts += 1
        if not applied_fix:
            # Nothing to apply this round
            try:
                log_text(ws, "SIMPLE_VERIFY_NO_FIX_APPLIED_BREAK")
            except Exception:
                pass
            break

    # Finalize failure status
    v["ok"] = False
    v["attempts"] = attempts
    v["max_attempts_reached"] = True
    state["max_verify_attempts_reached"] = True
    state.setdefault("events", []).append({
        "node": "verify_task",
        "ok": False,
        "task_id": tid,
        "attempts": attempts,
        "max_attempts_reached": True,
    })
    return state

