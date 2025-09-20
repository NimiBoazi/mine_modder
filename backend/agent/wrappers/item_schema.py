from __future__ import annotations

from typing import Dict, Any, TypedDict, List
from pathlib import Path
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
import json, re

from backend.agent.providers.paths import mod_items_dir

# Allowed enums
CREATIVE_TABS = [
    "minecraft:building_blocks",
    "minecraft:colored_blocks",
    "minecraft:natural_blocks",
    "minecraft:functional_blocks",
    "minecraft:redstone_blocks",
    "minecraft:tools_and_utilities",
    "minecraft:combat",
    "minecraft:food_and_drinks",
    "minecraft:ingredients",
    "minecraft:spawn_eggs",
]
MODEL_TYPES = ["basicItem", "handheldItem"]

_TOOL_HELD_HINTS = {"sword", "axe", "pickaxe", "shovel", "hoe", "bow", "crossbow", "wand", "staff", "hammer", "knife", "dagger", "gun"}

def _title_from_id(item_id: str) -> str:
    return re.sub(r"[_\-]+", " ", item_id).strip().title()

def _java_class_name_from_id(item_id: str) -> str:
    # "alexandrite_gem" -> "AlexandriteGem"
    parts = re.split(r"[^A-Za-z0-9]+", item_id)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)

