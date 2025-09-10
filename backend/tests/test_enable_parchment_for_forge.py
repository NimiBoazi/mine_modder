from __future__ import annotations

import json
from pathlib import Path
import textwrap

import pytest

# function under test
from backend.agent.tools.init.repositories import enable_parchment_for_forge
# storage wrapper used by the function to read/write workspace files
from backend.agent.wrappers.storage import STORAGE as storage


@pytest.fixture()
def parchment_versions_file():
    """
    Create (and restore) backend/config/parchment_versions.json
    so the function reads OUR test mapping table.
    """
    backend_dir = Path(__file__).resolve().parents[1]      # backend/
    config_dir = backend_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / "parchment_versions.json"
    backup = None

    if target.exists():
        backup = target.with_suffix(".json.bak_test")
        if backup.exists():
            backup.unlink()
        target.rename(backup)

    data = {
        "minecraft_to_parchment": {
            # exact present
            "1.21.8": "2025.07.20",
            # lower bounds across several minors
            "1.21.7": "2025.07.18",
            "1.21.6": "2025.06.29",
            "1.21.5": "2025.06.15",
            "1.21.4": "2025.03.23",
            "1.21.3": "2024.12.07",
            "1.21.1": "2024.11.17",
            "1.21":   "2024.11.10",
            "1.20.6": "2024.05.01",
            "1.20.4": "2024.04.14",
            "1.20.3": "2023.12.31",
            "1.20.2": "2023.12.10",
            "1.20.1": "2023.09.03",
            "1.19.4": "2023.06.26",
            "1.19.3": "2023.06.25",
            "1.19.2": "2022.11.27",
            "1.18.2": "2022.11.06",
            "1.17.1": "2021.12.12",
            "1.16.5": "2022.03.06",
        }
    }
    target.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        yield target
    finally:
        # restore original
        if target.exists():
            target.unlink()
        if backup and backup.exists():
            backup.rename(config_dir / "parchment_versions.json")


def _print_for_debug(ws: Path):
    """Return a helpful debug string with file contents."""
    parts = []
    gp = ws / "gradle.properties"
    for f in ("settings.gradle", "settings.gradle.kts", "build.gradle", "build.gradle.kts"):
        p = ws / f
        if p.exists():
            parts.append(f"\n===== {f} =====\n{p.read_text(encoding='utf-8')}")
    if gp.exists():
        parts.append(f"\n===== gradle.properties =====\n{gp.read_text(encoding='utf-8')}")
    return "\n".join(parts)


