# backend/agent/tools/archive.py
"""
Archive extraction utilities for project initialization (no caching here).

Responsibilities:
- unzip/untar a downloaded MDK/template into `dest_dir`
- guard against path traversal
- optionally flatten a single top-level folder (common in MDKs/templates)
- return the path to the extracted root

Usage:
    from pathlib import Path
    from backend.agent.tools.archive import extract_archive

    root = extract_archive(Path("runs/_downloads/forge/1.21/forge-1.21.8-58.1.0-mdk.zip"),
                           Path("runs/_downloads/forge/1.21/extracted"))

Design notes:
- We ignore "__MACOSX" when deciding whether to flatten.
- We support .zip and common tar variants: .tar.gz/.tgz, .tar.xz, .tar.bz2.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import zipfile
import tarfile
from typing import Iterable


def extract_archive(archive_path: Path, dest_dir: Path, *, strip_top_level: bool = True, overwrite: bool = True) -> Path:
    """
    Extract `archive_path` into `dest_dir`.
    If `strip_top_level` and the archive contains exactly one top-level directory (ignoring __MACOSX),
    flatten it so the contents land directly in `dest_dir`.

    Returns: Path to the extracted root (i.e., `dest_dir`).

    Raises: RuntimeError on unsupported format or traversal attempt.
    """
    archive_path = Path(archive_path)
    dest_dir = Path(dest_dir)

    if overwrite and dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    suffixes = "".join(archive_path.suffixes).lower()
    if suffixes.endswith(".zip"):
        _extract_zip_safe(archive_path, dest_dir)
    elif suffixes.endswith((".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tar")):
        _extract_tar_safe(archive_path, dest_dir)
    else:
        raise RuntimeError(f"Unsupported archive format: {archive_path.name}")

    if strip_top_level:
        _maybe_flatten_single_top_level(dest_dir)

    return dest_dir


# --------------------------
# internal helpers
# --------------------------

def _extract_zip_safe(zip_path: Path, dest_dir: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.infolist()
        for m in members:
            _guard_no_traversal(dest_dir, dest_dir / m.filename)
        zf.extractall(dest_dir)


def _extract_tar_safe(tar_path: Path, dest_dir: Path) -> None:
    mode = "r:*"  # auto-detect compression
    with tarfile.open(tar_path, mode) as tf:
        members = tf.getmembers()
        for m in members:
            # tarfile members can have names like "../x"; build the final path and check
            target = dest_dir / m.name
            _guard_no_traversal(dest_dir, target)
        tf.extractall(dest_dir)


def _guard_no_traversal(root: Path, target: Path) -> None:
    root_resolved = root.resolve()
    target_parent = (target if target.suffix else target.parent).resolve()
    if not str(target_parent).startswith(str(root_resolved)):
        raise RuntimeError(f"Blocked archive path traversal: {target}")


def _maybe_flatten_single_top_level(dest_dir: Path) -> None:
    """
    If dest_dir contains exactly one directory (ignoring __MACOSX) and no files,
    move its contents up into dest_dir and remove the wrapper directory.
    """
    entries = [e for e in dest_dir.iterdir() if e.name != "__MACOSX"]
    if len(entries) != 1 or not entries[0].is_dir():
        return

    wrapper = entries[0]
    # move children up
    for child in wrapper.iterdir():
        shutil.move(str(child), str(dest_dir / child.name))
    # remove wrapper
    shutil.rmtree(wrapper, ignore_errors=True)
    # clean stray __MACOSX if present
    macosx = dest_dir / "__MACOSX"
    if macosx.exists():
        shutil.rmtree(macosx, ignore_errors=True)
