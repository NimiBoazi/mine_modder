from __future__ import annotations

from typing import Optional
from langchain_core.runnables import Runnable

from backend.agent.providers.gpt5_provider import build_gpt5_chat_model
from backend.agent.wrappers.create_custom_item_class import make_create_custom_item_class
from backend.schemas.itemSchema import ItemSchema


def build_create_custom_item_class() -> Optional[Runnable]:
    """Return a Runnable that generates a full custom item class (Java) using GPT-5.

    The runnable expects an input payload with at least:
      {
        "item_schema": Dict[str, Any],              # the full item schema
        "mod_context": {"base_package": str, "modid": str},
        "workspace": str (optional),               # absolute path to repo root for file lookups
        "items_index": Dict[str, Dict] (optional), # item_id -> schema for dependency source lookup
      }
    and returns a string containing the full Java file after post-processing.
    """
    model = build_gpt5_chat_model()
    if model is None:
        return None
    # Increase timeout specifically for custom item class generation (slowest step)
    try:
        import os
        timeout_s = int(os.getenv("CUSTOM_ITEM_CLASS_TIMEOUT", os.getenv("OPENAI_REQUEST_TIMEOUT", "180")))
        model = model.bind(timeout=timeout_s)
    except Exception:
        pass
    # Optional: request higher reasoning effort if explicitly enabled (requires supported model/endpoint)
    try:
        import os
        _reasoning_flag = os.getenv("CUSTOM_ITEM_CLASS_REASONING", "").strip().lower()
        if _reasoning_flag in ("1", "true", "yes", "on", "high"):
            model = model.bind(
                extra_headers={"OpenAI-Beta": "reasoning=v1"},
                extra_body={"reasoning": {"effort": "high"}},
            )
    except Exception:
        pass
    return make_create_custom_item_class(model)

