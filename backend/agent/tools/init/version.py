"""
Minecraft version detection utilities (MDK-first)

Goal
----
Detect the effective Minecraft version from the downloaded MDK workspace itself,
so downstream steps never rely on a user-passed value once the MDK is present.

Detection order (conservative)
------------------------------
1) gradle.properties: minecraft_version= or mc_version=
2) build.gradle / build.gradle.kts: parse well-known coordinates/patterns
   - Forge: net.minecraftforge:forge:<mc>-<forge>
   - Generic fallback: look for a "minecraft_version" property usage

If nothing is found, return None and let callers decide how to proceed.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Optional


def detect_minecraft_version(ws: Path | str) -> Optional[str]:
    from backend.agent.wrappers.storage import STORAGE as storage
    root = Path(ws)

    # 1) Prefer gradle.properties
    gp = root / "gradle.properties"
    if storage.exists(gp):
        txt = storage.read_text(gp, encoding="utf-8", errors="ignore")
        m = re.search(r"(?m)^\s*minecraft_version\s*=\s*([0-9]+(?:\.[0-9]+){1,2})\s*$", txt)
        if m:
            return m.group(1)
        m = re.search(r"(?m)^\s*mc_version\s*=\s*([0-9]+(?:\.[0-9]+){1,2})\s*$", txt)
        if m:
            return m.group(1)

    # 2) build.gradle(.kts)
    for name in ("build.gradle", "build.gradle.kts"):
        p = root / name
        if not storage.exists(p):
            continue
        txt = storage.read_text(p, encoding="utf-8", errors="ignore")
        # Forge coordinate: net.minecraftforge:forge:<mc>-<forge>
        m = re.search(r"net\.minecraftforge:forge:([0-9]+(?:\.[0-9]+){1,2})-", txt)
        if m:
            return m.group(1)
        # NeoForge or others might interpolate property; try a relaxed property assignment capture
        # This is a best-effort; we still prefer gradle.properties above
        m = re.search(r"(?m)^(?:\s*ext\.|\s*def\s+)?minecraft_version\s*=\s*\"?([0-9]+(?:\.[0-9]+){1,2})\"?\s*$", txt)
        if m:
            return m.group(1)

    return None


__all__ = ["detect_minecraft_version"]

