from __future__ import annotations

from pathlib import Path
from typing import Optional, TypedDict

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


class PathsSettings(TypedDict):
    runs_root: str
    downloads_root: str


_DEFAULTS: PathsSettings = {
    "runs_root": "runs",
    "downloads_root": "runs/_downloads",
}


def _config_dir() -> Path:
    """Return the backend/config directory path.

    This file lives at backend/agent/providers/paths.py, so backend is parents[2].
    """
    return Path(__file__).resolve().parents[2] / "config"


def _config_file() -> Path:
    return _config_dir() / "paths.yaml"


def build_paths_settings() -> PathsSettings:
    """Load path settings from backend/config/paths.yaml.

    If the file is missing or unreadable (or pyyaml is unavailable), returns defaults.
    """
    cfg = _config_file()
    if not cfg.exists() or yaml is None:
        return _DEFAULTS.copy()
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        runs_root = str(data.get("runs_root") or _DEFAULTS["runs_root"]).strip()
        downloads_root = str(data.get("downloads_root") or _DEFAULTS["downloads_root"]).strip()
        return {"runs_root": runs_root, "downloads_root": downloads_root}
    except Exception:
        return _DEFAULTS.copy()


__all__ = [
    "PathsSettings",
    "build_paths_settings",
]

