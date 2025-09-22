from __future__ import annotations

from typing import Optional
from langchain_core.runnables import Runnable

from backend.agent.providers.gpt5_provider import build_gpt5_chat_model

try:
    from backend.agent.wrappers.verify.error_analyzer import make_error_analyzer
except Exception:  # pragma: no cover
    make_error_analyzer = None  # type: ignore


def build_error_analyzer() -> Optional[Runnable]:
    print("[ENTER] provider:verify_error_analyzer.build_error_analyzer")
    try:
        if make_error_analyzer is None:
            print("[PROVIDER] analyzer wrapper unavailable")
            return None
        model = build_gpt5_chat_model()
        if model is None:
            print("[PROVIDER] GPT-5 model unavailable")
            return None
        runnable = make_error_analyzer(model)
        print("[PROVIDER] analyzer runnable built")
        return runnable
    except Exception as e:
        print(f"[PROVIDER] analyzer build failed: {e}")
        return None


__all__ = ["build_error_analyzer"]

