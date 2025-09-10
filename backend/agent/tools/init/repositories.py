# backend/agent/tools/repositories.py
from __future__ import annotations

from pathlib import Path
import os
import re
import json
from typing import Optional, Tuple
from .version import detect_minecraft_version
from backend.agent.wrappers.storage import STORAGE as storage

# -----------------------------------------------------------------------------
# Shared config helpers
# -----------------------------------------------------------------------------

def _config_dir() -> Path:
    env = os.environ.get("MINEMODDER_CONFIG_DIR")
    if env:
        return Path(env)
    # backend/agent/tools/repositories.py → ../../../config
    return Path(__file__).resolve().parents[3] / "config"

def _parchment_map_path() -> Path:
    return _config_dir() / "parchment_versions.json"

def _parse_semver(s: str) -> tuple[int, int, int]:
    parts = [int(p) for p in re.split(r"\D+", s) if p]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])

def _nearest_parchment_date_for(mc_req: str, table: dict[str, str]) -> tuple[Optional[str], str]:
    # exact
    if mc_req in table:
        return table[mc_req], mc_req
    rM, rm, rp = _parse_semver(mc_req)
    same_minor, lower_all = [], []
    for k in table.keys():
        kM, km, kp = _parse_semver(k)
        if (kM, km) == (rM, rm) and kp <= rp:
            same_minor.append((kM, km, kp, k))
        if (kM, km, kp) <= (rM, rm, rp):
            lower_all.append((kM, km, kp, k))
    if same_minor:
        _, _, _, chosen = max(same_minor)
        return table[chosen], chosen
    if lower_all:
        _, _, _, chosen = max(lower_all)
        return table[chosen], chosen
    return None, mc_req

def _detect_mc_version_from_build(ws: Path, storage) -> Optional[str]:
    g = ws / "build.gradle"
    k = ws / "build.gradle.kts"
    target = g if storage.exists(g) else (k if storage.exists(k) else None)
    if target:
        txt = storage.read_text(target)
        # Forge coordinate often: net.minecraftforge:forge:<mc>-<forge>
        m = re.search(r"net\.minecraftforge:forge:([0-9]+(?:\.[0-9]+){1,2})-", txt)
        if m:
            return m.group(1)
        # NeoForge userdev usually derives MC from properties; fall back to gradle.properties
    gp = ws / "gradle.properties"
    if storage.exists(gp):
        gpt = storage.read_text(gp)
        m = re.search(r"(?m)^\s*(?:minecraft_version|mc_version)\s*=\s*([0-9]+(?:\.[0-9]+){1,2})\s*$", gpt)
        if m:
            return m.group(1)
    return None


# -----------------------------------------------------------------------------
# DRM repo management (Groovy/KTS) – merge-in-place, DSL-aware
# -----------------------------------------------------------------------------

# Minimal lines we want to ensure exist inside dependencyResolutionManagement.repositories
_GROOVY_REPO_LINES = [
    'maven { name = "Forge"; url = uri("https://maven.minecraftforge.net") }',
    'maven { name = "Minecraft libraries"; url = uri("https://libraries.minecraft.net") }',
    'maven { name = "Sponge"; url = uri("https://repo.spongepowered.org/repository/maven-public/") }',
    "mavenCentral()",
    "google()",
]
_KTS_REPO_LINES = [
    'maven("https://maven.minecraftforge.net") { name = "Forge" }',
    'maven("https://libraries.minecraft.net") { name = "Minecraft libraries" }',
    'maven("https://repo.spongepowered.org/repository/maven-public/") { name = "Sponge" }',
    "mavenCentral()",
    "google()",
]

# DRM templates (used if we must create a whole block)
FORGE_SETTINGS_GROOVY = """\
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.PREFER_PROJECT)
    repositories {
        maven { name = "Forge"; url = uri("https://maven.minecraftforge.net") }
        maven { name = "Minecraft libraries"; url = uri("https://libraries.minecraft.net") }
        maven { name = "Sponge"; url = uri("https://repo.spongepowered.org/repository/maven-public/") }
        mavenCentral()
        google()
    }
}
"""

