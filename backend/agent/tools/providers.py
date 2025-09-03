"""
Providers for downloading a fresh starter (MDK / template) per framework & MC version.

This module intentionally does **no caching** — call it every time for now.
Later, you can plug it behind a cache layer without changing call sites.

Public surface:
- resolve_url(framework: str, mc_version: str) -> str
- download(url: str, dest_path: Path, *, timeout: int = 120) -> None

Supported frameworks (initial): "forge", "fabric", "neoforge".

Notes:
- Forge URL derives from official promotions metadata (latest/recommended).
- Fabric uses the example mod repo. We attempt a versioned branch (e.g. "1.21"),
  then fallback to "main".
- NeoForge pulls the latest version from maven metadata and builds the MDK URL.

These resolvers are conservative and may need refinement per version cycle.
Keep them small and replaceable.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
import json
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
import urllib.parse
import contextlib
from backend.core.models import Framework

USER_AGENT = "MineModder/0.1 (+https://example.invalid)"


@dataclass(frozen=True)
class ProviderResult:
    url: str
    filename: str
    notes: str = ""


# --------------------
# Public API
# --------------------

def resolve_url(framework: Framework, mc_version: str) -> ProviderResult:
    if framework is Framework.FORGE:
        return _resolve_forge_mdk_url(mc_version)
    if framework is Framework.FABRIC:
        return _resolve_fabric_template_url(mc_version)
    if framework is Framework.NEOFORGE:
        return _resolve_neoforge_mdk_url(mc_version)
    # This becomes a safeguard against unhandled enum members,
    # rather than a catch-all for bad user input.
    raise ValueError(f"Unsupported framework: {framework}")


def download(url: str, dest_path: Path, *, timeout: int = 120) -> None:
    """Stream download to disk with a small buffer and basic error surfacing.
    Overwrites dest_path if it exists.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with contextlib.closing(urllib.request.urlopen(req, timeout=timeout)) as r, open(dest_path, "wb") as f:
            chunk = r.read(8192)
            while chunk:
                f.write(chunk)
                chunk = r.read(8192)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} when downloading {url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error downloading {url}: {e.reason}") from e


# --------------------
# Forge
# --------------------

FORGE_PROMOTIONS = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"


FORGE_PROMOTIONS = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"

def _resolve_forge_mdk_url(mc_version: str) -> ProviderResult:
    """
    Use Forge promotions to map MC version -> latest/recommended Forge version.
    MDK URL form:
      https://maven.minecraftforge.net/net/minecraftforge/forge/<ver>/forge-<ver>-mdk.zip
    where <ver> looks like "1.21.7-57.0.3".
    """
    data = _http_json(FORGE_PROMOTIONS)
    promos: dict = data.get("promos", {}) or {}

    parts = mc_version.split(".")
    # If user gave only major.minor (e.g., "1.21"), pick the highest patch that has recommended, else latest
    if len(parts) == 2:
        prefix = f"{mc_version}."
        # Collect available patches per channel
        patch_rec = []
        patch_lat = []
        for k in promos.keys():
            if not k.startswith(prefix):
                continue
            # k like "1.21.7-recommended" -> extract "7" and channel
            tail = k[len(prefix):]  # "7-recommended"
            patch_str, _, channel = tail.partition("-")
            if patch_str.isdigit():
                if channel == "recommended":
                    patch_rec.append(int(patch_str))
                elif channel == "latest":
                    patch_lat.append(int(patch_str))

        if patch_rec:
            patch = max(patch_rec)
            channel = "recommended"
        elif patch_lat:
            patch = max(patch_lat)
            channel = "latest"
        else:
            raise RuntimeError(f"No Forge builds found for MC line {mc_version} in promotions")

        mc_exact = f"{mc_version}.{patch}"
        forge_build = promos.get(f"{mc_exact}-{channel}")
        if not forge_build:
            raise RuntimeError(f"Forge promotions missing build value for {mc_exact}-{channel}")

    else:
        # Full version provided (e.g., "1.21.7")
        mc_exact = mc_version
        key_rec = f"{mc_exact}-recommended"
        key_lat = f"{mc_exact}-latest"
        forge_build = promos.get(key_rec) or promos.get(key_lat)
        if not forge_build:
            raise RuntimeError(f"Forge promotions has no build for MC {mc_exact}")

    version = f"{mc_exact}-{forge_build}"
    filename = f"forge-{version}-mdk.zip"
    url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{version}/{filename}"
    return ProviderResult(url=url, filename=filename, notes="forge promotions_slim.json")



# --------------------
# Fabric
# --------------------

FABRIC_EXAMPLE_REPO = "https://codeload.github.com/FabricMC/fabric-example-mod/zip/refs/heads/{branch}"


def _resolve_fabric_template_url(mc_version: str) -> ProviderResult:
    """Try a versioned example-mod branch like "1.21"; fallback to main.
    The example mod is a template you will parameterize later (loom, mappings, etc.).
    """
    # Try major.minor branch, e.g., "1.21" from "1.21.1"
    parts = mc_version.split(".")
    branch_guess = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else mc_version

    # Probe the branch; if 404, fallback to main (we don't download content here, only HEAD)
    branch_url = FABRIC_EXAMPLE_REPO.format(branch=branch_guess)
    if _url_exists(branch_url):
        return ProviderResult(url=branch_url, filename=f"fabric-example-mod-{branch_guess}.zip", notes="fabric example branch")
    # Fallback
    main_url = FABRIC_EXAMPLE_REPO.format(branch="main")
    return ProviderResult(url=main_url, filename="fabric-example-mod-main.zip", notes="fabric example main")


# --------------------
# NeoForge
# --------------------

NEOFORGE_GH_ZIP = "https://codeload.github.com/NeoForgeMDKs/{repo}/zip/refs/heads/main"

def _resolve_neoforge_mdk_url(mc_version: str) -> ProviderResult:
    """
    Resolve NeoForge MDK from the NeoForgeMDKs organization on GitHub.
    Repos are named like:
      - MDK-1.21.8-NeoGradle
      - MDK-1.21.8-ModDevGradle
      - (fallback for a line) MDK-1.21-NeoGradle, MDK-1.21-ModDevGradle
    We try exact patch first (if given), then the line, preferring NeoGradle.
    Resulting ZIP is the GitHub branch archive (…/<repo>/zip/refs/heads/main),
    which downloads as "<repo>-main.zip".
    """
    parts = mc_version.split(".")
    candidates = []
    # Prefer NeoGradle, then ModDevGradle
    plugins = ("NeoGradle", "ModDevGradle")

    if len(parts) >= 3:
        v_line = f"{parts[0]}.{parts[1]}"     # e.g., "1.21"
        v_full = mc_version                   # e.g., "1.21.8"
        for plug in plugins:
            candidates.append(f"MDK-{v_full}-{plug}")  # exact patch
        for plug in plugins:
            candidates.append(f"MDK-{v_line}-{plug}")  # line fallback
    else:
        v_line = mc_version
        for plug in plugins:
            candidates.append(f"MDK-{v_line}-{plug}")

    for repo in candidates:
        url = NEOFORGE_GH_ZIP.format(repo=repo)
        if _url_exists(url):
            # GitHub serves it as "<repo>-main.zip"
            filename = f"{repo}-main.zip"
            return ProviderResult(url=url, filename=filename, notes="NeoForgeMDKs GitHub")

    raise RuntimeError(f"Could not find a NeoForge MDK repo for MC {mc_version} under NeoForgeMDKs/*")



# --------------------
# Small HTTP helpers
# --------------------

def _http_json(url: str) -> dict:
    txt = _http_text(url)
    try:
        return json.loads(txt)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from {url}: {e}") from e


def _http_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with contextlib.closing(urllib.request.urlopen(req, timeout=30)) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} fetching {url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error fetching {url}: {e.reason}") from e


def _url_exists(url: str) -> bool:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with contextlib.closing(urllib.request.urlopen(req, timeout=10)):
            return True
    except Exception:
        return False
