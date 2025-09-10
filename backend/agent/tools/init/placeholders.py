# backend/agent/tools/placeholders.py
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
from typing import Iterable, Optional, Tuple

# Optional structured parsers (best-effort fallbacks below)
try:  # Python 3.11+
    import tomllib  # type: ignore
except Exception:  # pragma: no cover
    tomllib = None  # we'll use targeted, block-scoped regex edits for TOML

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
    from backend.agent.wrappers.storage import STORAGE as storage
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
        # Manifests first (we also capture old mod id to retarget dependency headers)
        m_changed, old_modid = _touch_forge_like_manifests(ws, modid, display_name, description,
                                                           authors, license_name, version, storage)
        changed.update(m_changed)

        # --- START: NEW CODE TO ADD ---
        # Handle mixins for Forge/NeoForge projects, which may be declared in their TOML manifest
        for manifest_name in ("neoforge.mods.toml", "mods.toml"):
            manifest_path = ws / "src" / "main" / "resources" / "META-INF" / manifest_name
            if storage.exists(manifest_path):
                mix_changed, mix_renames, mix_notes = _patch_forge_like_mixins(ws, package, modid, manifest_path, storage)
                changed.update(mix_changed)
                renamed.extend(mix_renames)
                notes.extend(mix_notes)
        # --- END: NEW CODE TO ADD ---

        # Rename the main mod class (ExampleMod.java) to CamelCase(modid) and update class name
        # Note: I've included your previous fix here by using the simplified version of this function.
        r_changed, r_notes, r_renames, desired_class, old_class = _rename_forge_main_class(ws, modid, storage)
        changed.update(r_changed)
        notes.extend(r_notes)
        renamed.extend(r_renames)

        # Normalize Forge idioms in code:
        # - Ensure constant is MOD_ID (not MODID), with correct value
        # - @Mod(<MainClass>.MOD_ID)
        # - Replace stale references like ExampleMod.MODID -> <MainClass>.MOD_ID
        code_changed, code_notes = _patch_forge_modid_in_code(ws, modid, storage, desired_class=desired_class, old_class=old_class)
        changed.update(code_changed)
        notes.extend(code_notes)

        # Update gradle.properties placeholders (mod_id, mod_name, mod_group_id, mod_authors, mod_description)
        gp_changed = _patch_gradle_properties(ws, modid, display_name, group, authors, description, storage)
        changed.update(gp_changed)

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

    # Only update pack.mcmeta if an MDK-derived MC version is available
    if mc_version:
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

def _extract_first_mods_block_span(txt: str) -> Optional[Tuple[int, int]]:
    """
    Return span (start, end) for the first [[mods]] or [mods] block (brace-less TOML).
    We scan until the next top-level bracket '[' start or end-of-file.
    """
    m = re.search(r'(?m)^\s*\[\[\s*mods\s*\]\]|\s*^\s*\[\s*mods\s*\]\s*', txt)
    if not m:
        return None
    start = m.start()
    # find next top-level table header
    nxt = re.search(r'(?m)^\s*\[', txt[m.end():])
    end = m.end() + (nxt.start() if nxt else (len(txt) - m.end()))
    return (start, end)

def _read_modid_from_mods_block(block: str) -> Optional[str]:
    m = re.search(r'(?m)^\s*modId\s*=\s*["\']([^"\']+)["\']\s*$', block)
    return m.group(1) if m else None

def _replace_in_span(text: str, span: Tuple[int, int], repl_fn) -> str:
    s, e = span
    part = text[s:e]
    part2 = repl_fn(part)
    if part2 == part:
        return text
    return text[:s] + part2 + text[e:]

