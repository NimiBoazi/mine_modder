from __future__ import annotations

import os
import sys
import json
import traceback
from typing import Any, Dict, Optional, Tuple
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None  # type: ignore

# Ensure repository root is on sys.path for `import backend.*` to work
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

STEP_OK = "OK"
STEP_FAIL = "FAIL"

# Load GOOGLE_API_KEY from backend/.env if available
if load_dotenv is not None:
    BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"  # backend/.env
    try:
        load_dotenv(BACKEND_ENV, override=False)
    except Exception:
        pass

DEFAULT_MODEL = os.getenv("MM_GEMINI_MODEL", "gemini-2.0-flash")


def _print_step(name: str, ok: bool, info: str = "") -> None:
    status = STEP_OK if ok else STEP_FAIL
    print(f"- {status} {name}: {info}")


def check_imports() -> Tuple[bool, Optional[str]]:
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: F401
        return True, None
    except Exception as e:
        return False, f"Import error: {e}\n{traceback.format_exc()}"


def check_env() -> Tuple[bool, Optional[str]]:
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        return False, "GOOGLE_API_KEY is not set in environment"
    if len(key) < 20:
        return False, "GOOGLE_API_KEY seems too short — is it correct?"
    return True, None


def check_model_init(model_name: str = DEFAULT_MODEL) -> Tuple[bool, Optional[str], Optional[Any]]:
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        model = ChatGoogleGenerativeAI(model=model_name, temperature=0.2)
        return True, None, model
    except Exception as e:
        return False, f"Model init failed for {model_name}: {e}\n{traceback.format_exc()}", None


def check_raw_invoke(model: Any) -> Tuple[bool, Optional[str], Optional[str]]:
    try:
        resp = model.invoke("Reply with the single word: pong")
        content = getattr(resp, "content", None) or str(resp)
        ok = isinstance(content, str) and ("pong" in content.lower())
        if not ok:
            return False, f"Unexpected response content: {content!r}", content
        return True, None, content
    except Exception as e:
        return False, f"Raw invoke failed: {e}\n{traceback.format_exc()}", None


def check_wrapper_invoke(model: Any) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    try:
        from backend.agent.wrappers.llm import make_name_desc_extractor
        extractor = make_name_desc_extractor(model)
        out = extractor.invoke("A Minecraft mod that adds a sapphire block and green rain weather.")
        if not isinstance(out, dict) or not {"name", "description"}.issubset(out):
            return False, f"Wrapper returned unexpected payload: {out!r}", out
        # Ensure description length policy
        desc = (out.get("description") or "").strip()
        if len(desc) > 200:
            return False, f"Wrapper description too long ({len(desc)} chars)", out
        return True, None, out
    except Exception as e:
        return False, f"Wrapper invoke failed: {e}\n{traceback.format_exc()}", None


def check_provider_build_and_invoke() -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    try:
        from backend.agent.providers.llm import build_name_desc_extractor
        extractor = build_name_desc_extractor()
        if extractor is None:
            return False, "Provider returned None (missing GOOGLE_API_KEY or provider import failure)", None
        out = extractor.invoke("A Minecraft mod that adds a sapphire block and green rain weather.")
        if not isinstance(out, dict) or not {"name", "description"}.issubset(out):
            return False, f"Provider extractor returned unexpected payload: {out!r}", out
        return True, None, out
    except Exception as e:
        return False, f"Provider build/invoke failed: {e}\n{traceback.format_exc()}", None


def main() -> int:
    print("== Google API (Gemini) connectivity diagnostics ==")
    print(f"Model: {DEFAULT_MODEL}")

    ok, info = check_imports()
    _print_step("import langchain_google_genai", ok, info or "")
    if not ok:
        return 1

    ok, info = check_env()
    _print_step("GOOGLE_API_KEY present", ok, info or "")
    if not ok:
        return 2

    ok, info, model = check_model_init(DEFAULT_MODEL)
    _print_step("model init", ok, info or "")
    if not ok:
        return 3

    ok, info, content = check_raw_invoke(model)
    _print_step("raw invoke", ok, info or (content or ""))
    if not ok:
        return 4

    ok, info, out = check_wrapper_invoke(model)
    _print_step("wrapper invoke (make_name_desc_extractor)", ok, info or json.dumps(out, ensure_ascii=False))
    if not ok:
        return 5

    ok, info, out = check_provider_build_and_invoke()
    _print_step("provider build_name_desc_extractor + invoke", ok, info or json.dumps(out, ensure_ascii=False))
    if not ok:
        return 6

    print("\nAll connectivity checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

