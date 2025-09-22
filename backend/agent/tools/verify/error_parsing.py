from __future__ import annotations

"""
Error parsing utilities for Gradle verify steps.

Extracts succinct error payloads suitable for GPT-5 triage, per error type:
- compileJava: first error per file (path, line, message)
- runData: stack head (10-20 lines) and all 'Caused by:' lines
- runClient: top of stack trace in user code, 'Caused by:' lines, and missing resource lines
"""

import re
from typing import Dict, Any, List, Tuple

_COMPILE_RE = re.compile(r"^(?P<path>.+\.java):(\s?)(?P<line>\d+):\s+error:\s+(?P<msg>.+)$")
_MISSING_RES_RE = re.compile(r"(Unable to load|Could(n't| not) load|Missing)\s+(texture|model|registry|recipe).*?(?P<res>[a-z0-9_\-.:/]+)", re.IGNORECASE)
_CAUSED_BY_RE = re.compile(r"^Caused by: .+$")
_STACK_LINE_RE = re.compile(r"^\s*at\s+([a-zA-Z0-9_$.]+)\(([^)]+)\)")


def parse_compile_errors(text: str) -> List[Dict[str, Any]]:
    """Return first error per file: {path, line, message}."""
    print("[ENTER] tool:error_parsing.parse_compile_errors")
    errors: Dict[str, Dict[str, Any]] = {}
    for line in (text or "").splitlines():
        m = _COMPILE_RE.match(line.strip())
        if not m:
            continue
        path = m.group("path")
        if path in errors:
            continue
        errors[path] = {
            "path": path,
            "line": int(m.group("line")),
            "message": m.group("msg").strip(),
        }
    return list(errors.values())


def parse_stack_head(text: str, max_lines: int = 20) -> List[str]:
    print("[ENTER] tool:error_parsing.parse_stack_head")
    lines = (text or "").splitlines()
    head: List[str] = []
    in_stack = False
    for ln in lines:
        if ln.strip().startswith(("Exception", "java.", "net.", "org.")) and "Exception" in ln and not head:
            in_stack = True
        if in_stack:
            head.append(ln)
            if len(head) >= max_lines:
                break
    return head


def collect_caused_by(text: str) -> List[str]:
    print("[ENTER] tool:error_parsing.collect_caused_by")
    return [ln for ln in (text or "").splitlines() if _CAUSED_BY_RE.match(ln.strip())]


def parse_missing_resources(text: str) -> List[str]:
    print("[ENTER] tool:error_parsing.parse_missing_resources")
    out: List[str] = []
    for ln in (text or "").splitlines():
        m = _MISSING_RES_RE.search(ln)
        if m:
            out.append(ln.strip())
    return out


def triage_for_task(task: str, stdout: str, stderr: str) -> Dict[str, Any]:
    """Return a compact triage payload based on task type."""
    print(f"[ENTER] tool:error_parsing.triage_for_task task={task}")
    combined = (stdout or "") + "\n" + (stderr or "")
    t = task.strip()
    if t == "compileJava":
        comp = parse_compile_errors(combined)
        return {"type": "compile", "errors": comp[:5], "raw_excerpt": combined[:4000]}
    if t == "runData":
        head = parse_stack_head(combined)
        caused = collect_caused_by(combined)
        return {"type": "datagen", "stack_head": head, "caused_by": caused, "raw_excerpt": combined[:6000]}
    if t == "runClient":
        head = parse_stack_head(combined)
        caused = collect_caused_by(combined)
        missing = parse_missing_resources(combined)
        return {"type": "runtime", "stack_head": head, "caused_by": caused, "resource_lines": missing, "raw_excerpt": combined[:8000]}
    return {"type": "unknown", "raw_excerpt": combined[:4000]}


__all__ = [
    "parse_compile_errors",
    "parse_stack_head",
    "collect_caused_by",
    "parse_missing_resources",
    "triage_for_task",
]