def _touch_forge_like_manifests(
    ws: Path,
    modid: str,
    display_name: Optional[str],
    description: Optional[str],
    authors: Optional[list[str]],
    license_name: Optional[str],
    version: Optional[str],
    storage,
) -> tuple[set[str], Optional[str]]:
    """
    Carefully update only the [[mods]] block (modId + optional fields).
    Also retarget [[dependencies.<old_modid>]] headers to [[dependencies.<modid>]].
    DO NOT touch dependency entries' modId (e.g., "minecraft"/"neoforge"/"forge").
    """
    changed: set[str] = set()
    old_modid_found: Optional[str] = None
    meta_inf = ws / "src" / "main" / "resources" / "META-INF"

    for name in ("neoforge.mods.toml", "mods.toml"):
        p = meta_inf / name
        if not storage.exists(p):
            continue
        txt = storage.read_text(p, encoding="utf-8", errors="ignore")
        orig = txt

        span = _extract_first_mods_block_span(txt)
        if span:
            # read old modid then update only inside this block
            block = txt[span[0]:span[1]]
            old = _read_modid_from_mods_block(block)
            if old:
                old_modid_found = old

            def _mutate(block_text: str) -> str:
                bt = block_text
                # modId = "<modid>"
                bt = re.sub(r'(?m)^(\s*modId\s*=\s*)["\'][^"\']*["\']\s*$', rf'\1"{modid}"', bt)
                # displayName, description, version
                if display_name:
                    bt, _ = re.subn(r'(?m)^(\s*displayName\s*=\s*)["\'][^"\']*["\']\s*$', rf'\1"{display_name}"', bt)
                if description:
                    bt, _ = re.subn(r'(?m)^(\s*description\s*=\s*)["\'][^"\']*["\']\s*$', rf'\1"{description}"', bt)
                if version:
                    bt, _ = re.subn(r'(?m)^(\s*version\s*=\s*)["\'][^"\']*["\']\s*$', rf'\1"{version}"', bt)
                if license_name:
                    bt, _ = re.subn(r'(?m)^(\s*license\s*=\s*)["\'][^"\']*["\']\s*$', rf'\1"{license_name}"', bt)
                if authors:
                    authors_str = ", ".join(str(a) for a in authors if a).strip()
                    if authors_str:
                        bt, _ = re.subn(r'(?m)^(\s*authors\s*=\s*)["\'][^"\']*["\']\s*$', rf'\1"{authors_str}"', bt)
                return bt

            txt = _replace_in_span(txt, span, _mutate)

        # Retarget dependency headers: [[dependencies.<old>]] -> [[dependencies.<modid>]]
        if old_modid_found and old_modid_found != modid:
            txt, _ = re.subn(
                rf'(?m)^\s*\[\[\s*dependencies\.{re.escape(old_modid_found)}\s*\]\]\s*$',
                f'[[dependencies.{modid}]]',
                txt
            )

        if txt != orig:
            storage.write_text(p, txt, encoding="utf-8")
            changed.add(str(p))

    return changed, old_modid_found