FORGE_SETTINGS_KTS = """\
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.PREFER_PROJECT)
    repositories {
        maven("https://maven.minecraftforge.net") { name = "Forge" }
        maven("https://libraries.minecraft.net") { name = "Minecraft libraries" }
        maven("https://repo.spongepowered.org/repository/maven-public/") { name = "Sponge" }
        mavenCentral()
        google()
    }
}
"""

def _find_block_span(text: str, header_regex: str) -> Optional[Tuple[int, int]]:
    """
    Find the span [start, end) of the first block matching 'keyword { ... }'
    identified by header_regex which should match up to just before the opening brace.
    Returns None if not found or braces are unbalanced.
    """
    m = re.search(header_regex, text)
    if not m:
        return None
    # Find the first '{' after the header
    i = text.find("{", m.end())
    if i == -1:
        return None
    depth = 0
    for j in range(i, len(text)):
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return (m.start(), j + 1)
    return None

def _ensure_repos_in_drm_block(drm_text: str, is_kts: bool) -> tuple[str, bool]:
    """
    Inside a dependencyResolutionManagement { ... } block, ensure:
      - repositoriesMode.set(...) == PREFER_PROJECT (replace all occurrences)
      - repositories { ... } exists
      - required repos exist (by URL tokens / keywords); append missing ones.
    Returns (new_text, changed)
    """
    original = drm_text

    # Force PREFER_PROJECT for all occurrences within DRM block
    drm_text_new = re.sub(
        r"repositoriesMode\.set\(RepositoriesMode\.\w+\)",
        "repositoriesMode.set(RepositoriesMode.PREFER_PROJECT)",
        drm_text,
    )

    # Find repositories { ... } inside DRM
    repo_span = _find_block_span(drm_text_new, r"repositories\s*\(" if is_kts else r"repositories\s*")
    if repo_span is None:
        # create a repositories block at the end, before the final closing brace
        insert_at = len(drm_text_new) - 1 if drm_text_new.rstrip().endswith("}") else len(drm_text_new)
        lines = _KTS_REPO_LINES if is_kts else _GROOVY_REPO_LINES
        repo_block = "    repositories {\n" + "".join(f"        {ln}\n" for ln in lines) + "    }\n"
        # insert before last '}' of DRM
        # find last '}' in drm_text_new
        last_brace = drm_text_new.rfind("}")
        if last_brace != -1:
            drm_text_new = drm_text_new[:last_brace] + repo_block + drm_text_new[last_brace:]
        else:
            drm_text_new = drm_text_new.rstrip() + "\n" + repo_block
    else:
        # Merge missing repos within repositories block
        rs, re_ = repo_span
        body = drm_text_new[rs:re_]
        want_lines = _KTS_REPO_LINES if is_kts else _GROOVY_REPO_LINES

        def has_url(url: str) -> bool:
            return url in body

        def has_token(tok: str) -> bool:
            # for mavenCentral()/google() we just check the token
            return re.search(rf"(?m)^\s*{re.escape(tok)}\s*\(\s*\)\s*$", body) is not None

        missing: list[str] = []
        # URL-based checks
        if not has_url("https://maven.minecraftforge.net"):
            missing.append(want_lines[0])
        if not has_url("https://libraries.minecraft.net"):
            missing.append(want_lines[1])
        if not has_url("https://repo.spongepowered.org/repository/maven-public/"):
            missing.append(want_lines[2])
        # token-based checks
        if not has_token("mavenCentral"):
            missing.append("mavenCentral()")
        if not has_token("google"):
            missing.append("google()")

        if missing:
            # Insert before the closing brace of the repositories block
            close = body.rfind("}")
            if close == -1:
                close = len(body)
            insertion = "".join(f"        {ln}\n" for ln in missing)
            body = body[:close] + insertion + body[close:]
            drm_text_new = drm_text_new[:rs] + body + drm_text_new[re_:]

    return drm_text_new, (drm_text_new != original)

def _pick_settings_file(ws: Path, storage) -> tuple[Path, bool]:
    """
    Decide which settings file to use.
    Returns (path, is_kts).
    Prefers existing settings.gradle(.kts). If none, chooses based on build DSL.
    """
    g = ws / "settings.gradle"
    k = ws / "settings.gradle.kts"
    if storage.exists(g):
        return g, False
    if storage.exists(k):
        return k, True
    # Create: choose DSL by build file
    if storage.exists(ws / "build.gradle.kts") and not storage.exists(ws / "build.gradle"):
        return k, True
    return g, False

