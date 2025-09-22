from __future__ import annotations

from typing import Optional
from langchain_core.runnables import Runnable

from backend.agent.providers.gpt5_provider import build_gpt5_chat_model

try:
    from backend.agent.wrappers.verify.error_fixer import make_error_fixer
except Exception:  # pragma: no cover
    make_error_fixer = None  # type: ignore


def build_error_fixer() -> Optional[Runnable]:
    print("[ENTER] provider:verify_error_fixer.build_error_fixer")
    try:
        if make_error_fixer is None:
            print("[PROVIDER] fixer wrapper unavailable")
            return None
        model = build_gpt5_chat_model()
        if model is None:
            print("[PROVIDER] GPT-5 model unavailable")
            return None
        runnable = make_error_fixer(model)
        print("[PROVIDER] fixer runnable built")
        return runnable
    except Exception as e:
        print(f"[PROVIDER] fixer build failed: {e}")
        return None


__all__ = ["build_error_fixer"]

