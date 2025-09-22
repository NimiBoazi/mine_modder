from __future__ import annotations

"""
Apply simple code edits proposed by GPT-5 during verify.

Supported edit schema (line-based, 1-based):
- Replace range:
{
  "path": "src/main/java/.../File.java",
  "action": "replace_range",
  "start_line": 10,
  "end_line": 15,
  "new_code": "...multi-line string..."
}
- Insert at a position (before the given line index):
{
  "path": "src/main/java/.../File.java",
  "action": "insert",
  "at_line": 10,
  "new_code": "...multi-line string..."
}

Notes
- Lines are 1-based. For insert: at_line may be len(file)+1 to append at end.
- All paths are interpreted as workspace-relative. Files outside the workspace are rejected.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Tuple

from backend.agent.wrappers.storage import STORAGE as storage


@dataclass
class EditResult:
    path: str
    ok: bool
    reason: str | None = None
    start_line: int | None = None
    end_line: int | None = None


def _apply_replace_range(ws: Path, rel_path: str, start_line: int, end_line: int, new_code: str) -> EditResult:
    print(f"[ENTER] tool:apply_patch._apply_replace_range path={rel_path} start={start_line} end={end_line}")
    target = (ws / rel_path).resolve()
    # Ensure target is inside workspace
    try:
        ws_res = ws.resolve()
        if not str(target).startswith(str(ws_res)):
            print("[PATCH] rejected: outside_workspace")
            return EditResult(rel_path, False, "outside_workspace")
    except Exception:
        print("[PATCH] rejected: resolve_failed")
        return EditResult(rel_path, False, "resolve_failed")

    if not storage.exists(target):
        print("[PATCH] rejected: file_not_found")
        return EditResult(rel_path, False, "file_not_found")

    try:
        text = storage.read_text(target)
        lines = text.splitlines()
        n = len(lines)
        s = max(1, int(start_line))
        e = min(n, int(end_line))
        if s > e or s < 1 or e > n:
            print("[PATCH] rejected: invalid_range")
            return EditResult(rel_path, False, "invalid_range", s, e)
        before = lines[: s - 1]
        after = lines[e:]
        replacement = (new_code or "").splitlines()
        new_lines = before + replacement + after
        storage.write_text(target, "\n".join(new_lines) + ("" if text.endswith("\n") else ""))
        print(f"[PATCH] applied lines {s}-{e} -> {rel_path}")
        return EditResult(rel_path, True, None, s, e)
    except Exception as e:
        print(f"[PATCH] exception: {e}")
        return EditResult(rel_path, False, f"exception:{e}")


def _apply_insert(ws: Path, rel_path: str, at_line: int, new_code: str) -> EditResult:
    print(f"[ENTER] tool:apply_patch._apply_insert path={rel_path} at={at_line}")
    target = (ws / rel_path).resolve()
    try:
        ws_res = ws.resolve()
        if not str(target).startswith(str(ws_res)):
            print("[PATCH] rejected: outside_workspace")
            return EditResult(rel_path, False, "outside_workspace")
    except Exception:
        print("[PATCH] rejected: resolve_failed")
        return EditResult(rel_path, False, "resolve_failed")

    if not storage.exists(target):
        print("[PATCH] rejected: file_not_found")
        return EditResult(rel_path, False, "file_not_found")

    try:
        text = storage.read_text(target)
        lines = text.splitlines()
        n = len(lines)
        pos = int(at_line)
        if pos < 1 or pos > n + 1:
            print("[PATCH] rejected: invalid_insert_position")
            return EditResult(rel_path, False, "invalid_insert_position", pos, pos)
        before = lines[: pos - 1]
        after = lines[pos - 1:]
        insertion = (new_code or "").splitlines()
        new_lines = before + insertion + after
        storage.write_text(target, "\n".join(new_lines) + ("" if text.endswith("\n") else ""))
        print(f"[PATCH] inserted at line {pos} -> {rel_path}")
        return EditResult(rel_path, True, None, pos, pos)
    except Exception as e:
        print(f"[PATCH] exception: {e}")
        return EditResult(rel_path, False, f"exception:{e}")


def apply_edits(workspace: str | Path, edits: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply a list of edits. Returns summary with per-edit results.

    Returns:
    {
      ok: bool,
      applied: int,
      results: [ {path, ok, reason?, start_line?, end_line?} ... ]
    }
    """
    print(f"[ENTER] tool:apply_patch.apply_edits count={len(edits or [])}")
    ws = Path(workspace)
    results: List[Dict[str, Any]] = []
    applied = 0
    for ed in (edits or []):
        action = (ed.get("action") or "").strip()
        rel = ed.get("path") or ""
        try:
            if action == "replace_range":
                r = _apply_replace_range(ws, rel, int(ed.get("start_line", 1)), int(ed.get("end_line", 0)), ed.get("new_code", ""))
            elif action == "insert":
                r = _apply_insert(ws, rel, int(ed.get("at_line", 1)), ed.get("new_code", ""))
            else:
                print(f"[PATCH] unsupported action for {rel}: {action}")
                results.append({"path": rel, "ok": False, "reason": "unsupported_action"})
                continue
            results.append({
                "path": r.path,
                "ok": r.ok,
                "reason": r.reason,
                "start_line": r.start_line,
                "end_line": r.end_line,
            })
            if r.ok:
                applied += 1
        except Exception as e:
            print(f"[PATCH] exception while applying to {rel}: {e}")
            results.append({"path": rel, "ok": False, "reason": f"exception:{e}"})
    return {"ok": applied == len(edits or []), "applied": applied, "results": results}


__all__ = ["apply_edits"]

