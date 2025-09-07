"""
Placeholders & scaffolding utilities (version-aware, detector-driven)

Purpose
-------
Turn a freshly-copied starter (MDK/template) into *your* mod project by applying
identifiers consistently across manifests, code, Gradle config, and resources.

Key guarantees
--------------
- Works for Forge, NeoForge, and Fabric starters (1.16+ typical layouts).
- **Edits file contents and paths** where needed (not just filenames).
- Idempotent: safe to run multiple times.
- Version-aware `pack.mcmeta` via config (see Dev vs Prod note below).

Dev vs Prod storage/config
--------------------------
- Reads `backend/config/project_matrix.yaml` in dev for `pack_format` rules.
  In prod, swap to your config service/DB but keep this module's API unchanged.

Public API
----------
apply_placeholders(
    workspace: Path | str,
    framework: str,
    *,
    modid: str,
    group: str,
    package: str,
    mc_version: str | None = None,
    display_name: str | None = None,
    description: str | None = None,
    authors: list[str] | None = None,
    license_name: str | None = None,
    version: str | None = None,
) -> dict
    Applies substitutions and creates missing files; returns a summary dict with
    `changed_files`, `renamed_files`, and `notes`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import re
import shutil
from typing import Iterable, Optional

# Optional structured parsers (best-effort fallbacks below)
try:  # Python 3.11+
    import tomllib  # type: ignore
except Exception:  # pragma: no cover
    tomllib = None  # we'll fallback to regex edits for TOML

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


# -------------------------
# Public entrypoint
# -------------------------

def apply_placeholders(
    workspace: Path | str,
    framework: str,
    *,
    modid: str,
    group: str,
    package: str,
    mc_version: str | None = None,
    display_name: str | None = None,
    description: str | None = None,
    authors: list[str] | None = None,
    license_name: str | None = None,
    version: str | None = None,
) -> dict:
    from backend.agent.tools.storage_layer import STORAGE as storage
    ws = Path(workspace)
    fw = framework.strip().lower()

    _validate_modid(modid)
    _validate_package(package)

    changed: set[str] = set()
    renamed: list[tuple[str, str]] = []
    notes: list[str] = []

    # 1) Move packages first (so subsequent FQCN rewrites match on-disk files)
    pkg_changed = _refactor_sources_to_package(ws, package, storage)
    changed.update(pkg_changed)

    # 2) Framework-specific manifest + code updates
    if fw in ("forge", "neoforge"):
        changed.update(_touch_forge_like_manifests(ws, modid, display_name, description, authors, license_name, version, storage))
        code_changed, code_notes = _patch_forge_modid_in_code(ws, modid, storage)
        changed.update(code_changed)
        notes.extend(code_notes)
    elif fw == "fabric":
        manifest_changed = _touch_fabric_manifest(ws, modid, display_name, description, authors, license_name, version)
        changed.update(manifest_changed)
        ep_changed, mixin_changed, mixin_renames, mixin_notes = _patch_fabric_entrypoints_and_mixins(ws, package, modid, storage)
        changed.update(ep_changed)
        changed.update(mixin_changed)
        renamed.extend(mixin_renames)
        notes.extend(mixin_notes)
    else:
        raise ValueError(f"Unsupported framework: {framework}")

    # 3) Gradle group (both DSLs), idempotent
    gradle_changed = _ensure_gradle_group(ws, group, storage)
    changed.update(gradle_changed)

    # 4) Resources
    lang_path = _ensure_lang(ws, modid, storage)
    if lang_path:
        changed.add(str(lang_path))

    mcmeta_path = _ensure_pack_mcmeta(ws, mc_version, storage)
    if mcmeta_path:
        changed.add(str(mcmeta_path))

    return {
        "framework": fw,
        "modid": modid,
        "group": group,
        "package": package,
        "changed_files": sorted(changed),
        "renamed_files": renamed,
        "notes": notes,
    }


# -------------------------
# Validation helpers
# -------------------------

def _validate_modid(modid: str) -> None:
    if not re.fullmatch(r"[a-z0-9_]+", modid):
        raise ValueError(f"Invalid modid '{modid}'. Use lowercase letters, digits, and underscores only.")


def _validate_package(package: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][\w]*(\.[A-Za-z_][\w]*)*", package):
        raise ValueError(f"Invalid Java package '{package}'.")


# -------------------------
# Config: pack_format mapping
# -------------------------

def _config_dir() -> Path:
    env = os.environ.get("MINEMODDER_CONFIG_DIR")
    if env:
        return Path(env)
    # backend/agent/tools/placeholders.py → ../../../config
    return Path(__file__).resolve().parents[3] / "config"


def _load_pack_rules() -> list[tuple[str, int]]:
    cfg = _config_dir() / "project_matrix.yaml"
    if not cfg.exists() or yaml is None:
        # conservative default; callers should supply mc_version for accurate value
        return [("*", 48)]
    data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    rp = data.get("resource_pack", {})
    rules = rp.get("pack_format_by_mc", {})
    out: list[tuple[str, int]] = []
    for k, v in rules.items():
        try:
            out.append((str(k), int(v)))
        except Exception:
            continue
    return out or [("*", 48)]


def _parse_ver(v: str) -> tuple[int, int, int]:
    parts = [p for p in re.split(r"[^0-9]", v) if p != ""]
    nums = [int(p) for p in parts[:3]]
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2])


def _cmp(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return (a > b) - (a < b)


def _rule_matches(mc_version: str, expr: str) -> bool:
    s = expr.strip()
    if s in ("*", "default"):
        return True
    # range with hyphen or en-dash
    if "-" in s or "–" in s:
        sep = "–" if "–" in s else "-"
        lo, hi = [x.strip() for x in s.split(sep, 1)]
        va = _parse_ver(mc_version)
        vlo = _parse_ver(lo)
        vhi = _parse_ver(hi)
        return _cmp(vlo, va) <= 0 and _cmp(va, vhi) <= 0
    m = re.match(r"^(>=|<=|==|=|>|<)?\s*(.+)$", s)
    if not m:
        return False
    op = m.group(1) or "=="
    bound = m.group(2)
    va = _parse_ver(mc_version)
    vb = _parse_ver(bound)
    c = _cmp(va, vb)
    return {
        "==": c == 0,
        "=": c == 0,
        ">=": c >= 0,
        ">": c > 0,
        "<=": c <= 0,
        "<": c < 0,
    }[op]


def _pack_format_for(mc_version: Optional[str]) -> int:
    if not mc_version:
        return 48  # fallback; better to supply mc_version
    for expr, pf in _load_pack_rules():
        if _rule_matches(mc_version, expr):
            return pf
    return 48


# -------------------------
# Manifests & code patching
# -------------------------

def _touch_forge_like_manifests(
    ws: Path,
    modid: str,
    display_name: Optional[str],
    description: Optional[str],
    authors: Optional[list[str]],
    license_name: Optional[str],
    version: Optional[str],
    storage,
) -> set[str]:
    changed: set[str] = set()
    meta_inf = ws / "src" / "main" / "resources" / "META-INF"
    for name in ("neoforge.mods.toml", "mods.toml"):
        p = meta_inf / name
        if not storage.exists(p):
            continue
        txt = storage.read_text(p, encoding="utf-8", errors="ignore")
        orig = txt

        # modId = "..."
        txt = re.sub(r'(?m)^(\s*modId\s*=\s*)"[^"]*"', rf'\1"{modid}"', txt)

        # Optional fields (best-effort; keep existing if present)
        if display_name:
            txt, _ = re.subn(r'(?m)^(\s*displayName\s*=\s*)"[^"]*"', rf'\1"{display_name}"', txt)
        if description:
            txt, _ = re.subn(r'(?m)^(\s*description\s*=\s*)"[^"]*"', rf'\1"{description}"', txt)
        if version:
            txt, _ = re.subn(r'(?m)^(\s*version\s*=\s*)"[^"]*"', rf'\1"{version}"', txt)

        if txt != orig:
            storage.write_text(p, txt, encoding="utf-8")
            changed.add(str(p))

    return changed

def _patch_forge_modid_in_code(ws: Path, modid: str, storage) -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    notes: list[str] = []
    roots = [ws / "src" / "main" / "java", ws / "src" / "main" / "kotlin"]
    any_mod_anno = False

    for root in roots:
        if not storage.exists(root):
            continue
        for file in storage.rglob(root, "*.java"):
            txt = storage.read_text(file, encoding="utf-8", errors="ignore")
            orig = txt
            # @Mod("...") literal
            txt, n1 = re.subn(r"@Mod\(\s*\"[^\"]*\"\s*\)", f'@Mod("{modid}")', txt)
            # public static final String MOD_ID = "..."; (common)
            txt, n2 = re.subn(r"(MOD[_]?ID\s*=\s*)\"[^\"]*\"", f'\\1"{modid}"', txt)
            if txt != orig:
                storage.write_text(file, txt, encoding="utf-8")
                changed.add(str(file))
                if n1:
                    any_mod_anno = True
        for file in storage.rglob(root, "*.kt"):
            txt = storage.read_text(file, encoding="utf-8", errors="ignore")
            orig = txt
            # @Mod("...") literal
            txt, n1 = re.subn(r"@Mod\(\s*\"[^\"]*\"\s*\)", f'@Mod("{modid}")', txt)
            # const val MOD_ID = "..." or val MOD_ID = "..."
            txt, n2 = re.subn(r"(MOD[_]?ID\s*=\s*)\"[^\"]*\"", f'\\1"{modid}"', txt)
            if txt != orig:
                storage.write_text(file, txt, encoding="utf-8")
                changed.add(str(file))
                if n1:
                    any_mod_anno = True

    if not any_mod_anno:
        notes.append("No @Mod(\"...\") literal found; relied on MOD_ID constant if present.")
    return changed, notes


def _touch_fabric_manifest(
    ws: Path,
    modid: str,
    display_name: Optional[str],
    description: Optional[str],
    authors: Optional[list[str]],
    license_name: Optional[str],
    version: Optional[str],
) -> set[str]:
    from backend.agent.tools.storage_layer import STORAGE as storage
    p = ws / "src" / "main" / "resources" / "fabric.mod.json"
    changed: set[str] = set()
    if not storage.exists(p):
        return changed
    try:
        data = json.loads(storage.read_text(p, encoding="utf-8"))
    except Exception:
        return changed
    orig = json.dumps(data, sort_keys=True)

    data["id"] = modid
    if display_name:
        data.setdefault("name", display_name)
    if description:
        data.setdefault("description", description)
    if version:
        data.setdefault("version", version)
    if authors:
        arr = data.setdefault("authors", [])
        if isinstance(arr, list) and arr == []:
            data["authors"] = authors
    if license_name:
        data.setdefault("license", license_name)

    new = json.dumps(data, sort_keys=True)
    if new != orig:
        storage.write_text(p, json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        changed.add(str(p))
    return changed


def _patch_fabric_entrypoints_and_mixins(ws: Path, package: str, modid: str, storage) -> tuple[set[str], set[str], list[tuple[str, str]], list[str]]:
    """Rewrite entrypoint FQCNs in fabric.mod.json to the new package and
    update/rename mixins JSON files; set their "package" field to the new package.
    Returns (entrypoint_changed_files, mixin_changed_files, mixin_renames, notes).
    """
    changed_ep: set[str] = set()
    changed_mixin: set[str] = set()
    renames: list[tuple[str, str]] = []
    notes: list[str] = []

    mod_json = ws / "src" / "main" / "resources" / "fabric.mod.json"
    if not storage.exists(mod_json):
        return changed_ep, changed_mixin, renames, notes

    try:
        data = json.loads(storage.read_text(mod_json, encoding="utf-8"))
    except Exception:
        return changed_ep, changed_mixin, renames, notes

    # --- entrypoints ---
    eps = data.get("entrypoints")
    if isinstance(eps, dict):
        mutated = False
        for key, arr in list(eps.items()):
            if isinstance(arr, list):
                new_arr = []
                for item in arr:
                    if isinstance(item, str):
                        cls = item.split(".")[-1]
                        new_arr.append(f"{package}.{cls}")
                    elif isinstance(item, dict) and "adapter" in item and "value" in item:
                        # Rare: {"adapter": "kotlin", "value": "pkg.Class"}
                        cls = str(item["value"]).split(".")[-1]
                        item["value"] = f"{package}.{cls}"
                        new_arr.append(item)
                    else:
                        new_arr.append(item)
                if new_arr != arr:
                    eps[key] = new_arr
                    mutated = True
        if mutated:
            storage.write_text(mod_json, json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            changed_ep.add(str(mod_json))

    # --- mixins ---
    mix = data.get("mixins")
    res_dir = ws / "src" / "main" / "resources"

    def _process_mixin_file(rel: str) -> None:
        nonlocal changed_mixin, renames, notes
        src = res_dir / rel
        if not storage.exists(src):
            notes.append(f"mixins file referenced but not found: {rel}")
            return
        # Rename to <modid>.mixins.json if a single mixin file is referenced by a generic name
        base = src.name
        desired = f"{modid}.mixins.json"
        target = src if base == desired else src.with_name(desired)
        if target != src:
            try:
                if storage.exists(target):
                    # Avoid overwriting; keep existing name
                    notes.append(f"desired mixins filename exists, keeping: {target.name}")
                else:
                    storage.move(src, target)
                    renames.append((str(src), str(target)))
                    # Update reference in fabric.mod.json
                    if isinstance(mix, str):
                        data["mixins"] = desired
                    elif isinstance(mix, list):
                        data["mixins"] = [desired if x == rel else x for x in mix]
                    storage.write_text(mod_json, json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                    changed_ep.add(str(mod_json))
                src = target
            except Exception:
                pass
        # Update package field inside mixins json
        try:
            mdata = json.loads(storage.read_text(src, encoding="utf-8"))
            if mdata.get("package") != package:
                mdata["package"] = package
                storage.write_text(src, json.dumps(mdata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                changed_mixin.add(str(src))
        except Exception:
            notes.append(f"could not parse mixins file: {src}")

    if isinstance(mix, str):
        _process_mixin_file(mix)
    elif isinstance(mix, list):
        for rel in mix:
            if isinstance(rel, str):
                _process_mixin_file(rel)

    return changed_ep, changed_mixin, renames, notes


# -------------------------
# Gradle group
# -------------------------

def _ensure_gradle_group(ws: Path, group: str, storage) -> set[str]:
    changed: set[str] = set()
    for name in ("build.gradle", "build.gradle.kts"):
        p = ws / name
        if not storage.exists(p):
            continue
        txt = storage.read_text(p, encoding="utf-8", errors="ignore")
        orig = txt
        # Already has group?
        if re.search(r"(?m)^\s*group\s*(=|\s)\s*['\"]", txt):
            # Try to normalize value if it's clearly the example
            txt = re.sub(r"(?m)^(\s*group\s*(=|\s)\s*)['\"][^'\"]*['\"]", rf"\1\"{group}\"", txt, count=1)
        else:
            txt = txt.rstrip() + f"\n\n// mine_modder: injected group\ngroup = \"{group}\"\n"
        if txt != orig:
            storage.write_text(p, txt, encoding="utf-8")
            changed.add(str(p))
    return changed


# -------------------------
# Source tree refactor (Java/Kotlin)
# -------------------------

EXAMPLE_PACKAGES = (
    "com.example.examplemod",       # Forge MDK classic
    "com.example.mod",              # common variant
    "net.fabricmc.example",         # Fabric example
)


def _refactor_sources_to_package(ws: Path, new_pkg: str, storage) -> set[str]:
    """Move Java/Kotlin sources from example package to `new_pkg` and rewrite
    `package ...;` lines. Returns set of changed file paths.
    """
    changed: set[str] = set()
    for lang_root in (ws / "src" / "main" / "java", ws / "src" / "main" / "kotlin"):
        if not storage.exists(lang_root):
            continue
        # Find an existing example package dir
        example_dir: Optional[Path] = None
        for ex in EXAMPLE_PACKAGES:
            cand = lang_root / Path(ex.replace(".", "/"))
            if storage.exists(cand):
                example_dir = cand
                break
        if example_dir is None:
            # Heuristic: if exactly one top-level dir, treat as current root package
            pkgs = [p for p in storage.iterdir(lang_root) if p.is_dir()]
            if len(pkgs) == 1:
                example_dir = pkgs[0]
            else:
                # still rewrite package lines in place
                changed.update(_rewrite_package_decls(lang_root, new_pkg, storage))
                continue

        target_dir = lang_root / Path(new_pkg.replace(".", "/"))
        if target_dir != example_dir:
            storage.ensure_dir(target_dir)
            for path in storage.rglob(example_dir, "*"):
                rel = Path(path).relative_to(example_dir)
                dst = target_dir / rel
                if Path(path).is_dir():
                    storage.ensure_dir(dst)
                else:
                    storage.ensure_parent_dir(dst)
                    storage.move(path, dst)
                    changed.add(str(dst))
            try:
                storage.remove_tree(example_dir)
            except Exception:
                pass
            # Rewrite in the new tree
            changed.update(_rewrite_package_decls(target_dir, new_pkg, storage))
        else:
            changed.update(_rewrite_package_decls(example_dir, new_pkg, storage))
    return changed


def _rewrite_package_decls(root: Path, new_pkg: str, storage) -> set[str]:
    changed: set[str] = set()
    pkg_line_re = re.compile(r"^(\s*package\s+)([\w\.]+)(\s*;)")
    files = (list(storage.rglob(root, "*.java")) + list(storage.rglob(root, "*.kt")))
    for file in files:
        txt = storage.read_text(file, encoding="utf-8", errors="ignore")
        new, n = pkg_line_re.subn(rf"\1{new_pkg}\3", txt, count=1)
        if n:
            storage.write_text(file, new, encoding="utf-8")
            changed.add(str(file))
    return changed


# -------------------------
# Resources
# -------------------------

def _ensure_lang(ws: Path, modid: str, STORAGE) -> Optional[Path]:
    lang = ws / "src" / "main" / "resources" / "assets" / modid / "lang" / "en_us.json"
    if STORAGE.exists(lang):
        return None
    STORAGE.ensure_parent_dir(lang)
    STORAGE.write_text(lang, "{}\n", encoding="utf-8")
    return lang


def _ensure_pack_mcmeta(ws: Path, mc_version: Optional[str], STORAGE) -> Optional[Path]:
    mcmeta = ws / "src" / "main" / "resources" / "pack.mcmeta"
    desired_pf = _pack_format_for(mc_version)
    if STORAGE.exists(mcmeta):
        # Update pack_format if present and different
        try:
            data = json.loads(STORAGE.read_text(mcmeta, encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("pack"), dict):
                if data["pack"].get("pack_format") != desired_pf:
                    data["pack"]["pack_format"] = desired_pf
                    STORAGE.write_text(mcmeta, json.dumps(data, indent=2) + "\n", encoding="utf-8")
                    return mcmeta
            return None
        except Exception:
            # fall through to overwrite with minimal valid structure
            pass
    data = {"pack": {"pack_format": desired_pf, "description": "Generated by MineModder"}}
    STORAGE.ensure_parent_dir(mcmeta)
    STORAGE.write_text(mcmeta, json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return mcmeta


__all__ = ["apply_placeholders"]
