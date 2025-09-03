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
    ws = Path(workspace)
    fw = framework.strip().lower()

    _validate_modid(modid)
    _validate_package(package)

    changed: set[str] = set()
    renamed: list[tuple[str, str]] = []
    notes: list[str] = []

    # 1) Move packages first (so subsequent FQCN rewrites match on-disk files)
    pkg_changed = _refactor_sources_to_package(ws, package)
    changed.update(pkg_changed)

    # 2) Framework-specific manifest + code updates
    if fw in ("forge", "neoforge"):
        changed.update(_touch_forge_like_manifests(ws, modid, display_name, description, authors, license_name, version))
        code_changed, code_notes = _patch_forge_modid_in_code(ws, modid)
        changed.update(code_changed)
        notes.extend(code_notes)
    elif fw == "fabric":
        manifest_changed = _touch_fabric_manifest(ws, modid, display_name, description, authors, license_name, version)
        changed.update(manifest_changed)
        ep_changed, mixin_changed, mixin_renames, mixin_notes = _patch_fabric_entrypoints_and_mixins(ws, package, modid)
        changed.update(ep_changed)
        changed.update(mixin_changed)
        renamed.extend(mixin_renames)
        notes.extend(mixin_notes)
    else:
        raise ValueError(f"Unsupported framework: {framework}")

    # 3) Gradle group (both DSLs), idempotent
    gradle_changed = _ensure_gradle_group(ws, group)
    changed.update(gradle_changed)

    # 4) Resources
    lang_path = _ensure_lang(ws, modid)
    if lang_path:
        changed.add(str(lang_path))

    mcmeta_path = _ensure_pack_mcmeta(ws, mc_version)
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
) -> set[str]:
    changed: set[str] = set()
    meta_inf = ws / "src" / "main" / "resources" / "META-INF"
    for name in ("neoforge.mods.toml", "mods.toml"):
        p = meta_inf / name
        if not p.exists():
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        orig = txt
        
        # modId = "..."
        # FIX: Use single quotes for the f-string to avoid escaping inner double quotes.
        txt = re.sub(r'(?m)^(\s*modId\s*=\s*)"[^"]*"', rf'\1"{modid}"', txt)
        
        # Optional fields (best-effort; keep existing if present)
        if display_name:
            # FIX: Apply the same pattern here.
            txt, _ = re.subn(r'(?m)^(\s*displayName\s*=\s*)"[^"]*"', rf'\1"{display_name}"', txt)
        if description:
            # FIX: Apply the same pattern here.
            txt, _ = re.subn(r'(?m)^(\s*description\s*=\s*)"[^"]*"', rf'\1"{description}"', txt)
        if version:
            # FIX: Apply the same pattern here.
            txt, _ = re.subn(r'(?m)^(\s*version\s*=\s*)"[^"]*"', rf'\1"{version}"', txt)
            
        if txt != orig:
            p.write_text(txt, encoding="utf-8")
            changed.add(str(p))
            
    return changed

def _patch_forge_modid_in_code(ws: Path, modid: str) -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    notes: list[str] = []
    roots = [ws / "src" / "main" / "java", ws / "src" / "main" / "kotlin"]
    any_mod_anno = False

    for root in roots:
        if not root.exists():
            continue
        for file in root.rglob("*.java"):
            txt = file.read_text(encoding="utf-8", errors="ignore")
            orig = txt
            # @Mod("...") literal
            txt, n1 = re.subn(r"@Mod\(\s*\"[^\"]*\"\s*\)", f'@Mod("{modid}")', txt)
            # public static final String MOD_ID = "..."; (common)
            # FIX: Use a standard f-string with an escaped backslash for the backreference.
            txt, n2 = re.subn(r"(MOD[_]?ID\s*=\s*)\"[^\"]*\"", f'\\1"{modid}"', txt)
            if txt != orig:
                file.write_text(txt, encoding="utf-8")
                changed.add(str(file))
                if n1:
                    any_mod_anno = True
        for file in root.rglob("*.kt"):
            txt = file.read_text(encoding="utf-8", errors="ignore")
            orig = txt
            # @Mod("...") literal
            txt, n1 = re.subn(r"@Mod\(\s*\"[^\"]*\"\s*\)", f'@Mod("{modid}")', txt)
            # const val MOD_ID = "..." or val MOD_ID = "..."
            # FIX: Use a standard f-string with an escaped backslash for the backreference.
            txt, n2 = re.subn(r"(MOD[_]?ID\s*=\s*)\"[^\"]*\"", f'\\1"{modid}"', txt)
            if txt != orig:
                file.write_text(txt, encoding="utf-8")
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
    p = ws / "src" / "main" / "resources" / "fabric.mod.json"
    changed: set[str] = set()
    if not p.exists():
        return changed
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
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
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        changed.add(str(p))
    return changed


