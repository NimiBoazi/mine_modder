from __future__ import annotations

from typing import Dict, Any, TypedDict
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
import json, re


def _title_from_id(item_id: str) -> str:
    return re.sub(r"[_\-]+", " ", item_id).strip().title()


def _registry_const(item_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", item_id).upper().strip("_")


class ItemExtractorInput(TypedDict):
    task: str          # specific item task (e.g., "Create an alexandrite gem item")
    user_prompt: str   # overall mod description/context


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
        raise ValueError(
            '"item_id" contains invalid characters; must match ^[a-z0-9_./-]+$'
        )
    # Note: other keys are allowed/passed through, but not required today.


def make_item_schema_extractor(model: BaseChatModel) -> Runnable[ItemExtractorInput, Dict[str, Any]]:
    """
    Returns a Runnable that takes {'task', 'user_prompt'} and returns a dict
    with at least {'item_id': str}. No fallbacks—invalid output raises ValueError.

    Prompt already requests a richer schema so you can later consume more fields
    by only changing the prompt, not this code.
    """
    system = SystemMessage(content=(
    "You are an expert Minecraft modding assistant. Derive a SINGLE item's schema "
    "from a specific item task, using the overall mod prompt for context.\n"
    "Return STRICT JSON (no markdown, no extra text). Do not include code fences.\n\n"
    "Schema to return (keys shown; add only if relevant; fields marked REQUIRED must appear):\n"
    "{\n"
    '  "item_id": "lower_snake_case_id",  // REQUIRED; ^[a-z0-9_./-]+$\n'
    '  "display_name": "Title Cased Name",\n'
    '  "add_to_creative": true,\n'
    '  "creative_tab_key": "CreativeModeTabs.INGREDIENTS",\n'
    '  "model_parent": "minecraft:item/generated",\n'
    '  "texture_prompt": "concise description for 16x16 pixel-art item texture"  // REQUIRED\n'
    "}\n"
    "Rules:\n"
    "- The response MUST be a single valid JSON object. No prose, no explanation.\n"
    "- item_id MUST reflect the item mentioned in the task within the mod context.\n"
    "- texture_prompt MUST be concise (<= 12 words), nouns/adjectives only, describe color/material/pattern;\n"
    "  no camera/lighting/style terms; avoid the words 'minecraft', 'pixel art', or 'texture'.\n"
    "- If you cannot determine a valid item_id, return an empty JSON object {}."
))

    def _run(payload: ItemExtractorInput) -> Dict[str, Any]:
        task = payload.get("task", "")
        user_prompt = payload.get("user_prompt", "")

        user_msg = HumanMessage(content=(
            "Overall mod prompt:\n"
            f"{user_prompt}\n\n"
            "Item task (extract schema for this specific item ONLY):\n"
            f"{task}\n\n"
            "Respond with the JSON object ONLY."
        ))

        resp = model.invoke([system, user_msg])
        text = resp.content if hasattr(resp, "content") else str(resp)

        # Strict parse only—no heuristic extraction.
        data = json.loads(text)

        # Strict validation—no defaults or auto-fixes.
        _validate_output(data)

        # Build full schema: only item_id/display_name from LLM, everything else deterministic
        item_id = data["item_id"].strip()
        display_name = data.get("display_name") or _title_from_id(item_id)
        texture_prompt = data.get("texture_prompt")

        full: Dict[str, Any] = {
            "item_id": item_id,
            "display_name": display_name,
            "texture_prompt": texture_prompt,
            # Deterministic defaults (ignore any LLM-provided values for these)
            "add_to_creative": True,
            "creative_tab_key": "CreativeModeTabs.INGREDIENTS",
            "model_parent": "minecraft:item/generated",
            # Derived, not from LLM
            "registry_constant": _registry_const(item_id),
        }
        return full

    return RunnableLambda(lambda x: _run(x))