def _patch_forge_modid_in_code(
    ws: Path,
    modid: str,
    storage,
    *,
    desired_class: Optional[str],
    old_class: Optional[str],
) -> tuple[set[str], list[str]]:
    """
    Normalize Forge code to:
      - public static final String MOD_ID = "<modid>" (or Kotlin const val)
      - @Mod(<DesiredClass>.MOD_ID)
      - Replace <OldClass>.MODID and <DesiredClass>.MODID -> <DesiredClass>.MOD_ID
      - Normalize bare MODID -> MOD_ID when it's clearly the same constant
    """
    changed: set[str] = set()
    notes: list[str] = []
    roots = [ws / "src" / "main" / "java", ws / "src" / "main" / "kotlin"]

    cls = desired_class or "MODSENTRY"  # placeholder; should be set by rename
    oc  = old_class

    for root in roots:
        if not storage.exists(root):
            continue

        # --- Java files ---
        for file in storage.rglob(root, "*.java"):
            txt = storage.read_text(file, encoding="utf-8", errors="ignore")
            orig = txt

            # Ensure constant name & value (handles both MOD_ID and MODID declarations)
            # public static final String MODID = "...";
            txt, _ = re.subn(
                r'(?m)^\s*(public\s+static\s+final\s+String\s+)MODID(\s*=\s*)"[^\"]*"\s*;',
                rf'\1MOD_ID\2"{modid}";',
                txt
            )
            # public static final String MOD_ID = "...";
            txt, _ = re.subn(
                r'(?m)^\s*(public\s+static\s+final\s+String\s+)MOD_ID(\s*=\s*)"[^\"]*"\s*;',
                rf'\1MOD_ID\2"{modid}";',
                txt
            )

            # @Mod(...) -> @Mod(<DesiredClass>.MOD_ID)
            txt, _ = re.subn(
                r'@Mod\s*\(\s*[^)]*\s*\)',
                f'@Mod({cls}.MOD_ID)',
                txt
            )

            # Replace stale references: <OldClass>.MODID -> <DesiredClass>.MOD_ID
            if oc:
                txt, _ = re.subn(rf'\b{re.escape(oc)}\.MODID\b', f'{cls}.MOD_ID', txt)
                txt, _ = re.subn(rf'\b{re.escape(oc)}\.MOD_ID\b', f'{cls}.MOD_ID', txt)  # if old used MOD_ID already

                # general static & ctor references:
                txt, _ = re.subn(rf'\b{re.escape(oc)}\s*::', f'{cls}::', txt)   # method refs
                txt, _ = re.subn(rf'\b{re.escape(oc)}\s*\.', f'{cls}.', txt)    # static field/method refs
                txt, _ = re.subn(rf'\bnew\s+{re.escape(oc)}\s*\(', f'new {cls}(', txt)  # constructors

            # Also normalize <DesiredClass>.MODID -> <DesiredClass>.MOD_ID
            txt, _ = re.subn(rf'\b{re.escape(cls)}\.MODID\b', f'{cls}.MOD_ID', txt)

            # Bare MODID -> MOD_ID (heuristic; safe in typical MDKs)
            txt = re.sub(r'\bMODID\b', 'MOD_ID', txt)

            if txt != orig:
                storage.write_text(file, txt, encoding="utf-8")
                changed.add(str(file))

        # --- Kotlin files ---
        for file in storage.rglob(root, "*.kt"):
            txt = storage.read_text(file, encoding="utf-8", errors="ignore")
            orig = txt

            # const val MODID = "..."  -> const val MOD_ID = "<modid>"
            txt, _ = re.subn(
                r'(?m)^\s*(const\s+val\s+)MODID(\s*=\s*)"[^\"]*"\s*$',
                rf'\1MOD_ID\2"{modid}"',
                txt
            )
            # const val MOD_ID = "..." -> value update
            txt, _ = re.subn(
                r'(?m)^\s*(const\s+val\s+)MOD_ID(\s*=\s*)"[^\"]*"\s*$',
                rf'\1MOD_ID\2"{modid}"',
                txt
            )

            # @Mod(...) -> @Mod(<DesiredClass>.MOD_ID)
            txt, _ = re.subn(
                r'@Mod\s*\(\s*[^)]*\s*\)',
                f'@Mod({cls}.MOD_ID)',
                txt
            )

            if oc:
                txt, _ = re.subn(rf'\b{re.escape(oc)}\.MODID\b', f'{cls}.MOD_ID', txt)
                txt, _ = re.subn(rf'\b{re.escape(oc)}\.MOD_ID\b', f'{cls}.MOD_ID', txt)

                # NEW: general static refs & method refs
                txt, _ = re.subn(rf'\b{re.escape(oc)}\s*::', f'{cls}::', txt)   # method refs
                txt, _ = re.subn(rf'\b{re.escape(oc)}\s*\.', f'{cls}.', txt)    # static field/method refs

            txt, _ = re.subn(rf'\b{re.escape(cls)}\.MODID\b', f'{cls}.MOD_ID', txt)
            txt = re.sub(r'\bMODID\b', 'MOD_ID', txt)

            if txt != orig:
                storage.write_text(file, txt, encoding="utf-8")
                changed.add(str(file))

    if desired_class is None:
        notes.append("Could not determine main class name; used literal MOD_ID form.")
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
    from backend.agent.wrappers.storage import STORAGE as storage
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

