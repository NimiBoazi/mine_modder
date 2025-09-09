# backend/agent/tools/init/archive.py
"""
Archive extraction utilities (delegates to storage layer).
"""
from __future__ import annotations
from pathlib import Path
from backend.agent.wrappers.storage import STORAGE as storage


def extract_archive(archive_path: Path, dest_dir: Path, *, strip_top_level: bool = True, overwrite: bool = True) -> Path:
    """Extract `archive_path` into `dest_dir` via storage backend.
    Returns dest_dir.
    """
    return storage.extract_archive(Path(archive_path), Path(dest_dir), strip_top_level=strip_top_level, overwrite=overwrite)
