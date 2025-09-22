from __future__ import annotations

"""
Extract code snippets around a file:line for error reporting.

Nodes should not read files directly; use this tool from verify_task.
"""

from pathlib import Path
from typing import Dict, Any, List

from backend.agent.wrappers.storage import STORAGE as storage


def extract_snippet(workspace: str | Path, rel_path: str, line: int, context: int = 6) -> Dict[str, Any]:
    """Return a dict with a small code excerpt around `line` (1-based).
    If file does not exist, returns an empty snippet with exists=False.
    """
    print(f"[ENTER] tool:code_context.extract_snippet path={rel_path} line={line} ctx={context}")
    ws = Path(workspace)
    file_path = (ws / rel_path).resolve()
    if not storage.exists(file_path):
        return {
            "path": str(rel_path),
            "exists": False,
            "start_line": 0,
            "end_line": 0,
            "code": "",
        }
    try:
        text = storage.read_text(file_path)
        lines = text.splitlines()
        idx = max(1, int(line))
        start = max(1, idx - context)
        end = min(len(lines), idx + context)
        snippet = "\n".join(lines[start - 1:end])
        return {
            "path": str(rel_path),
            "exists": True,
            "start_line": start,
            "end_line": end,
            "code": snippet,
        }
    except Exception:
        return {
            "path": str(rel_path),
            "exists": False,
            "start_line": 0,
            "end_line": 0,
            "code": "",
        }


__all__ = ["extract_snippet"]