@pytest.mark.parametrize("dialect", ["groovy", "kts"])
@pytest.mark.parametrize(
    "requested_mc, forge_coord_mc, expected_date",
    [
        # exact entry in mapping table
        ("1.21.8", "1.21.8", "2025.07.20"),
        # fallback: request 1.18.5 (not present) -> use lower bound 1.18.2 date
        ("1.18.5", "1.18.5", "2022.11.06"),
    ],
)
def test_enable_parchment_for_forge_sets_real_mapping_version(
    tmp_path: Path, parchment_versions_file: Path, dialect: str, requested_mc: str, forge_coord_mc: str, expected_date: str
):
    """
    This test builds a minimal workspace and runs ONLY enable_parchment_for_forge.
    It asserts that:
      - pluginManagement has the parchment repo
      - Librarian plugin is present
      - minecraft { mappings ... } uses 'parchment' with YYYY.MM.DD-<MC> (no TBD)
      - gradle.properties has mapping_channel=parchment and mapping_version=YYYY.MM.DD-<MC>
    If anything fails, we print the file contents so you can see the exact failure point.
    """
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)

    # ---- minimal settings file (choose dialect) ----
    if dialect == "groovy":
        (ws / "settings.gradle").write_text(
            textwrap.dedent(
                """
                pluginManagement {
                    repositories {
                        gradlePluginPortal()
                        mavenCentral()
                    }
                }
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
    else:
        (ws / "settings.gradle.kts").write_text(
            textwrap.dedent(
                """
                pluginManagement {
                    repositories {
                        gradlePluginPortal()
                        mavenCentral()
                    }
                }
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

    # ---- minimal build file with forge coordinate to *detect* MC version ----
    if dialect == "groovy":
        (ws / "build.gradle").write_text(
            textwrap.dedent(
                f"""
                plugins {{
                    id 'net.minecraftforge.gradle' version '6.0.+'
                }}

                dependencies {{
                    minecraft 'net.minecraftforge:forge:{forge_coord_mc}-58.1.0'
                }}

                minecraft {{
                    // mappings will be inserted/updated here
                }}
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
    else:
        (ws / "build.gradle.kts").write_text(
            textwrap.dedent(
                f"""
                plugins {{
                    id("net.minecraftforge.gradle") version "6.0.+"
                }}

                dependencies {{
                    "minecraft"("net.minecraftforge:forge:{forge_coord_mc}-58.1.0")
                }}

                minecraft {{
                    // mappings will be inserted/updated here
                }}
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

    # ---- gradle.properties (include a bogus placeholder to ensure it gets replaced) ----
    (ws / "gradle.properties").write_text(
        "mapping_channel=TBD\nmapping_version=TBD-0.0.0\nmappings_channel=TBD\nmappings_version=TBD-0.0.0\n",
        encoding="utf-8",
    )

    # ---- run the function under test ----
    status = enable_parchment_for_forge(ws, requested_mc)

    # ---- diagnostics on failure ----
    debug = _print_for_debug(ws)

    # ---- assertions ----
    # 1) It must never leave TBD in gradle.properties
    gp = (ws / "gradle.properties").read_text(encoding="utf-8")
    assert "mapping_channel=parchment" in gp, f"'mapping_channel=parchment' missing.\nSTATUS: {status}\n{debug}"
    assert f"mapping_version={expected_date}-{forge_coord_mc}" in gp, (
        "Wrong mapping_version OR wrong MC version/date used.\n"
        f"Expected: mapping_version={expected_date}-{forge_coord_mc}\n"
        f"STATUS: {status}\n{debug}"
    )
    # Also write plural variants (many MDKs still read those)
    assert "mappings_channel=parchment" in gp, f"'mappings_channel=parchment' missing.\nSTATUS: {status}\n{debug}"
    assert f"mappings_version={expected_date}-{forge_coord_mc}" in gp, (
        "Wrong mappings_version (plural) OR wrong MC/date.\n"
        f"Expected: mappings_version={expected_date}-{forge_coord_mc}\n"
        f"STATUS: {status}\n{debug}"
    )
    assert "TBD-" not in gp, f"Found TBD in gradle.properties.\nSTATUS: {status}\n{debug}"

    # 2) settings.* must have the parchment repo
    if dialect == "groovy":
        s = (ws / "settings.gradle").read_text(encoding="utf-8")
        assert "parchmentmc.org" in s and "pluginManagement" in s, f"Parchment repo missing in settings.gradle.\nSTATUS: {status}\n{debug}"
    else:
        s = (ws / "settings.gradle.kts").read_text(encoding="utf-8")
        assert "parchmentmc.org" in s and "pluginManagement" in s, f"Parchment repo missing in settings.gradle.kts.\nSTATUS: {status}\n{debug}"

    # 3) build file must have Librarian + mappings
    bpath = ws / ("build.gradle" if dialect == "groovy" else "build.gradle.kts")
    btxt = bpath.read_text(encoding="utf-8")

    assert "org.parchmentmc.librarian.forgegradle" in btxt, (
        "Librarian plugin not applied.\n"
        f"STATUS: {status}\n{debug}"
    )

    if dialect == "groovy":
        assert f"mappings channel: 'parchment', version: '{expected_date}-{forge_coord_mc}'" in btxt, (
            "Groovy mappings not set to parchment or wrong version/date.\n"
            f"Expected: mappings channel: 'parchment', version: '{expected_date}-{forge_coord_mc}'\n"
            f"STATUS: {status}\n{debug}"
        )
    else:
        assert f'mappings("parchment", "{expected_date}-{forge_coord_mc}")' in btxt, (
            "KTS mappings not set to parchment or wrong version/date.\n"
            f'Expected: mappings("parchment", "{expected_date}-{forge_coord_mc}")\n'
            f"STATUS: {status}\n{debug}"
        )
