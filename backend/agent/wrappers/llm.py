from __future__ import annotations

from typing import Dict, Any
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda


def make_name_desc_extractor(model: BaseChatModel) -> Runnable:
    system = SystemMessage(content=(
        "You are extracting metadata for a Minecraft mod.\n"
        "Return STRICT JSON with keys name and description only.\n"
        "- name: a concise, human-friendly mod name.\n"
        "- description: <= 160 characters, one sentence.\n"
        "Do not include code fences or extra text."
    ))
    # We will keep it simple and rely on model.invoke for now.
    def _run(user_prompt: str) -> Dict[str, Any]:
        msg = HumanMessage(content=(
            "User request describing a mod:\n\n" + user_prompt + "\n\n"
            "Respond with JSON: {\"name\": string, \"description\": string}"
        ))
        resp = model.invoke([system, msg])
        text = resp.content if hasattr(resp, "content") else str(resp)
        # naive JSON extraction; models should comply; fallback parse heuristics
        import json, re
        try:
            return json.loads(text)
        except Exception:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
            return {"name": "My Mod", "description": "A Minecraft mod."}
    return RunnableLambda(lambda x: _run(x))

