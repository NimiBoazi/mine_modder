"""
Workspace management utilities

⚠️ Storage note (dev vs prod)
--------------------------------
This module currently writes **only to the local filesystem** (e.g., `runs/…`).
In production you should swap these direct filesystem writes for a storage gateway
that writes large artifacts to **object storage** (S3/GCS/Azure Blob) and persists
metadata (paths, hashes, sizes) to a **database**. The public API of this module
(`create`, `copy_from_extracted`) can stay the same; only the implementation of
where files live needs to change.

Suggested later split:
- `storage_gateway.save_workspace(path) -> uri`
- `storage_gateway.save_artifact(path, kind) -> uri`
- `db.runs.update(run_id, {workspace_uri, status})`


This module creates the **editable project workspace** (your "desk copy") and
copies files from an extracted starter (MDK/template) into it.

Why separate workspace from downloads?
- downloads/extracted (library copy) stays pristine
- workspace is where your agent edits files and runs Gradle

Public API
----------
- create(runs_root, modid, framework, mc_version) -> Path
    Create a timestamped directory under runs_root, e.g.
    runs/20250902_193455_redsapphire_forge_1.21

- copy_from_extracted(extracted_dir, workspace_dir) -> None
    Copy all files from the extracted starter into the workspace.
    Skips VCS/system junk; ensures gradle wrapper is executable on POSIX.
"""
from __future__ import annotations

from pathlib import Path
import os
import shutil
import stat
import time
from typing import Iterable

IGNORED_TOP_LEVEL: set[str] = {".git", ".github", "__MACOSX"}


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _nonce(n:int=6) -> str:
    import uuid
    return uuid.uuid4().hex[:max(4, min(12, n))]


def _sanitize_token(token: str) -> str:
    """Make a token safe for filesystem names (conservative).
    Lowercase, keep alnum, dash, underscore, and dot; replace others with '-'.
    """
    safe = []
    for ch in token.strip():
        if ch.isalnum() or ch in {"-", "_", "."}:
            safe.append(ch)
        else:
            safe.append("-")
    return ("".join(safe)).lower().strip("-") or "project"


def create(runs_root: Path | str, modid: str, framework: str, mc_version: str) -> Path:
    """Create a new workspace directory under runs_root via storage."""
    from backend.agent.wrappers.storage import STORAGE as storage
    runs_root = Path(runs_root)
    storage.ensure_dir(runs_root)

    name = f"{_timestamp()}_{_sanitize_token(modid)}_{_sanitize_token(framework)}_{_sanitize_token(mc_version)}_{_nonce()}"
    ws = runs_root / name
    if storage.exists(ws):
        raise FileExistsError(str(ws))
    storage.ensure_dir(ws)
    return ws


def _iter_top_level_entries(src: Path) -> Iterable[Path]:
    for entry in src.iterdir():
        if entry.name in IGNORED_TOP_LEVEL:
            continue
        yield entry


def _ensure_executable(path: Path) -> None:
    """Best-effort: mark as executable on POSIX for wrapper scripts."""
    try:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        # On Windows or restricted FS, just ignore
        pass


def copy_from_extracted(extracted_dir: Path | str, workspace_dir: Path | str) -> None:
    """Copy the extracted starter files into the workspace using storage.

    - Skips VCS/system junk ('.git', '.github', '__MACOSX')
    - Preserves file metadata where possible
    - Ensures Gradle wrapper scripts are executable on POSIX
    - Does not delete anything already in workspace_dir
    """
    from backend.agent.wrappers.storage import STORAGE as storage
    src = Path(extracted_dir)
    dst = Path(workspace_dir)

    if not storage.exists(src) or not storage.is_dir(src):
        raise FileNotFoundError(f"extracted_dir not found or not a directory: {src}")
    if not storage.exists(dst) or not storage.is_dir(dst):
        raise FileNotFoundError(f"workspace_dir not found or not a directory: {dst}")

    for item in _iter_top_level_entries(src):
        target = dst / item.name
        if item.is_dir():
            if storage.exists(target):
                storage.merge_tree(item, target)
            else:
                storage.copy_tree(item, target)
        else:
            storage.copy_file(item, target)

    # Ensure gradle wrapper is usable on POSIX
    gradlew = dst / "gradlew"
    if storage.exists(gradlew):
        storage.set_executable(gradlew)
    # Windows batch is fine as-is; presence optional


__all__ = [
    "create",
    "copy_from_extracted",
]
