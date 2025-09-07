"""
Storage abstraction for file operations used by the initialization pipeline.

Usage pattern in pipeline modules:
    from backend.agent.tools.storage_layer import STORAGE
    # then use STORAGE for all file/path operations

To switch backends later (e.g., to S3/DB), change STORAGE below to another
implementation; pipeline modules stay unchanged.
"""
from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager
from typing import Iterable
import shutil
import stat
import zipfile
import tarfile


class Storage:
    # Existence/metadata
    def exists(self, path: Path) -> bool: raise NotImplementedError
    def is_file(self, path: Path) -> bool: raise NotImplementedError
    def is_dir(self, path: Path) -> bool: raise NotImplementedError

    # Directory/listing
    def ensure_dir(self, path: Path) -> None: raise NotImplementedError
    def ensure_parent_dir(self, path: Path) -> None: raise NotImplementedError
    def iterdir(self, path: Path) -> Iterable[Path]: raise NotImplementedError
    def rglob(self, root: Path, pattern: str) -> Iterable[Path]: raise NotImplementedError

    # Read/write
    def read_text(self, path: Path, encoding: str = "utf-8", errors: str = "ignore") -> str: raise NotImplementedError
    def write_text(self, path: Path, text: str, encoding: str = "utf-8") -> None: raise NotImplementedError
    def read_bytes(self, path: Path) -> bytes: raise NotImplementedError
    def write_bytes(self, path: Path, data: bytes) -> None: raise NotImplementedError

    @contextmanager
    def open_for_read_bytes(self, path: Path): raise NotImplementedError

    @contextmanager
    def open_for_write_bytes(self, path: Path): raise NotImplementedError

    # Copy/move/delete
    def copy_file(self, src: Path, dst: Path) -> None: raise NotImplementedError
    def copy_tree(self, src: Path, dst: Path) -> None: raise NotImplementedError
    def merge_tree(self, src: Path, dst: Path) -> None: raise NotImplementedError
    def move(self, src: Path, dst: Path) -> None: raise NotImplementedError
    def remove_tree(self, path: Path) -> None: raise NotImplementedError

    # Perms
    def set_executable(self, path: Path) -> None: raise NotImplementedError

    # Archives
    def extract_archive(self, archive_path: Path, dest_dir: Path, *, strip_top_level: bool = True, overwrite: bool = True) -> Path:
        raise NotImplementedError


