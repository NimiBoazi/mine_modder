"""
Java toolchain utilities

Purpose
-------
Pick the correct Java version for a given Minecraft version (from
`backend/config/project_matrix.yaml`) and ensure the Gradle build uses it.
Also sets the Gradle `group` if missing.

Dev vs Prod
-----------
This module reads a local YAML config in dev. In production you can plug in a
config service/DB without changing callers — keep the public API stable.

Public API
----------
- java_for(mc_version: str) -> int
- patch_toolchain(workspace: Path | str, java_version: int, group: str | None = None) -> dict

Behavior
--------
- `java_for` evaluates rules in the order they appear in the YAML under
  `java_toolchain:` (e.g., ">=1.20.5": 21, "<=1.20.4": 17) and returns the
  first matching version. If the file is missing, falls back to 21 for >=1.20.5
  else 17.
- `patch_toolchain` updates or injects a Gradle `java { toolchain { ... } }` block
  in either `build.gradle` (Groovy DSL) or `build.gradle.kts` (Kotlin DSL).
  If `group` is provided and no group is present, it injects one.
"""
from __future__ import annotations

from pathlib import Path
import os
import re
from dataclasses import dataclass
from typing import Iterable, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # graceful fallback; we'll use defaults


# -------------------------
# Config loading
# -------------------------

_DEF_RULES: list[tuple[str, int]] = [(">=1.20.5", 21), ("<=1.20.4", 17)]


def _config_dir() -> Path:
    env = os.environ.get("MINEMODDER_CONFIG_DIR")
    if env:
        return Path(env)
    # backend/agent/tools/java_toolchain.py → ../../../config
    return Path(__file__).resolve().parents[3] / "config"


def _load_rules_from_yaml() -> list[tuple[str, int]]:
    cfg_path = _config_dir() / "project_matrix.yaml"
    if not cfg_path.exists() or yaml is None:
        return _DEF_RULES
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    jt = data.get("java_toolchain", {})
    # Preserve file order (PyYAML keeps it in modern Python)
    rules: list[tuple[str, int]] = []
    for k, v in jt.items():
        try:
            rules.append((str(k), int(v)))
        except Exception:
            continue
    return rules or _DEF_RULES


# -------------------------
# Version comparison
# -------------------------

def _parse_ver(v: str) -> tuple[int, int, int]:
    parts = [p for p in re.split(r"[^0-9]", v) if p != ""]
    nums = [int(p) for p in parts[:3]]
    while len(nums) < 3:
        nums.append(0)
    return nums[0], nums[1], nums[2]


