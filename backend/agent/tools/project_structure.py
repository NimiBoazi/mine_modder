from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from backend.agent.wrappers.storage import STORAGE as storage


DEFAULT_STRUCTURE_PATH = Path("backend/config/project_structure.json")

# Anchors present in custom item class templates
_CUSTOM_ITEM_ANCHORS: Dict[str, str] = {
    "EXTRA_IMPORTS_BEGIN": "Optional extra imports for this custom class (e.g., MobEffects, utilities).",
    # The template contains clearly marked insert anchors for these regions
    "STATIC_FIELDS": "Insert static fields used by this item class (constants, cached effects, etc.).",
    "CONSTRUCTOR_BODY": "Insert constructor logic to initialize item-specific state or properties.",
    "METHODS": "Insert or override methods to implement custom behavior (e.g., use, onUseOn, appendHoverText).",
}

_CUSTOM_ITEM_NOTES = (
    "Custom item class implementing this item's behavior. The ModItems registry constructs instances of these "
    "classes with new Item.Properties(). Use these anchors to add fields, constructor logic, and methods. Keep "
    "imports in the EXTRA_IMPORTS block. Game-data (recipes, models, tags, food) lives in datagen/providers/JSONs."
)


def _load_base_structure(structure_path: Path = DEFAULT_STRUCTURE_PATH) -> Dict[str, Any]:
    if not storage.exists(structure_path):
        raise FileNotFoundError(f"project_structure.json not found at {structure_path}")
    try:
        text = storage.read_text(structure_path, encoding="utf-8")
        return json.loads(text)
    except Exception as e:
        raise RuntimeError(f"Failed to parse project_structure.json: {e}")


def augment_with_custom_items(
    *,
    items_index: Dict[str, Dict[str, Any]],
    structure_path: Path = DEFAULT_STRUCTURE_PATH,
) -> Dict[str, Any]:
    """
    Load the base project_structure.json (without modifying it) and return a new
    dict augmented with entries for each custom item in items_index.

    - items_index: mapping of item_id -> item_schema payload (from agent state)
      Expected fields per item: item_id, item_class_name, description
    - structure_path: optional override for the base manifest location

    Returns a new dict ready to send to the LLM.
    """
    base = _load_base_structure(structure_path)
    out = dict(base)  # shallow copy is fine; we'll only add new top-level keys

    if not isinstance(items_index, dict) or not items_index:
        return out

    for item_id, schema in items_index.items():
        try:
            s = schema or {}
            desc = str(s.get("description") or "Custom item class for this mod.").strip()
            item_class_name = str(s.get("item_class_name") or s.get("custom_class_name") or "").strip()
            # Key format: custom_item_class:<item_id>  (stable, discoverable)
            key = f"custom_item_class:{item_id}"

            # Compose a per-item description: prefer schema description, fallback
            description = desc if desc else f"Custom item class: {item_class_name or item_id}."

            out[key] = {
                "description": description,
                "anchors": dict(_CUSTOM_ITEM_ANCHORS),
                "notes": _CUSTOM_ITEM_NOTES,
            }
        except Exception:
            # Keep robust: skip any malformed entries
            continue

    return out


def load_and_augment_project_structure(
    *,
    workspace_path: Optional[str | Path] = None,  # not used currently, reserved for future path hints
    items_index: Dict[str, Dict[str, Any]],
    structure_path: Path = DEFAULT_STRUCTURE_PATH,
) -> Dict[str, Any]:
    """
    Convenience wrapper with an API suited for nodes: give it the items_index
    from state and it returns the augmented manifest dict.

    This does not write any files; it only reads the base JSON and returns a new dict.
    """
    # workspace_path is currently unused (anchors/notes are generic), kept for future needs
    return augment_with_custom_items(items_index=items_index, structure_path=structure_path)

