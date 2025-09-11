from __future__ import annotations

from pathlib import Path
from typing import TypedDict, Optional, Dict, Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


# -------- Settings types --------

class TemplateRoots(TypedDict, total=False):
    forge: str
    neoforge: str
    fabric: str  # future-proof; harmless if unused


class PathsSettings(TypedDict, total=False):
    runs_root: str
    downloads_root: str
    template_roots: TemplateRoots


# -------- Defaults (OK to keep for runs/downloads) --------

_DEFAULTS: PathsSettings = {
    "runs_root": "runs",
    "downloads_root": "runs/_downloads",
    "template_roots": {
        # Base root; templates_dir() will require <base>/<domain>/<framework> to exist
        "forge":    "backend/code_templates",
        "neoforge": "backend/code_templates",
        "fabric":   "backend/code_templates",
    },
}


# -------- Local helpers --------

def _project_root() -> Path:
    """Repo root (…/). This file lives at backend/agent/providers/paths.py."""
    return Path(__file__).resolve().parents[3]

def _backend_root() -> Path:
    """…/backend"""
    return Path(__file__).resolve().parents[2]

def _config_dir() -> Path:
    """Return the backend/config directory path."""
    return _backend_root() / "config"

def _config_file() -> Path:
    return _config_dir() / "paths.yaml"

def _resolve_from_project(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else _project_root() / p


# -------- Public API: settings & template roots --------

def build_paths_settings() -> PathsSettings:
    """Load path settings from backend/config/paths.yaml, with safe defaults."""
    cfg = _config_file()
    if not cfg.exists() or yaml is None:
        return _DEFAULTS.copy()
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        runs_root = str(data.get("runs_root") or _DEFAULTS["runs_root"]).strip()
        downloads_root = str(data.get("downloads_root") or _DEFAULTS["downloads_root"]).strip()

        # Merge template_roots with defaults
        template_roots = dict(_DEFAULTS["template_roots"])
        tr = data.get("template_roots")
        if isinstance(tr, dict):
            for k, v in tr.items():
                if isinstance(v, str) and v.strip():
                    template_roots[k] = v.strip()

        return {
            "runs_root": runs_root,
            "downloads_root": downloads_root,
            "template_roots": template_roots,
        }
    except Exception:
        return _DEFAULTS.copy()


def templates_dir(framework: str, domain: str = "item") -> Path:
    """
    STRICT: Resolve the code-templates directory for a given framework/domain.
    Requires configured base and an existing directory at <base>/<domain>/<framework>.
    """
    framework = (framework or "").strip().lower()
    s = build_paths_settings()
    roots = s.get("template_roots", {}) or {}

    base_str = roots.get(framework)
    if not base_str:
        raise ValueError(
            f"No template root configured for framework '{framework}'. "
            f"Add template_roots.{framework} in backend/config/paths.yaml."
        )
    base = _resolve_from_project(base_str)
    d = base / domain / framework
    if not d.exists():
        raise FileNotFoundError(
            f"Template directory not found: {d}. "
            f"Expected <base>/<domain>/<framework> with your templates."
        )
    return d


# -------- Public API: workspace tree helpers --------

def java_src_root(ws: Path) -> Path:
    return ws / "src" / "main" / "java"

def resources_root(ws: Path) -> Path:
    return ws / "src" / "main" / "resources"

def java_base_package_dir(ws: Path, base_package: str) -> Path:
    return java_src_root(ws) / Path(base_package.replace(".", "/"))

def main_class_file(ws: Path, base_package: str, main_class_name: str) -> Path:
    return java_base_package_dir(ws, base_package) / f"{main_class_name}.java"

def mod_items_file(ws: Path, base_package: str) -> Path:
    return java_base_package_dir(ws, base_package) / "item" / "ModItems.java"

def assets_dir(ws: Path, modid: str) -> Path:
    return resources_root(ws) / "assets" / modid

def lang_file(ws: Path, modid: str) -> Path:
    return assets_dir(ws, modid) / "lang" / "en_us.json"


# -------- Path template rendering (STRICT: templates must exist) --------

def _render_placeholders(text: str, ctx: Dict[str, Any]) -> str:
    """Ultra-simple {{key}} replacer; no logic/loops."""
    for k, v in ctx.items():
        text = text.replace(f"{{{{{k}}}}}", str(v))
    return text

def model_file(ws: Path, framework: str, ctx: Dict[str, Any]) -> Path:
    """
    Resolve the item model JSON path using a REQUIRED path template:
      backend/code_templates/item/<framework>/item_model_path.txt
    """
    td = templates_dir(framework, domain="item")
    tpl_path = td / "item_model_path.txt"
    if not tpl_path.exists():
        raise FileNotFoundError(f"Missing path template: {tpl_path}")
    rel = _render_placeholders(tpl_path.read_text(encoding="utf-8"), ctx).strip()
    return ws / Path(rel)

def texture_file(ws: Path, framework: str, ctx: Dict[str, Any]) -> Path:
    """
    Resolve the item texture PNG path using a REQUIRED path template:
      backend/code_templates/item/<framework>/texture_file_path.txt
    """
    td = templates_dir(framework, domain="item")
    tpl_path = td / "texture_file_path.txt"
    if not tpl_path.exists():
        raise FileNotFoundError(f"Missing path template: {tpl_path}")
    rel = _render_placeholders(tpl_path.read_text(encoding="utf-8"), ctx).strip()
    return ws / Path(rel)


__all__ = [
    "PathsSettings",
    "build_paths_settings",
    "templates_dir",
    "java_src_root",
    "resources_root",
    "java_base_package_dir",
    "main_class_file",
    "mod_items_file",
    "assets_dir",
    "lang_file",
    "model_file",
    "texture_file",
]