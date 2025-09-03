"""
End‑to‑end initializer: from provider download → extract → workspace → placeholders
→ java toolchain → Gradle smoke build.

Usage (from repo root):

  python -m backend.tests.init_e2e \
    --framework forge fabric neoforge \
    --mc 1.21 \
    --modid redsapphire \
    --group io.nimi \
    --package io.nimi.redsapphire \
    --name "Red Sapphire" \
    --desc "A demo mod scaffolded by MineModder" \
    --author Nimi \
    --timeout 1200

You can target one framework too (e.g., just `--framework forge`).
Exit code 0 means all requested frameworks completed the smoke build.
"""
from __future__ import annotations

import argparse
import sys
import platform  # <-- Added for architecture detection
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

from backend.agent.tools.providers import resolve_url, download
from backend.agent.tools.archive import extract_archive
from backend.core.models import Framework
from backend.agent.tools.workspace import create as ws_create, copy_from_extracted
from backend.agent.tools.placeholders import apply_placeholders
from backend.agent.tools.java_toolchain import java_for, patch_toolchain
# <-- Import your new function
from backend.agent.tools.repositories import patch_settings_repositories
from backend.agent.tools.gradle import smoke_build

GREEN = "\x1b[32m"
RED = "\x1b[31m"
YELLOW = "\x1b[33m"
DIM = "\x1b[2m"
RESET = "\x1b[0m"


@dataclass
class StepResult:
    name: str
    ok: bool
    msg: str = ""


def _print_step(step: StepResult) -> None:
    color = GREEN if step.ok else RED
    status = "OK" if step.ok else "FAIL"
    print(f"- {color}{status}{RESET} {step.name}{DIM}{(': ' + step.msg) if step.msg else ''}{RESET}")


def _do_one(framework: str, mc_version: str, modid: str, group: str, package: str,
            runs_root: Path, downloads_root: Path, timeout: int,
            name: Optional[str], desc: Optional[str], authors: List[str], task_override: Optional[str]) -> int:
    print(f"\n=== {framework} @ MC {mc_version} ===")

    # 1) Resolve + download
    try:
        try:
            fw_enum = Framework[framework.upper()]
        except Exception:
            raise ValueError(f"Unknown framework enum: {framework}")
        pr = resolve_url(fw_enum, mc_version)
        _print_step(StepResult("resolve_url", True, f"{pr.url}"))
    except Exception as e:
        _print_step(StepResult("resolve_url", False, str(e)))
        return 2

    dl_dir = downloads_root / framework / mc_version
    dl_dir.mkdir(parents=True, exist_ok=True)
    dest_zip = dl_dir / pr.filename

    try:
        download(pr.url, dest_zip)
        _print_step(StepResult("download", True, f"→ {dest_zip} ({dest_zip.stat().st_size} bytes)"))
    except Exception as e:
        _print_step(StepResult("download", False, str(e)))
        return 2

    # 2) Extract
    extracted_dir = dl_dir / "extracted"
    try:
        root = extract_archive(dest_zip, extracted_dir)
        _print_step(StepResult("extract_archive", True, f"root={root}"))
    except Exception as e:
        _print_step(StepResult("extract_archive", False, str(e)))
        return 3

    # 3) Create workspace and copy
    try:
        ws = ws_create(runs_root, modid=modid, framework=framework, mc_version=mc_version)
        copy_from_extracted(root, ws)
        _print_step(StepResult("workspace", True, f"{ws}"))
    except Exception as e:
        _print_step(StepResult("workspace", False, str(e)))
        return 4

    # 4) Placeholders
    try:
        ph = apply_placeholders(
            ws, framework,
            modid=modid,
            group=group,
            package=package,
            mc_version=mc_version,
            display_name=name,
            description=desc,
            authors=authors or None,
        )
        _print_step(StepResult("placeholders", True, f"changed={len(ph.get('changed_files', []))}, notes={ph.get('notes', [])}"))
    except Exception as e:
        _print_step(StepResult("placeholders", False, str(e)))
        return 5

    # 5) Java toolchain ...
    try:
        jv = java_for(mc_version)
        patch = patch_toolchain(ws, jv, group=group)
        _print_step(StepResult("java_toolchain", True, f"java={jv}, files={patch.get('results')}"))
    except Exception as e:
        _print_step(StepResult("java_toolchain", False, str(e)))
        return 6

    # 6) Repository patch (settings)
    try:
        msg = patch_settings_repositories(ws)  # leaves PREFER_PROJECT; no extra repos for Forge
        _print_step(StepResult("repository_patch", True, msg))
    except Exception as e:
        _print_step(StepResult("repository_patch", False, str(e)))
        return 7

    # 6b) Forge-only: let freetype resolve from Forge maven (macOS patched classifier)
    try:
        if framework == "forge":
            from backend.agent.tools.repositories import patch_forge_build_gradle_for_lwjgl_macos_patch
            msg2 = patch_forge_build_gradle_for_lwjgl_macos_patch(ws)
            _print_step(StepResult("forge_lwjgl_patch", True, msg2))
    except Exception as e:
        _print_step(StepResult("forge_lwjgl_patch", False, str(e)))
        return 7

    # 7) Gradle smoke build
    try:
        res = smoke_build(framework, ws, task_override=task_override, timeout=timeout)
        _print_step(StepResult("gradle_smoke", res.get("ok", False),
                            f"task={res.get('task')} exit={res.get('exit_code')} log={res.get('log_path')}"))
        return 0 if res.get("ok", False) else 8
    except Exception as e:
        _print_step(StepResult("gradle_smoke", False, str(e)))
        return 8


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--framework", nargs="+", required=True, choices=["forge", "fabric", "neoforge"])
    ap.add_argument("--mc", required=True, help="Minecraft version line (e.g. 1.21)")
    ap.add_argument("--modid", required=True)
    ap.add_argument("--group", required=True)
    ap.add_argument("--package", required=True)
    ap.add_argument("--name")
    ap.add_argument("--desc")
    ap.add_argument("--author", action="append", default=[], help="Repeatable: --author Alice --author Bob")
    ap.add_argument("--runs-root", default="runs")
    ap.add_argument("--downloads-root", default="runs/_downloads")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--task", dest="task_override")
    args = ap.parse_args(argv)

    runs_root = Path(args.runs_root)
    downloads_root = Path(args.downloads_root)

    print(f"== init_e2e ==\nFrameworks: {', '.join(args.framework)}\nMC: {args.mc}\nRuns root: {runs_root}\nDownloads root: {downloads_root}\nTimeout: {args.timeout}s")

    failures = 0
    for fw in args.framework:
        rc = _do_one(
            fw, args.mc, args.modid, args.group, args.package,
            runs_root, downloads_root, args.timeout,
            args.name, args.desc, args.author, args.task_override,
        )
        if rc != 0:
            failures += 1

    print(f"\nSummary: {len(args.framework) - failures} OK, {failures} FAIL")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())