from __future__ import annotations

from typing import Dict
from pathlib import Path

from backend.agent.wrappers.storage import STORAGE as storage


def render_placeholders(text: str, ctx: Dict[str, object]) -> str:
    """Simple template replacement for "{{key}}" placeholders.
    - Replaces each {{key}} with str(value) from ctx.
    - Does not perform any escaping or logic.
    """
    for k, v in ctx.items():
        text = text.replace(f"{{{{{k}}}}}", str(v))
    return text


def insert_before_anchor(full_text: str, anchor: str, block: str) -> str:
    """Insert block just above the first occurrence of anchor, preserving indentation.

    If the anchor is not found, the block is appended at the end with an extra newline.
    """
    idx = full_text.find(anchor)
    if idx == -1:
        # Anchor missing; append at end with a guard newline
        return (full_text.rstrip() + "\n\n" + block.rstrip() + "\n")

    # Compute indentation of the anchor line
    line_start = full_text.rfind("\n", 0, idx) + 1
    anchor_line = full_text[line_start: full_text.find("\n", idx)]
    indent = anchor_line[: len(anchor_line) - len(anchor_line.lstrip())]
    indented_block = "\n".join(indent + ln if ln else ln for ln in block.rstrip().splitlines()) + "\n"
    return full_text[:line_start] + indented_block + full_text[line_start:]


def insert_between_anchors_text(full_text: str, begin: str, end: str, snippet: str) -> str:
    """Insert snippet just above the END anchor line within the BEGIN..END block.

    - Matches indentation of the BEGIN anchor line for inserted content.
    - Normalizes END anchor indentation to match BEGIN anchor indentation.
    - Idempotent: if the fully-indented snippet already exists anywhere in the file, returns original.
    - Preserves existing content between anchors; appends just above END.
    - Ensures exactly one empty line above the END anchor after insertion.
    """
    s = full_text
    start = s.find(begin)
    stop = s.find(end, start + len(begin) if start != -1 else 0)
    if start == -1 or stop == -1:
        raise ValueError(f"Anchor block not found: [{begin}..{end}]")

    import re as _re

    # BEGIN anchor line and indent
    begin_line_start = s.rfind("\n", 0, start)
    if begin_line_start == -1:
        begin_line_start = 0
    else:
        begin_line_start += 1
    begin_line_end = s.find("\n", start)
    if begin_line_end == -1:
        begin_line_end = len(s)
    begin_line = s[begin_line_start:begin_line_end]
    begin_indent = _re.match(r"[\t ]*", begin_line).group(0)

    # END anchor line and indent
    end_line_start = s.rfind("\n", 0, stop)
    if end_line_start == -1:
        end_line_start = 0
    else:
        end_line_start += 1
    end_line_end = s.find("\n", stop)
    if end_line_end == -1:
        end_line_end = len(s)
    end_line = s[end_line_start:end_line_end]

    # Prepare indented snippet (multi-line safe) using BEGIN indent
    rendered = snippet.rstrip("\n")
    indented = "\n".join((begin_indent + ln if ln else ln) for ln in rendered.splitlines())

    # Prepare normalization of END anchor indentation to match BEGIN indent
    end_line_core = end_line.lstrip(" \t")
    normalized_end_line = begin_indent + end_line_core
    needs_end_norm = (end_line != normalized_end_line)

    # If the snippet already exists, avoid duplicating it but still normalize END indentation
    if indented and indented in s:
        if not needs_end_norm:
            return s
        # Replace END line indentation only
        before_end_line = s[:end_line_start]
        after_end_line = s[end_line_end:]
        # Ensure exactly one blank line before END anchor (preserve content above)
        before_end_line = before_end_line.rstrip(" \t\n") + "\n\n"
        return before_end_line + normalized_end_line + after_end_line

    # Compose new content with inserted snippet and normalized END line
    before_end_line = s[:end_line_start]
    after_end_line = s[end_line_end:]

    # Ensure exactly one blank line before END anchor
    before_end_line = before_end_line.rstrip(" \t\n") + "\n\n"

    new = before_end_line + indented + "\n" + normalized_end_line + after_end_line
    return new



def load_optional(path: Path) -> str:
    """Read text from path if it exists; return empty string on any error.

    Uses the STORAGE abstraction and is safe to call in idempotent wrapper steps.
    """
    try:
        return storage.read_text(path) if storage.exists(path) else ""
    except Exception:
        return ""


__all__ = [
    "render_placeholders",
    "insert_before_anchor",
    "insert_between_anchors_text",
    "load_optional",
]