def _patch_forge_like_mixins(
    ws: Path,
    package: str,
    modid: str,
    manifest_path: Path,
    storage,
) -> tuple[set[str], list[tuple[str, str]], list[str]]:
    """
    Finds mixin declarations in a TOML manifest, renames the mixin JSON file,
    updates the reference in the manifest, and patches the package path inside the JSON.
    """
    changed: set[str] = set()
    renames: list[tuple[str, str]] = []
    notes: list[str] = []

    if not storage.exists(manifest_path):
        return changed, renames, notes

    txt = storage.read_text(manifest_path, encoding="utf-8", errors="ignore")
    orig_txt = txt
    res_dir = ws / "src" / "main" / "resources"

    # Find all mixin file declarations, e.g., mixins = "examplemod.mixins.json"
    # and replace them in-place.
    def replace_mixin_ref(match):
        nonlocal changed, renames, notes
        prefix = match.group(1)
        old_mixin_name = match.group(2)
        
        old_mixin_path = res_dir / old_mixin_name
        if not storage.exists(old_mixin_path):
            notes.append(f"Mixin file referenced in {manifest_path.name} not found: {old_mixin_name}")
            return match.group(0) # Return original string if file not found

        # 1. Determine new name and rename the physical file
        desired_mixin_name = f"{modid}.mixins.json"
        new_mixin_path = old_mixin_path.with_name(desired_mixin_name)
        
        current_mixin_path = old_mixin_path
        if str(old_mixin_path) != str(new_mixin_path):
            if storage.exists(new_mixin_path):
                notes.append(f"Desired mixin filename exists, using original: {new_mixin_path.name}")
                # If the target file exists, we shouldn't rename, so we keep the old path.
                # However, we'll still patch its contents.
                current_mixin_path = new_mixin_path
            else:
                storage.move(old_mixin_path, new_mixin_path)
                renames.append((str(old_mixin_path), str(new_mixin_path)))
                changed.add(str(new_mixin_path))
                current_mixin_path = new_mixin_path

        # 2. Patch the "package" inside the mixin JSON file
        try:
            mixin_data = json.loads(storage.read_text(current_mixin_path, encoding="utf-8"))
            if "package" in mixin_data and isinstance(mixin_data["package"], str):
                old_mixin_pkg = mixin_data["package"]
                # Preserve the ".mixin" suffix from the original package
                suffix = ""
                if "." in old_mixin_pkg:
                    parts = old_mixin_pkg.split('.')
                    if parts[-1].lower() == 'mixin':
                         suffix = "." + parts[-1]
                
                desired_mixin_pkg = f"{package}{suffix}"
                
                if old_mixin_pkg != desired_mixin_pkg:
                    mixin_data["package"] = desired_mixin_pkg
                    storage.write_text(current_mixin_path, json.dumps(mixin_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                    changed.add(str(current_mixin_path))
        except Exception as e:
            notes.append(f"Could not parse or patch mixin file {current_mixin_path.name}: {e}")

        # 3. Return the updated line for the manifest file
        return f'{prefix}"{desired_mixin_name}"'

    # Use re.sub with our helper function to perform all operations
    txt = re.sub(r'(?m)^(\s*mixins\s*=\s*)"([^"]+)"', replace_mixin_ref, txt)

    # Write back the updated manifest if it changed
    if txt != orig_txt:
        storage.write_text(manifest_path, txt, encoding="utf-8")
        changed.add(str(manifest_path))

    return changed, renames, notes


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
# Forge main class rename + gradle.properties
# -------------------------

def _camel_case_modid(modid: str) -> str:
    parts = [p for p in modid.split("_") if p]
    return "".join(s[:1].upper() + s[1:] for s in parts)


def _rename_forge_main_class(ws: Path, modid: str, storage) -> tuple[set[str], list[str], list[tuple[str, str]], Optional[str], Optional[str]]:
    """Find the primary @Mod class and rename it to CamelCase(modid) including the class name.
    Also normalize constructor name to match the new class.
    Returns (changed_files, notes, renames, desired_class_name, old_class_name).
    """
    changed: set[str] = set()
    notes: list[str] = []
    renames: list[tuple[str, str]] = []
    desired = _camel_case_modid(modid)

    roots = [ws / "src" / "main" / "java", ws / "src" / "main" / "kotlin"]
    target_file = None
    for root in roots:
        if not storage.exists(root):
            continue
        for fpath in storage.rglob(root, "*.java") + storage.rglob(root, "*.kt"):
            try:
                txt = storage.read_text(fpath, encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "@Mod(" not in txt:
                continue
            target_file = fpath
            break
        if target_file:
            break

    if not target_file:
        notes.append("forge main class not found (@Mod annotation)")
        return changed, notes, renames, None, None

    # Determine current class name (Java/Kotlin)
    txt = storage.read_text(target_file, encoding="utf-8", errors="ignore")
    m = re.search(r"\b(class|object)\s+([A-Za-z_][A-Za-z0-9_]*)", txt)
    if not m:
        notes.append(f"could not parse class name in {target_file}")
        return changed, notes, renames, None, None
    kind = m.group(1)
    current = m.group(2)

    if current != desired:
        # Update class name in content
        new_txt = txt[:m.start(2)] + desired + txt[m.end(2):]
        # Fix constructor name for Java classes (skip Kotlin object)
        if kind == "class":
            new_txt = re.sub(rf'\b(public\s+)?{re.escape(current)}\s*\(', rf'\1{desired}(', new_txt)

        storage.write_text(target_file, new_txt, encoding="utf-8")
        changed.add(str(target_file))

        # Rename file to match class
        dest = target_file.with_name(f"{desired}{target_file.suffix}")
        if str(dest) != str(target_file):
            if storage.exists(dest):
                # Avoid overwrite; keep content change but not file rename
                notes.append(f"desired filename exists, kept original: {dest.name}")
            else:
                storage.move(target_file, dest)
                renames.append((str(target_file), str(dest)))
                changed.add(str(dest))
                target_file = dest  # update pointer
    else:
        # Still normalize constructor name if mismatch (Java)
        if kind == "class":
            new_txt = re.sub(rf'\b(public\s+)?{re.escape(current)}\s*\(', rf'\1{desired}(', txt)
            if new_txt != txt:
                storage.write_text(target_file, new_txt, encoding="utf-8")
                changed.add(str(target_file))

    return changed, notes, renames, desired, current


def _patch_gradle_properties(
    ws: Path,
    modid: str,
    display_name: Optional[str],
    group: str,
    authors: Optional[list[str]],
    description: Optional[str],
    storage,
) -> set[str]:
    """Ensure common Forge properties are set in gradle.properties.
    Keys: mod_id, mod_name, mod_group_id, mod_authors, mod_description.
    """
    gp = ws / "gradle.properties"
    updated: set[str] = set()

    # If file missing, create minimal with our values
    if not storage.exists(gp):
        lines: list[str] = []
    else:
        try:
            lines = storage.read_text(gp, encoding="utf-8").splitlines()
        except Exception:
            lines = []

    kv = {
        "mod_id": modid,
        "mod_group_id": group,
    }
    if display_name:
        kv["mod_name"] = display_name
    if authors and isinstance(authors, list):
        kv["mod_authors"] = ", ".join(str(a) for a in authors if a)
    if description:
        # Escape newlines for .properties value
        kv["mod_description"] = str(description).replace("\r\n", "\n").replace("\n", r"\n")

    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        m = re.match(r"\s*([A-Za-z0-9_.-]+)\s*=\s*(.*)$", line)
        if not m:
            out.append(line)
            continue
        key = m.group(1)
        if key in kv:
            out.append(f"{key}={kv[key]}")
            seen.add(key)
            updated.add(str(gp))
        else:
            out.append(line)
    # Append missing keys
    for k, v in kv.items():
        if k not in seen:
            out.append(f"{k}={v}")
            updated.add(str(gp))

    # Write back if content changed
    new_text = "\n".join(out) + "\n"
    orig_text = "\n".join(lines) + ("\n" if lines else "")
    if new_text != orig_text:
        storage.ensure_parent_dir(gp)
        storage.write_text(gp, new_text, encoding="utf-8")
        updated.add(str(gp))

    return updated



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
