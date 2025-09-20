from pathlib import Path
from ..state import AgentState
from ...core.models import Framework
from ..wrappers.storage import STORAGE as storage
from ..tools.init.providers import resolve_url, download
from ..tools.init.archive import extract_archive
from ..tools.init.workspace import create as ws_create, copy_from_extracted
from ..tools.init.version import detect_minecraft_version
from ..tools.init.placeholders import apply_placeholders
from ..tools.init.java_toolchain import java_for, patch_toolchain
from ..tools.init.repositories import (
    patch_settings_repositories,
    patch_forge_build_gradle_for_lwjgl_macos_patch,
    enable_parchment_for_forge,
    enable_parchment_for_neoforge
)
from ..tools.init.gradle import smoke_build
from .template_init import template_init


def init_subgraph(state: AgentState) -> AgentState:
    """Run the real initialization pipeline using inferred params."""

    print("[ENTER] node:init_subgraph")

    framework = state.get("framework")
    mc_version = state.get("mc_version")
    modid = state.get("modid")
    group = state.get("group")
    package = state.get("package")
    display_name = state.get("display_name")
    description = state.get("description")
    authors = state.get("authors") or []
    timeout = int(state.get("timeout", 1800))

    runs_root = Path(state.get("runs_root") or "runs")
    downloads_root = Path(state.get("downloads_root") or "runs/_downloads")

    # 1) Resolve + download
    fw_enum = Framework[framework.upper()]
    pr = resolve_url(fw_enum, mc_version)
    dl_dir = downloads_root / framework / mc_version

    storage.ensure_dir(dl_dir)
    dest_zip = dl_dir / pr.filename
    download(pr.url, dest_zip)

    # Record artifacts for tests/snapshots
    state.setdefault("artifacts", {})["mdk_zip_path"] = str(dest_zip)
    state["artifacts"]["mdk_download_dir"] = str(dl_dir)

    # 2) Extract
    extracted_dir = dl_dir / "extracted"
    root = extract_archive(dest_zip, extracted_dir)

    # Track extracted directory for snapshotting
    state.setdefault("artifacts", {})["mdk_extracted_dir"] = str(extracted_dir)

    # 3) Create workspace and copy
    ws = ws_create(runs_root, modid=modid, framework=framework, mc_version=mc_version)
    copy_from_extracted(root, ws)

    # Expose workspace path to downstream nodes that expect it in state
    state["workspace_path"] = str(ws)

    # 3b) Detect effective Minecraft version from the MDK workspace (prefer gradle.properties)
    detected_mc = detect_minecraft_version(ws)
    # Persist in state and emit an event; this is the single source of truth downstream
    state["effective_mc_version"] = detected_mc
    state.setdefault("events", []).append({
        "node": "resolve_mdk_version", "ok": bool(detected_mc), "version": detected_mc
    })

    # 4) Placeholders (use detected MC for any version-derived writes)
    ph = apply_placeholders(
        ws, framework,
        modid=modid,
        group=group,
        package=package,
        mc_version=detected_mc,
        display_name=display_name,
        description=description,
        authors=authors or None,
    )
    # If placeholders derived a framework-specific package (e.g., net.<modid> for NeoForge), persist it
    if isinstance(ph, dict) and ph.get("package"):
        state["package"] = ph["package"]

    # 5) Toolchain (only if MDK version was detected; no fallback to user value)
    if detected_mc:
        jv = java_for(detected_mc)
        patch_toolchain(ws, jv, group=group)

    # 6) Repositories patch (idempotent)
    # Matches backend/tests/init_e2e.py behavior
    patch_settings_repositories(ws)

    # 6b) Forge-only LWJGL macOS patch on build.gradle (idempotent) and parchment enablement
    if framework == "forge":
        if detected_mc:
            enable_parchment_for_forge(ws, detected_mc)
            patch_forge_build_gradle_for_lwjgl_macos_patch(ws)

    elif framework == "neoforge":
        if detected_mc:
            enable_parchment_for_neoforge(ws, detected_mc)

    # 6c) Generic templates initialization (second to last step before smoke test)
    state = template_init(state)

    # 7) Gradle smoke build
    res = smoke_build(framework, ws, task_override=None, timeout=timeout)

    state["workspace_path"] = str(ws)
    state.setdefault("artifacts", {})["gradle_smoke"] = res
    state.setdefault("events", []).append({"node": "init_subgraph", "ok": bool(res.get("ok")), "workspace_path": str(ws)})
    return state