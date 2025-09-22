from __future__ import annotations

"""
Verify Task dedicated logger.

Writes to <workspace>/_mm_logs/verify_task.log
- Text events
- JSON payloads/responses (LLM)
- Full tracebacks on exceptions

Use this from verify_task node to keep node body clean and pure.
"""

import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.agent.wrappers.storage import STORAGE as storage


LOG_FILENAME = "verify_task.log"


def _log_path(workspace: str | Path) -> Path:
    ws = Path(workspace)
    d = ws / "_mm_logs"
    d.mkdir(parents=True, exist_ok=True)
    return d / LOG_FILENAME


def _ts() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def log_text(workspace: str | Path, message: str) -> None:
    try:
        p = _log_path(workspace)
        existing = storage.read_text(p) if storage.exists(p) else ""
        line = f"[{_ts()}] {message}\n"
        storage.write_text(p, existing + line)
        print(f"[VERIFY_LOG] {message}")
    except Exception as e:
        print(f"[VERIFY_LOG] failed to write text: {e}")


def log_json(workspace: str | Path, label: str, obj: Any) -> None:
    try:
        p = _log_path(workspace)
        existing = storage.read_text(p) if storage.exists(p) else ""
        payload = json.dumps(obj, ensure_ascii=False, indent=2)
        block = f"[{_ts()}] {label}: {payload}\n"
        storage.write_text(p, existing + block)
        print(f"[VERIFY_LOG] {label} written ({len(block)} bytes)")
    except Exception as e:
        print(f"[VERIFY_LOG] failed to write json: {e}")


def log_exception(workspace: str | Path, label: str, exc: BaseException | None = None) -> None:
    try:
        p = _log_path(workspace)
        existing = storage.read_text(p) if storage.exists(p) else ""
        tb = traceback.format_exc() if exc is not None else traceback.format_exc()
        block = f"[{_ts()}] {label} TRACEBACK:\n{tb}\n"
        storage.write_text(p, existing + block)
        print(f"[VERIFY_LOG] {label} traceback written")
    except Exception as e:
        print(f"[VERIFY_LOG] failed to write traceback: {e}")


__all__ = [
    "log_text",
    "log_json",
    "log_exception",
]

