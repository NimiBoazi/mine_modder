from backend.agent.providers.paths import templates_dir
from backend.agent.wrappers.storage import STORAGE as storage
from pathlib import Path
from typing import Dict

def _render(text: str, ctx: Dict[str, str]) -> str:
    # ultra-simple {{key}} replacer (no logic)
    for k, v in ctx.items():
        text = text.replace(f"{{{{{k}}}}}", str(v))
    return text

def _read_template(framework: str, name: str) -> str:
    p = templates_dir(framework) / name
    return storage.read_text(p)

def _write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    storage.ensure_dir(path.parent)
    storage.write_text(path, content)
    return True

def _insert_between_anchors(path: Path, begin: str, end: str, snippet: str) -> bool:
    """Idempotent insert of snippet inside [begin, end] if not already present."""
    s = storage.read_text(path)
    if snippet.strip() in s:
        return False
    start = s.find(begin)
    stop = s.find(end, start + len(begin))
    if start == -1 or stop == -1:
        raise RuntimeError(f"Anchor block not found in {path}: [{begin}..{end}]")
    new = s[:start+len(begin)] + "\n" + snippet.rstrip() + "\n" + s[stop:]
    storage.write_text(path, new)
    return True

def _json_lang_update(path: Path, key: str, value: str) -> bool:
    import json
    data = {}
    if path.exists():
        data = json.loads(storage.read_text(path) or "{}")
    if data.get(key) == value:
        return False
    data[key] = value
    storage.ensure_dir(path.parent)
    storage.write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
    return True