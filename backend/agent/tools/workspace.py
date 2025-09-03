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
    """Create a new workspace directory under runs_root.

    The directory name is timestamped and embeds modid/framework/version to make
    it human-readable and unique:
        <runs_root>/<YYYYMMDD_HHMMSS>_<modid>_<framework>_<mc_version>/

    Returns the workspace Path. Raises FileExistsError only if an improbable
    name collision occurs.
    """
    runs_root = Path(runs_root)
    runs_root.mkdir(parents=True, exist_ok=True)

    name = f"{_timestamp()}_{_sanitize_token(modid)}_{_sanitize_token(framework)}_{_sanitize_token(mc_version)}"
    ws = runs_root / name
    ws.mkdir(parents=True, exist_ok=False)
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
    """Copy the extracted starter files into the workspace.

    - Skips VCS/system junk ('.git', '.github', '__MACOSX')
    - Preserves file metadata where possible
    - Ensures Gradle wrapper scripts are executable on POSIX
    - Does not delete anything already in workspace_dir
    """
    src = Path(extracted_dir)
    dst = Path(workspace_dir)

    if not src.exists() or not src.is_dir():
        raise FileNotFoundError(f"extracted_dir not found or not a directory: {src}")
    if not dst.exists() or not dst.is_dir():
        raise FileNotFoundError(f"workspace_dir not found or not a directory: {dst}")

    for item in _iter_top_level_entries(src):
        target = dst / item.name
        if item.is_dir():
            if target.exists():
                # Merge copy: copy contents into existing directory
                for child in item.rglob('*'):
                    rel = child.relative_to(item)
                    t = target / rel
                    if child.is_dir():
                        t.mkdir(parents=True, exist_ok=True)
                    else:
                        t.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(child, t)
            else:
                shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)

    # Ensure gradle wrapper is usable on POSIX
    gradlew = dst / "gradlew"
    if gradlew.exists():
        _ensure_executable(gradlew)
    # Windows batch is fine as-is; presence optional


__all__ = [
    "create",
    "copy_from_extracted",
]