def _registry_const(item_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", item_id).upper().strip("_")

class ItemExtractorInput(TypedDict, total=False):
    task: str          # specific item task (e.g., "Create an alexandrite gem item")
    user_prompt: str   # overall mod description/context
    available_objects: List[str]  # optional: IDs of already-created objects in this mod

_ITEM_ID_RE = re.compile(r"^[a-z0-9_./-]+$")

def _validate_output(data: Dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError("LLM output is not a JSON object.")
    if "item_id" not in data:
        raise ValueError('LLM JSON must include "item_id".')
    item_id = data["item_id"]
    if not isinstance(item_id, str) or not item_id:
        raise ValueError('"item_id" must be a non-empty string.')
    if not _ITEM_ID_RE.match(item_id):
        raise ValueError('"item_id" contains invalid characters; must match ^[a-z0-9_./-]+$')
    # Optional types
    if "recipe_ingredients" in data and not isinstance(data["recipe_ingredients"], list):
        raise ValueError('"recipe_ingredients" must be a list of strings if present.')
    if "tags" in data and not isinstance(data["tags"], list):
        raise ValueError('"tags" must be a list of strings if present.')
    if "tooltip_text" in data and not isinstance(data["tooltip_text"], str):
        raise ValueError('"tooltip_text" must be a string if present.')
    if "description" in data and not isinstance(data["description"], str):
        raise ValueError('"description" must be a string if present.')
    if "object_ids_for_context" in data and not isinstance(data["object_ids_for_context"], list):
        raise ValueError('"object_ids_for_context" must be a list of strings if present.')

def make_item_schema_extractor(model: BaseChatModel) -> Runnable[ItemExtractorInput, Dict[str, Any]]:
    """
    Takes {'task', 'user_prompt'} and returns a dict with the full item schema
    fields (except modid/base_package which are provided elsewhere).
    """
    system = SystemMessage(content=(
        "You are an expert Minecraft modding assistant. Extract a SINGLE item's schema "
        "from a specific item task, using the overall mod prompt for context.\n"
        "Return STRICT JSON (no markdown, no extra text; no code fences).\n\n"
        "Required fields:\n"
        "{\n"
        '  "item_id": "lower_snake_case_id",\n'
        '  "item_class_name": "JavaClassName",\n'
        '  "display_name": "Title Cased Name",\n'
        '  "texture_prompt": "≤12 words, nouns/adjectives only",\n'
        '  "creative_tab_key": one of ["minecraft:building_blocks","minecraft:colored_blocks","minecraft:natural_blocks","minecraft:functional_blocks","minecraft:redstone_blocks","minecraft:tools_and_utilities","minecraft:combat","minecraft:food_and_drinks","minecraft:ingredients","minecraft:spawn_eggs"],\n'
        '  "model_type": one of ["basicItem", "handheldItem"],\n'
        '  "description": "concise, informative, list all custom functionalities"\n'
        "}\n"
        "Optional fields:\n"
        '{  "recipe_ingredients": ["item_id_or_tag", ...], '
        '  "tags": ["VANILLA_ITEM_TAG_CONSTANT", ...], '
        '  "tooltip_text": "short whimsical tip", '
        '  "object_ids_for_context": ["object_id", ...] }\n'
        "Semantics for 'object_ids_for_context': include only if source files are strictly required "
        "(e.g., this item extends/uses that object). Choose only from AVAILABLE_OBJECTS; otherwise omit.\n"
        "\n"
        "Tags (concise rules):\n"
        "Only emit valid Minecraft *VANILLA* item tags. \n"
        "\n"
        "Rules:\n"
        "- Output MUST be a single valid JSON object and nothing else.\n"
        "- 'item_class_name' is the main custom Java class for this item (CamelCase). "
        "  If item_id is 'alexandrite_gem', a good class name is 'AlexandriteGem'.\n"
        "- 'texture_prompt' ≤ 12 words; nouns/adjectives only; describe color/material/pattern; "
        "  avoid 'minecraft', 'pixel art', or 'texture'.\n"
    ))


    def _pick_model_type_from_id(item_id: str, description: str|None) -> str:
        text = f"{item_id} {description or ''}".lower()
        return "handheldItem" if any(w in text for w in _TOOL_HELD_HINTS) else "basicItem"

    def _run(payload: ItemExtractorInput) -> Dict[str, Any]:
        print("[ENTER] wrapper:item_schema_extractor")

        task = payload.get("task", "")
        user_prompt = payload.get("user_prompt", "")
        available_objects = payload.get("available_objects") or []
        if not isinstance(available_objects, list):
            available_objects = []
        available_objects = [str(x) for x in available_objects if isinstance(x, (str, bytes))]

        ao_block = ""
        if available_objects:
            # Present as JSON-like for clarity
            ao_list = ", ".join([f'"{o}"' for o in available_objects])
            ao_block = (
                "AVAILABLE_OBJECTS (already created in this mod; choose only from this list if needed for context):\n"
                f"[{ao_list}]\n\n"
            )

        user_msg = HumanMessage(content=(
            "Overall mod prompt:\n"
            f"{user_prompt}\n\n"
            + ao_block +
            "Item task (extract schema for this specific item ONLY):\n"
            f"{task}\n\n"
            "Respond with the JSON object ONLY."
        ))

        resp = model.invoke([system, user_msg])
        text = resp.content if hasattr(resp, "content") else str(resp)

        # Strict parse only—no heuristic extraction before JSON.
        data = json.loads(text)
        _validate_output(data)

        # Normalize / fill
        item_id = data["item_id"].strip()
        display_name = (data.get("display_name") or _title_from_id(item_id)).strip()

        # item_class_name: use provided or derive CamelCase from item_id
        item_class_name = data.get("item_class_name")
        if not item_class_name or not isinstance(item_class_name, str) or not item_class_name.strip():
            item_class_name = _java_class_name_from_id(item_id)

        description = (data.get("description") or "").strip()
        # if not description:
        #     raise ValueError("Missing required 'description'.")

        texture_prompt = data.get("texture_prompt")
        # if not texture_prompt or not isinstance(texture_prompt, str) or not texture_prompt.strip():
        #     raise ValueError("Missing required 'texture_prompt'.")

        creative_tab_key = data.get("creative_tab_key")
        # if creative_tab_key not in CREATIVE_TABS:
        #     # fallback: choose a reasonable default if the model missed / invalid
        #     creative_tab_key = "minecraft:ingredients"

        model_type = data.get("model_type")
        # if model_type not in MODEL_TYPES:
        #     model_type = _pick_model_type_from_id(item_id, description)

        # Optionals (keep if present)
        recipe_ingredients = data.get("recipe_ingredients")
        tags = data.get("tags")
        tooltip_text = data.get("tooltip_text")
        # Optional dependency context list; keep ONLY those present in available_objects
        needs_ctx = data.get("object_ids_for_context")
        if isinstance(needs_ctx, list):
            needs_ctx = [str(x) for x in needs_ctx if isinstance(x, (str, bytes))]
            allow = set(available_objects)
            needs_ctx = [x for x in needs_ctx if x in allow]
            if len(needs_ctx) == 0:
                needs_ctx = None
        else:
            needs_ctx = None

        full: Dict[str, Any] = {
            "item_id": item_id,
            "display_name": display_name,
            "item_class_name": item_class_name,
            "texture_prompt": texture_prompt,
            "creative_tab_key": creative_tab_key,
            "model_type": model_type,
            "description": description,

            # Optional
            "recipe_ingredients": recipe_ingredients if isinstance(recipe_ingredients, list) else None,
            "tags": tags if isinstance(tags, list) else None,
            "tooltip_text": tooltip_text if isinstance(tooltip_text, str) else None,
            "object_ids_for_context": needs_ctx,

            # Derived, not from LLM
            "registry_constant": _registry_const(item_id),

            # Back-compat nicety: some pipelines expect custom_class_name
            "custom_class_name": item_class_name,
        }
        return full

    return RunnableLambda(lambda x: _run(x))


# ---- Path helpers (kept in wrapper for reuse by nodes/wrappers) ----

def get_custom_item_class_path(ws: Path|str, base_package: str, item_schema: Dict[str, Any]) -> Path:
    """Resolve the Java file path for an item's main custom class.

    Uses the standard location: src/main/java/<base_package>/item/custom/<ItemClassName>.java
    """
    ws_path = Path(ws)
    icn = item_schema.get("item_class_name")
    if not isinstance(icn, str) or not icn.strip():
        raise ValueError("item_schema missing 'item_class_name' for custom class path")
    custom_dir = mod_items_dir(ws_path, base_package) / "custom"
    return custom_dir / f"{icn}.java"



