#!/usr/bin/env python3
"""
providers_check.py — online smoke test for agent/tools/providers.py

What it does
------------
- Calls resolve_url(framework, mc_version) for the frameworks you ask for
- Optionally downloads the resolved ZIP to a destination directory
- Prints a short report (URL, filename, bytes, sha256 when downloaded)
- Exits non‑zero if any resolution or download fails

Usage examples
--------------
# Resolve only (no downloads)
python backend/scripts/providers_check.py --framework forge fabric neoforge --mc 1.21 1.20.1

# Resolve + download into a temp directory
python backend/scripts/providers_check.py --framework forge --mc 1.21 --download

# Resolve + download into a specific directory with a longer timeout
python backend/scripts/providers_check.py --framework fabric --mc 1.20.1 --download --dest /tmp/mdk_test --timeout 240

Notes
-----
- This is an ONLINE test; it hits public endpoints for Forge/Fabric/NeoForge.
- If a provider changes its endpoints or metadata, the script will surface a clear error.
- Keep this script network‑optional in CI (e.g., guard behind an env var).
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List

# Project imports
try:
    from backend.agent.tools.init import providers
    from backend.core.models import Framework
except Exception as e:  # pragma: no cover
    sys.stderr.write("\nERROR: Could not import providers or Framework.\n")
    raise


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Online smoke test for providers.py")
    p.add_argument("--framework", "-f", nargs="+", required=True,
                   choices=["forge", "fabric", "neoforge"],
                   help="Frameworks to test")
    p.add_argument("--mc", nargs="+", required=True,
                   help="Minecraft versions to test (e.g., 1.21, 1.21.1)")
    p.add_argument("--download", action="store_true",
                   help="Also download the resolved ZIPs")
    p.add_argument("--dest", type=Path, default=None,
                   help="Destination directory for downloads (defaults to a temp dir)")
    p.add_argument("--timeout", type=int, default=120,
                   help="Per-download timeout seconds (default: 120)")
    return p.parse_args(argv)


def as_framework(name: str) -> Framework:
    m = name.lower()
    if m == "forge":
        return Framework.FORGE
    if m == "fabric":
        return Framework.FABRIC
    if m == "neoforge":
        return Framework.NEOFORGE
    raise ValueError(f"Unknown framework: {name}")


def ensure_dest_dir(dest: Path | None) -> Path:
    if dest is None:
        import tempfile
        d = Path(tempfile.mkdtemp(prefix="providers_check_"))
        return d
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    dest_dir = ensure_dest_dir(args.dest) if args.download else None

    failures = 0

    print("\n== providers_check: starting ==\n")
    print(f"Frameworks: {', '.join(args.framework)}")
    print(f"MC Versions: {', '.join(args.mc)}")
    if args.download:
        print(f"Download dest: {dest_dir}")
        print(f"Timeout: {args.timeout}s")
    print("")

    for fw_name in args.framework:
        fw_enum = as_framework(fw_name)
        for mc_version in args.mc:
            print(f"-- Resolving {fw_name} @ MC {mc_version} …", end=" ")
            try:
                result = providers.resolve_url(fw_enum, mc_version)
                print("OK")
                print(f"   url:      {result.url}")
                print(f"   filename: {result.filename}")
                if args.download:
                    out_path = (dest_dir / fw_name / mc_version)
                    out_path.mkdir(parents=True, exist_ok=True)
                    file_path = out_path / result.filename
                    print(f"   downloading → {file_path}")
                    providers.download(result.url, file_path, timeout=args.timeout)
                    size = file_path.stat().st_size
                    sha = _sha256(file_path)
                    print(f"   size: {size} bytes, sha256: {sha}")

                # Light sanity checks per framework
                # Light sanity checks per framework
                if fw_name == "forge":
                    if not result.filename.endswith("-mdk.zip"):
                        raise AssertionError("Expected a Forge MDK ZIP (…-mdk.zip)")
                elif fw_name == "neoforge":
                    # We use NeoForgeMDKs GitHub archives, e.g., MDK-1.21-NeoGradle-main.zip
                    if not (result.filename.startswith("MDK-") and result.filename.endswith(".zip")):
                        raise AssertionError("Expected a NeoForge MDK GitHub ZIP (e.g., MDK-…-main.zip)")
                elif fw_name == "fabric" and not result.filename.endswith(".zip"):
                    raise AssertionError("Expected a zip filename for fabric example mod")

            except NameError as ne:
                # Common coding mistake guard: undefined key_rec in forge resolver
                print("FAIL (NameError)")
                print("   Hint: Did you define 'key_rec' before using it in _resolve_forge_mdk_url? ")
                print("   Exception:")
                traceback.print_exc(limit=1)
                failures += 1
            except Exception:
                print("FAIL")
                traceback.print_exc(limit=1)
                failures += 1
            print("")

    print("== providers_check: done ==")
    if failures:
        print(f"Failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