def patch_settings_repositories(ws: Path) -> str:
    """
    Merge/ensure dependencyResolutionManagement.repositories with required repos.
    Never creates duplicate DRM blocks. Creates the appropriate settings file (Groovy/KTS)
    if missing, based on the build DSL.
    """
    from backend.agent.wrappers.storage import STORAGE as storage

    settings_path, is_kts = _pick_settings_file(ws, storage)
    exists = storage.exists(settings_path)
    text = storage.read_text(settings_path) if exists else ""

    # Find existing DRM block
    drm_span = _find_block_span(text, r"dependencyResolutionManagement\s*")
    if drm_span:
        s, e = drm_span
        head, drm, tail = text[:s], text[s:e], text[e:]
        drm_new, changed = _ensure_repos_in_drm_block(drm, is_kts=is_kts)
        new_text = head + drm_new + tail
        if changed:
            storage.write_text(settings_path, new_text)
            return f"settings: dependencyResolutionManagement merged ({'kts' if is_kts else 'groovy'})"
        else:
            # Ensure we don't have a second DRM elsewhere; if not, no change
            return f"settings: dependencyResolutionManagement already OK ({'kts' if is_kts else 'groovy'})"
    else:
        # No DRM at all → append a fresh block
        tpl = FORGE_SETTINGS_KTS if is_kts else FORGE_SETTINGS_GROOVY
        new_text = (text.rstrip() + "\n\n" + tpl) if text.strip() else tpl
        storage.write_text(settings_path, new_text)
        return f"settings: created dependencyResolutionManagement => PREFER_PROJECT ({'kts' if is_kts else 'groovy'})"


# -----------------------------------------------------------------------------
# LWJGL macOS patch (Forge) – robust brace-aware removal + scoped override
# -----------------------------------------------------------------------------