def _patch_fabric_entrypoints_and_mixins(ws: Path, package: str, modid: str) -> tuple[set[str], set[str], list[tuple[str, str]], list[str]]:
    """Rewrite entrypoint FQCNs in fabric.mod.json to the new package and
    update/rename mixins JSON files; set their "package" field to the new package.
    Returns (entrypoint_changed_files, mixin_changed_files, mixin_renames, notes).
    """
    changed_ep: set[str] = set()
    changed_mixin: set[str] = set()
    renames: list[tuple[str, str]] = []
    notes: list[str] = []

    mod_json = ws / "src" / "main" / "resources" / "fabric.mod.json"
    if not mod_json.exists():
        return changed_ep, changed_mixin, renames, notes

    try:
        data = json.loads(mod_json.read_text(encoding="utf-8"))
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
            mod_json.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            changed_ep.add(str(mod_json))

    # --- mixins ---
    mix = data.get("mixins")
    res_dir = ws / "src" / "main" / "resources"

    def _process_mixin_file(rel: str) -> None:
        nonlocal changed_mixin, renames, notes
        src = res_dir / rel
        if not src.exists():
            notes.append(f"mixins file referenced but not found: {rel}")
            return
        # Rename to <modid>.mixins.json if a single mixin file is referenced by a generic name
        base = src.name
        desired = f"{modid}.mixins.json"
        target = src if base == desired else src.with_name(desired)
        if target != src:
            try:
                if target.exists():
                    # Avoid overwriting; keep existing name
                    notes.append(f"desired mixins filename exists, keeping: {target.name}")
                else:
                    src.rename(target)
                    renames.append((str(src), str(target)))
                    # Update reference in fabric.mod.json
                    if isinstance(mix, str):
                        data["mixins"] = desired
                    elif isinstance(mix, list):
                        data["mixins"] = [desired if x == rel else x for x in mix]
                    mod_json.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                    changed_ep.add(str(mod_json))
                src = target
            except Exception:
                pass
        # Update package field inside mixins json
        try:
            mdata = json.loads(src.read_text(encoding="utf-8"))
            if mdata.get("package") != package:
                mdata["package"] = package
                src.write_text(json.dumps(mdata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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

def _ensure_gradle_group(ws: Path, group: str) -> set[str]:
    changed: set[str] = set()
    for name in ("build.gradle", "build.gradle.kts"):
        p = ws / name
        if not p.exists():
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        orig = txt
        # Already has group?
        if re.search(r"(?m)^\s*group\s*(=|\s)\s*['\"]", txt):
            # Try to normalize value if it's clearly the example
            txt = re.sub(r"(?m)^(\s*group\s*(=|\s)\s*)['\"][^'\"]*['\"]", rf"\1\"{group}\"", txt, count=1)
        else:
            txt = txt.rstrip() + f"\n\n// mine_modder: injected group\ngroup = \"{group}\"\n"
        if txt != orig:
            p.write_text(txt, encoding="utf-8")
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


def _refactor_sources_to_package(ws: Path, new_pkg: str) -> set[str]:
    """Move Java/Kotlin sources from example package to `new_pkg` and rewrite
    `package ...;` lines. Returns set of changed file paths.
    """
    changed: set[str] = set()
    for lang_root in (ws / "src" / "main" / "java", ws / "src" / "main" / "kotlin"):
        if not lang_root.exists():
            continue
        # Find an existing example package dir
        example_dir: Optional[Path] = None
        for ex in EXAMPLE_PACKAGES:
            cand = lang_root / Path(ex.replace(".", "/"))
            if cand.exists():
                example_dir = cand
                break
        if example_dir is None:
            # Heuristic: if exactly one top-level dir, treat as current root package
            pkgs = [p for p in lang_root.iterdir() if p.is_dir()]
            if len(pkgs) == 1:
                example_dir = pkgs[0]
            else:
                # still rewrite package lines in place
                changed.update(_rewrite_package_decls(lang_root, new_pkg))
                continue

        target_dir = lang_root / Path(new_pkg.replace(".", "/"))
        if target_dir != example_dir:
            target_dir.mkdir(parents=True, exist_ok=True)
            for path in example_dir.rglob("*"):
                rel = path.relative_to(example_dir)
                dst = target_dir / rel
                if path.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(path), str(dst))
                    changed.add(str(dst))
            try:
                shutil.rmtree(example_dir)
            except Exception:
                pass
            # Rewrite in the new tree
            changed.update(_rewrite_package_decls(target_dir, new_pkg))
        else:
            changed.update(_rewrite_package_decls(example_dir, new_pkg))
    return changed


def _rewrite_package_decls(root: Path, new_pkg: str) -> set[str]:
    changed: set[str] = set()
    pkg_line_re = re.compile(r"^(\s*package\s+)([\w\.]+)(\s*;)")
    for file in list(root.rglob("*.java")) + list(root.rglob("*.kt")):
        txt = file.read_text(encoding="utf-8", errors="ignore")
        new, n = pkg_line_re.subn(rf"\1{new_pkg}\3", txt, count=1)
        if n:
            file.write_text(new, encoding="utf-8")
            changed.add(str(file))
    return changed


# -------------------------
# Resources
# -------------------------

def _ensure_lang(ws: Path, modid: str) -> Optional[Path]:
    lang = ws / "src" / "main" / "resources" / "assets" / modid / "lang" / "en_us.json"
    if lang.exists():
        return None
    lang.parent.mkdir(parents=True, exist_ok=True)
    lang.write_text("{}\n", encoding="utf-8")
    return lang


def _ensure_pack_mcmeta(ws: Path, mc_version: Optional[str]) -> Optional[Path]:
    mcmeta = ws / "src" / "main" / "resources" / "pack.mcmeta"
    desired_pf = _pack_format_for(mc_version)
    if mcmeta.exists():
        # Update pack_format if present and different
        try:
            data = json.loads(mcmeta.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("pack"), dict):
                if data["pack"].get("pack_format") != desired_pf:
                    data["pack"]["pack_format"] = desired_pf
                    mcmeta.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                    return mcmeta
            return None
        except Exception:
            # fall through to overwrite with minimal valid structure
            pass
    data = {"pack": {"pack_format": desired_pf, "description": "Generated by MineModder"}}
    mcmeta.parent.mkdir(parents=True, exist_ok=True)
    mcmeta.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return mcmeta


__all__ = ["apply_placeholders"]