def _cmp(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return (a > b) - (a < b)


def _match_rule(version: str, rule: str) -> bool:
    m = re.match(r"^(>=|<=|==|=|>|<)?\s*(.+)$", rule.strip())
    if not m:
        return False
    op = m.group(1) or "=="
    bound = m.group(2)
    va = _parse_ver(version)
    vb = _parse_ver(bound)
    c = _cmp(va, vb)
    if op in ("==", "="):
        return c == 0
    if op == ">=":
        return c >= 0
    if op == ">":
        return c > 0
    if op == "<=":
        return c <= 0
    if op == "<":
        return c < 0
    return False


# -------------------------
# Public API
# -------------------------

def java_for(mc_version: str) -> int:
    """Return Java version (e.g., 17 or 21) for a given MC version.
    Evaluates rules in YAML order; falls back to _DEF_RULES.
    """
    rules = _load_rules_from_yaml()
    for expr, jv in rules:
        if _match_rule(mc_version, expr):
            return int(jv)
    # Fallback: conservative default
    return 21 if _match_rule(mc_version, ">=1.20.5") else 17


@dataclass
class PatchResult:
    file: Path
    inserted: bool
    replaced: bool
    ensured_group: bool


_GROOVY_BLOCK = (
    "java {\n"
    "    toolchain {\n"
    "        languageVersion = JavaLanguageVersion.of(%d)\n"
    "    }\n"
    "}\n"
)

_KOTLIN_BLOCK = (
    "java {\n"
    "    toolchain {\n"
    "        languageVersion.set(JavaLanguageVersion.of(%d))\n"
    "    }\n"
    "}\n"
)


def patch_toolchain(workspace: Path | str, java_version: int, group: Optional[str] = None) -> dict:
    """Ensure Gradle uses the given Java toolchain (and group if provided)."""
    from backend.agent.wrappers.storage import STORAGE as storage
    ws = Path(workspace)
    results: list[PatchResult] = []

    for fname, kotlin in (("build.gradle", False), ("build.gradle.kts", True)):
        p = ws / fname
        if not storage.exists(p):
            continue
        txt = storage.read_text(p, encoding="utf-8", errors="ignore")
        original = txt

        # Replace existing languageVersion setting if present
        if not kotlin:
            # Groovy DSL
            txt, n1 = re.subn(r"languageVersion\s*=\s*JavaLanguageVersion\.of\(\d+\)",
                               f"languageVersion = JavaLanguageVersion.of({java_version})", txt)
        else:
            # Kotlin DSL
            txt, n1 = re.subn(r"languageVersion\.set\(JavaLanguageVersion\.of\(\d+\)\)",
                               f"languageVersion.set(JavaLanguageVersion.of({java_version}))", txt)
            if n1 == 0:
                # also try assignment form if present in some samples
                txt, n1b = re.subn(r"languageVersion\s*=\s*JavaLanguageVersion\.of\(\d+\)",
                                   f"languageVersion = JavaLanguageVersion.of({java_version})", txt)
                n1 += n1b

        replaced = n1 > 0
        inserted = False

        if not replaced:
            # Try to insert into an existing toolchain block
            if not kotlin:
                # Insert/replace inside java { toolchain { ... } }
                if re.search(r"java\s*\{[\s\S]*?toolchain\s*\{[\s\S]*?\}\s*\}", txt):
                    # Replace or add the languageVersion line inside toolchain
                    def _inject_lang(match: re.Match[str]) -> str:
                        block = match.group(0)
                        if re.search(r"languageVersion\s*=\s*JavaLanguageVersion\.of\(\d+\)", block):
                            block = re.sub(r"languageVersion\s*=\s*JavaLanguageVersion\.of\(\d+\)",
                                           f"languageVersion = JavaLanguageVersion.of({java_version})", block)
                        else:
                            block = re.sub(r"toolchain\s*\{", f"toolchain {{\n        languageVersion = JavaLanguageVersion.of({java_version})", block, count=1)
                        return block
                    txt = re.sub(r"java\s*\{[\s\S]*?toolchain\s*\{[\s\S]*?\}\s*\}", _inject_lang, txt, count=1)
                    inserted = True
                else:
                    # Append a full block
                    txt = txt.rstrip() + "\n\n" + (_GROOVY_BLOCK % java_version)
                    inserted = True
            else:
                # Kotlin DSL
                if re.search(r"java\s*\{[\s\S]*?toolchain\s*\{[\s\S]*?\}\s*\}", txt):
                    def _inject_lang_k(match: re.Match[str]) -> str:
                        block = match.group(0)
                        if re.search(r"languageVersion\.set\(JavaLanguageVersion\.of\(\d+\)\)", block):
                            block = re.sub(r"languageVersion\.set\(JavaLanguageVersion\.of\(\d+\)\)",
                                           f"languageVersion.set(JavaLanguageVersion.of({java_version}))", block)
                        else:
                            block = re.sub(r"toolchain\s*\{", f"toolchain {{\n        languageVersion.set(JavaLanguageVersion.of({java_version}))", block, count=1)
                        return block
                    txt = re.sub(r"java\s*\{[\s\S]*?toolchain\s*\{[\s\S]*?\}\s*\}", _inject_lang_k, txt, count=1)
                    inserted = True
                else:
                    txt = txt.rstrip() + "\n\n" + (_KOTLIN_BLOCK % java_version)
                    inserted = True

        ensured_group = False
        if group:
            if not re.search(r"(?m)^\s*group\s*(=|\s)\s*['\"]", txt):
                # Inject a simple group assignment at EOF (works for both DSLs)
                txt = txt.rstrip() + f"\n\n// mine_modder: injected group\ngroup = \"{group}\"\n"
                ensured_group = True

        if txt != original:
            storage.write_text(p, txt, encoding="utf-8")

        results.append(PatchResult(file=p, inserted=inserted, replaced=replaced, ensured_group=ensured_group))

    return {
        "results": [
            {
                "file": str(r.file),
                "inserted": r.inserted,
                "replaced": r.replaced,
                "ensured_group": r.ensured_group,
            }
            for r in results
        ]
    }


__all__ = ["java_for", "patch_toolchain"]