def _find_all_block_spans(text: str, header_regex: str) -> list[Tuple[int, int]]:
    spans = []
    pos = 0
    while True:
        m = re.search(header_regex, text[pos:])
        if not m:
            break
        start = pos + m.start()
        # find '{' after header
        brace = text.find("{", pos + m.end())
        if brace == -1:
            break
        depth = 0
        for j in range(brace, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    spans.append((start, j + 1))
                    pos = j + 1
                    break
        else:
            break
    return spans

def _remove_one_lwjgl_pin_exclusive_content(text: str) -> tuple[str, bool]:
    """
    Remove (at most) one 'exclusiveContent { ... }' block that pins org.lwjgl
    (includeGroup|includeGroupAndSubgroups|includeModule("org.lwjgl", ...)).
    Brace-aware to avoid false positives. Returns (new_text, removed).
    """
    spans = _find_all_block_spans(text, r"exclusiveContent\s*")
    for s, e in spans:
        block = text[s:e]
        # detect org.lwjgl pin inside filter { ... }
        if re.search(r'include(Group|GroupAndSubgroups)\s*\(\s*["\']org\.lwjgl["\']\s*\)', block) or \
           re.search(r'includeModule\s*\(\s*["\']org\.lwjgl["\']\s*,', block):
            # Also ensure it's steering to a single repo (commonly mavenCentral)
            # but we won't enforce which repo – just remove the pin block.
            new_text = text[:s] + "// MM_LWJGL_MACOS_PATCH: removed org.lwjgl exclusiveContent pin\n" + text[e:]
            return new_text, True
    return text, False

def patch_forge_build_gradle_for_lwjgl_macos_patch(ws: Path) -> str:
    """
    Forge-only: allow Gradle to fetch the macOS patched LWJGL freetype from Forge's maven.
    Idempotent and safe to run multiple times. Uses storage wrapper.
    """
    from backend.agent.wrappers.storage import STORAGE as storage

    g = ws / "build.gradle"
    k = ws / "build.gradle.kts"
    target = g if storage.exists(g) else (k if storage.exists(k) else None)
    if not target:
        return "no build.gradle(.kts) found"

    txt = storage.read_text(target)
    if "MM_LWJGL_MACOS_PATCH" in txt:
        return "already patched"

    # 1) Remove one org.lwjgl exclusiveContent pin (if any)
    txt2, removed = _remove_one_lwjgl_pin_exclusive_content(txt)

    # 2) Add a narrow override for just lwjgl-freetype from Forge maven
    if target.suffix == ".kts":
        snippet = """
// MM_LWJGL_MACOS_PATCH (kts): allow Forge's patched macOS natives
repositories {
    exclusiveContent {
        forRepository(maven("https://maven.minecraftforge.net"))
        filter {
            includeModule("org.lwjgl", "lwjgl-freetype")
        }
    }
}
// /MM_LWJGL_MACOS_PATCH
"""
    else:
        snippet = """
// MM_LWJGL_MACOS_PATCH (groovy): allow Forge's patched macOS natives
repositories {
    exclusiveContent {
        forRepository {
            maven { url = "https://maven.minecraftforge.net" }
        }
        filter {
            includeModule("org.lwjgl", "lwjgl-freetype")
        }
    }
}
// /MM_LWJGL_MACOS_PATCH
"""

    new_text = txt2.rstrip() + "\n\n" + snippet
    if new_text != txt:
        storage.write_text(target, new_text)
    return f"applied LWJGL macOS patch to {target.name}{' (removed conflicting pin)' if removed else ''}"


# -----------------------------------------------------------------------------
# Parchment enablement (Forge / NeoForge)
# -----------------------------------------------------------------------------

# --- replace this helper with the version below --------------------------------

def _detect_mc_version_from_build(ws: Path, storage) -> Optional[str]:
    """
    Prefer reading the version from gradle.properties (minecraft_version or mc_version).
    Fall back to parsing build.gradle(.kts) Forge coordinates if necessary.
    """
    # 1) Prefer gradle.properties
    gp = ws / "gradle.properties"
    if storage.exists(gp):
        gpt = storage.read_text(gp)
        m = re.search(r"(?m)^\s*(?:minecraft_version|mc_version)\s*=\s*([0-9]+(?:\.[0-9]+){1,2})\s*$", gpt)
        if m:
            return m.group(1)

    # 2) Fallback: try build.gradle(.kts) Forge coordinate pattern
    g = ws / "build.gradle"
    k = ws / "build.gradle.kts"
    target = g if storage.exists(g) else (k if storage.exists(k) else None)
    if target:
        txt = storage.read_text(target)
        # Forge-style coordinate: net.minecraftforge:forge:<mc>-<forge>
        m = re.search(r"net\.minecraftforge:forge:([0-9]+(?:\.[0-9]+){1,2})-", txt)
        if m:
            return m.group(1)

    return None

def enable_parchment_for_forge(ws: Path, mc_version: Optional[str] = None) -> str:
    """
    Always enable Parchment for a Forge workspace, without branching on ForgeGradle version.

    Exactly does:
      1) Ensure ParchmentMC repo in pluginManagement.repositories (settings.gradle/.kts)
      2) Apply Librarian plugin (version '1.+') BELOW the ForgeGradle plugin in build.gradle(.kts)
      3) Create a minimal `minecraft { mappings ... }` block ONLY IF MISSING (never modify an existing block)
      4) Update gradle.properties with mapping_channel/version (+ legacy plurals)

    Returns a short status string.
    """

    # ---- 0) Minecraft version (use the already-imported helper) ----
    mc_detected = detect_minecraft_version(ws)
    if not mc_detected:
        raise ValueError(
            "Could not determine Minecraft version. "
            "Ensure gradle.properties contains 'minecraft_version=<major.minor[.patch]>' or 'mc_version=...'."
        )

    # ---- 1) Resolve parchment tag from the shared map (use module helpers) ----
    map_path = _parchment_map_path()
    if not map_path.exists():
        raise FileNotFoundError(f"parchment_versions.json not found at {map_path}.")
    data = json.loads(map_path.read_text(encoding="utf-8")) or {}
    table: dict[str, str] = data.get("minecraft_to_parchment", {}) or {}

    # _nearest_parchment_date_for returns (date_str|None, chosen_mc_key)
    date, chosen_mc = _nearest_parchment_date_for(mc_detected, table)
    version_tag = f"{(date or 'TBD')}-{chosen_mc}"

    # ---- 2) settings.gradle/.kts: ensure Parchment plugin repo ----
    def _ensure_plugin_repo(text: str, is_kts: bool) -> str:
        if "parchmentmc.org" in text and "pluginManagement" in text:
            return text
        pattern = r"(pluginManagement\s*\{\s*repositories\s*\{\s*)"
        repl = r"\1" + ('maven("https://maven.parchmentmc.org")\n' if is_kts
                        else 'maven { url = uri("https://maven.parchmentmc.org") }\n')
        patched, n = re.subn(pattern, repl, text, count=1, flags=re.S)
        if n:
            return patched
        repo_line = ('        maven("https://maven.parchmentmc.org")\n' if is_kts
                     else '        maven { url = uri("https://maven.parchmentmc.org") }\n')
        add = "pluginManagement {\n    repositories {\n" + repo_line + "    }\n}\n"
        return (text.rstrip() + "\n\n" + add) if text.strip() else add

    gs, ks = ws / "settings.gradle", ws / "settings.gradle.kts"
    if storage.exists(gs):
        t = storage.read_text(gs); p = _ensure_plugin_repo(t, False)
        if p != t: storage.write_text(gs, p); settings_status = "settings.gradle: patched"
        else: settings_status = "settings.gradle: unchanged"
    elif storage.exists(ks):
        t = storage.read_text(ks); p = _ensure_plugin_repo(t, True)
        if p != t: storage.write_text(ks, p); settings_status = "settings.gradle.kts: patched"
        else: settings_status = "settings.gradle.kts: unchanged"
    else:
        if storage.exists(ws / "build.gradle.kts") and not storage.exists(ws / "build.gradle"):
            storage.write_text(ks, 'pluginManagement {\n    repositories {\n        maven("https://maven.parchmentmc.org")\n    }\n}\n')
            settings_status = "settings.gradle.kts: created"
        else:
            storage.write_text(gs, 'pluginManagement {\n    repositories {\n        maven { url = uri("https://maven.parchmentmc.org") }\n    }\n}\n')
            settings_status = "settings.gradle: created"

    # ---- 3) build.gradle(.kts): add Librarian; create minecraft{} only if missing ----
    g, k = ws / "build.gradle", ws / "build.gradle.kts"
    target = g if storage.exists(g) else (k if storage.exists(k) else None)
    if not target:
        build_status = "build: no build.gradle(.kts)"
    else:
        bt = storage.read_text(target)
        is_kts = target.suffix == ".kts"

        # 3a) Apply Librarian v1.+ below ForgeGradle
        lib_line = ('    id("org.parchmentmc.librarian.forgegradle") version "1.+"\n'
                    if is_kts else
                    "    id 'org.parchmentmc.librarian.forgegradle' version '1.+'\n")
        if re.search(r'org\.parchmentmc\.librarian\.forgegradle', bt) is None:
            m_plugins = re.search(r"(plugins\s*\{)(.*?)(\})", bt, flags=re.S)
            if m_plugins:
                head, body, tail = m_plugins.groups()
                m_fg = re.search(
                    r'(?m)^\s*id\(\s*["\']net\.minecraftforge\.gradle["\']\s*\).*?$' if is_kts
                    else r"(?m)^\s*id\s+['\"]net\.minecraftforge\.gradle['\"].*?$",
                    body,
                )
                if m_fg:
                    idx = m_fg.end()
                    body = body[:idx] + "\n" + lib_line + body[idx:]
                else:
                    body = lib_line + body
                bt = bt[:m_plugins.start(1)] + head + body + tail + bt[m_plugins.end(3):]
            else:
                bt = "plugins {\n" + lib_line + "}\n\n" + bt
        else:
            # normalize version to 1.+
            bt = (re.sub(r'(id\("org\.parchmentmc\.librarian\.forgegradle"\)\s*version\s*")([^"]+)(")',
                         r'\g<1>1.+\3', bt, flags=re.S)
                  if is_kts else
                  re.sub(r"(id\s+'org\.parchmentmc\.librarian\.forgegradle'\s+version\s+')([^']+)(')",
                         r"\g<1>1.+\3", bt, flags=re.S))

        # 3b) Create minecraft{} ONLY IF MISSING; never touch if present
        has_block = re.search(r"(?:^|\n)\s*minecraft\s*\{", bt) is not None
        if not has_block:
            block = (
                "minecraft {\n"
                f"    mappings channel: 'parchment', version: '{version_tag}'\n"
                "}\n"
            ) if not is_kts else (
                "minecraft {\n"
                f'    mappings("parchment", "{version_tag}")\n'
                "}\n"
            )
            bt = (bt.rstrip() + "\n\n" + block) if bt.strip() else block
            build_status = f"{target.name}: librarian set; minecraft{{}} created ({version_tag})"
        else:
            build_status = f"{target.name}: librarian set; minecraft{{}} unchanged"

        storage.write_text(target, bt)

    # ---- 4) gradle.properties: set parchment keys ----
    gp = ws / "gradle.properties"
    gpt = storage.read_text(gp) if storage.exists(gp) else ""
    orig = gpt
    for key in ("mapping_channel", "mappings_channel", "mapping_version", "mappings_version"):
        gpt = re.sub(rf"(?m)^\s*{key}\s*=.*\n?", "", gpt)
    lines = [
        "mapping_channel=parchment",
        f"mapping_version={version_tag}",
        "mappings_channel=parchment",
        f"mappings_version={version_tag}",
    ]
    gpt_new = (gpt.rstrip() + "\n\n" + "\n".join(lines) + "\n") if gpt.strip() else ("\n".join(lines) + "\n")
    if gpt_new != orig:
        storage.write_text(gp, gpt_new)
        prop_status = "gradle.properties: set parchment keys"
    else:
        prop_status = "gradle.properties: unchanged"

    warn = "" if date else " | WARNING: using TBD; update parchment_versions.json"
    return f"{settings_status} | {build_status} | {prop_status}{warn}"


# --- replace enable_parchment_for_neoforge with the version below --------------

def enable_parchment_for_neoforge(ws: Path, mc_version: Optional[str] = None) -> str:
    """
    NeoForge: DO NOT touch settings.gradle or build.gradle structure.
    NOTE: The mc_version parameter is IGNORED (kept only for backward-compat).
    The Minecraft version is read from gradle.properties (minecraft_version or mc_version),
    falling back to build.gradle(.kts) detection. If not found, this function raises.

    Simply sets gradle.properties mapping_channel/mapping_version (and legacy plurals),
    as userdev resolves mappings from properties.
    """

    # 0) MC version from gradle.properties (preferred) or build detection
    mc_detected = detect_minecraft_version(ws)
    if not mc_detected:
        raise ValueError(
            "Could not determine Minecraft version. "
            "Ensure gradle.properties contains 'minecraft_version=<major.minor[.patch]>' "
            "or 'mc_version=...'."
        )

    # 1) Read mapping table
    map_path = _parchment_map_path()
    if not map_path.exists():
        raise FileNotFoundError(
            f"parchment_versions.json not found at {map_path}. This file is required; no fallback is allowed."
        )
    data = json.loads(map_path.read_text(encoding="utf-8")) or {}
    table = data.get("minecraft_to_parchment", {}) or {}

    date, _ = _nearest_parchment_date_for(mc_detected, table)
    version_tag = f"{(date or 'TBD')}-{mc_detected}"

    # 2) gradle.properties only
    gp = ws / "gradle.properties"
    gpt = storage.read_text(gp) if storage.exists(gp) else ""
    orig = gpt

    for key in ("mapping_channel", "mappings_channel", "mapping_version", "mappings_version"):
        gpt = re.sub(rf"(?m)^\s*{key}\s*=.*\n?", "", gpt)

    lines = [
        "mapping_channel=parchment",
        f"mapping_version={version_tag}",
        "mappings_channel=parchment",
        f"mappings_version={version_tag}",
    ]
    gpt_new = (gpt.rstrip() + "\n\n" + "\n".join(lines) + "\n") if gpt.strip() else ("\n".join(lines) + "\n")

    if gpt_new != orig:
        storage.write_text(gp, gpt_new)
        return f"gradle.properties set (NeoForge) {version_tag}"
    return f"gradle.properties unchanged (NeoForge) {version_tag}"