class LocalStorage(Storage):
    """Filesystem-backed implementation."""

    # Existence/metadata
    def exists(self, path: Path) -> bool: return Path(path).exists()
    def is_file(self, path: Path) -> bool: return Path(path).is_file()
    def is_dir(self, path: Path) -> bool: return Path(path).is_dir()

    # Directory/listing
    def ensure_dir(self, path: Path) -> None:
        Path(path).mkdir(parents=True, exist_ok=True)
    def ensure_parent_dir(self, path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    def iterdir(self, path: Path) -> Iterable[Path]:
        return list(Path(path).iterdir())
    def rglob(self, root: Path, pattern: str) -> Iterable[Path]:
        return list(Path(root).rglob(pattern))

    # Read/write
    def read_text(self, path: Path, encoding: str = "utf-8", errors: str = "ignore") -> str:
        return Path(path).read_text(encoding=encoding, errors=errors)
    def write_text(self, path: Path, text: str, encoding: str = "utf-8") -> None:
        self.ensure_parent_dir(Path(path))
        Path(path).write_text(text, encoding=encoding)
    def read_bytes(self, path: Path) -> bytes:
        return Path(path).read_bytes()
    def write_bytes(self, path: Path, data: bytes) -> None:
        self.ensure_parent_dir(Path(path))
        Path(path).write_bytes(data)
    @contextmanager
    def open_for_read_bytes(self, path: Path):
        with open(Path(path), "rb") as f:
            yield f
    @contextmanager
    def open_for_write_bytes(self, path: Path):
        p = Path(path)
        self.ensure_parent_dir(p)
        with open(p, "wb") as f:
            yield f

    # Copy/move/delete
    def copy_file(self, src: Path, dst: Path) -> None:
        dstp = Path(dst); dstp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(src), dstp)
    def copy_tree(self, src: Path, dst: Path) -> None:
        srcp, dstp = Path(src), Path(dst)
        if dstp.exists():
            self.merge_tree(srcp, dstp)
        else:
            shutil.copytree(srcp, dstp)
    def merge_tree(self, src: Path, dst: Path) -> None:
        srcp, dstp = Path(src), Path(dst)
        dstp.mkdir(parents=True, exist_ok=True)
        for child in srcp.rglob("*"):
            rel = child.relative_to(srcp)
            t = dstp / rel
            if child.is_dir():
                t.mkdir(parents=True, exist_ok=True)
            else:
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(child, t)
    def move(self, src: Path, dst: Path) -> None:
        dstp = Path(dst); dstp.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(Path(src)), str(dstp))
    def remove_tree(self, path: Path) -> None:
        p = Path(path)
        if p.exists():
            shutil.rmtree(p)

    # Perms
    def set_executable(self, path: Path) -> None:
        try:
            p = Path(path)
            mode = p.stat().st_mode
            p.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception:
            pass

    # Archives
    def extract_archive(self, archive_path: Path, dest_dir: Path, *, strip_top_level: bool = True, overwrite: bool = True) -> Path:
        archive_path = Path(archive_path)
        dest_dir = Path(dest_dir)
        if overwrite and dest_dir.exists():
            shutil.rmtree(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        suffixes = "".join(archive_path.suffixes).lower()
        # Prefer using file object so other backends can override
        if suffixes.endswith(".zip"):
            with self.open_for_read_bytes(archive_path) as f:
                with zipfile.ZipFile(f) as zf:
                    members = zf.infolist()
                    # path traversal guard
                    for m in members:
                        _guard_no_traversal(dest_dir, dest_dir / m.filename)
                    for m in members:
                        if m.filename.endswith("/"):
                            continue
                        data = zf.read(m)
                        out = dest_dir / m.filename
                        self.ensure_parent_dir(out)
                        self.write_bytes(out, data)
        elif suffixes.endswith((".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tar")):
            mode = "r:*"
            with self.open_for_read_bytes(archive_path) as f:
                with tarfile.open(fileobj=f, mode=mode) as tf:
                    members = tf.getmembers()
                    for m in members:
                        target = dest_dir / m.name
                        _guard_no_traversal(dest_dir, target)
                    for m in members:
                        if m.isdir():
                            continue
                        extracted = tf.extractfile(m)
                        if extracted is None:
                            continue
                        data = extracted.read()
                        out = dest_dir / m.name
                        self.ensure_parent_dir(out)
                        self.write_bytes(out, data)
        else:
            raise RuntimeError(f"Unsupported archive format: {archive_path.name}")

        if strip_top_level:
            _maybe_flatten_single_top_level(self, dest_dir)

        return dest_dir


def _guard_no_traversal(root: Path, target: Path) -> None:
    root_resolved = Path(root).resolve()
    target_parent = (target if Path(target).suffix else Path(target).parent).resolve()
    if not str(target_parent).startswith(str(root_resolved)):
        raise RuntimeError(f"Blocked archive path traversal: {target}")


def _maybe_flatten_single_top_level(storage: Storage, dest_dir: Path) -> None:
    entries = [e for e in storage.iterdir(dest_dir) if Path(e).name != "__MACOSX"]
    if len(entries) != 1 or not storage.is_dir(entries[0]):
        return
    wrapper = entries[0]
    for child in storage.iterdir(wrapper):
        storage.move(child, Path(dest_dir) / Path(child).name)
    storage.remove_tree(wrapper)
    macosx = Path(dest_dir) / "__MACOSX"
    if storage.exists(macosx):
        storage.remove_tree(macosx)


# Default backend instance used by pipeline modules. Swap this to change storage backend.
STORAGE: Storage = LocalStorage()

__all__ = [
    "Storage",
    "LocalStorage",
    "STORAGE",
]

