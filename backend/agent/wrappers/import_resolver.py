from __future__ import annotations

from typing import Dict, Any
import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda

from backend.agent.tools.verify.verify_logger import log_json as _v_log_json
from backend.agent.wrappers.utils import normalize_import_lines


def make_import_resolver(model: BaseChatModel) -> Runnable[Dict[str, Any], Dict[str, Any]]:
    """
    Given a concise Java compile error excerpt and a Java file header (package + existing imports + class decl),
    return ONLY the import lines needed to fix the missing-import error.

    Input payload:
      {
        "workspace_path": "<abs|rel>",           # optional, used for logging only
        "file_path": "src/main/java/.../X.java",
        "file_header": "...",                    # top-of-file content (package, imports, class signature portion)
        "error_excerpt": "...",                  # concise error text from Gradle/javac
        "max_imports": 3                          # optional safety cap
      }

    Output:
      { "imports": [ "import foo.bar.Baz;", ... ] }
    """

    def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
        ws = str(payload.get("workspace_path") or "").strip()
        file_path = str(payload.get("file_path") or "").strip()
        header = str(payload.get("file_header") or "").strip()
        error_excerpt = str(payload.get("error_excerpt") or "").strip()
        max_imports = int(payload.get("max_imports") or 2)

        system = SystemMessage(content=(
            "You are a Java build assistant. Your task is to output ONLY the minimal Java import lines "
            "required to fix the missing import error. Return strict JSON with an 'imports' array. "
            "Rules: imports must be full Java import statements ending in ';'. No comments, no extra text."
        ))
        user = HumanMessage(content=(
            f"FILE: {file_path}\n\n"
            "Top-of-file header (package + current imports + first lines):\n" + header + "\n\n"
            "Compile error excerpt (concise):\n" + error_excerpt + "\n\n"
            f"Return JSON exactly like: {{\"imports\": [\"import x.y.Z;\"]}} with at most {max_imports} entries."
        ))

        try:
            if ws:
                _v_log_json(ws, "import_resolver.prompt", {
                    "system": system.content,
                    "user": user.content,
                })
        except Exception:
            pass

        resp = model.invoke([system, user])
        raw = str(getattr(resp, "content", resp))
        try:
            data = json.loads(raw.strip().strip("`"))
        except Exception:
            data = {"imports": []}
        try:
            if ws:
                _v_log_json(ws, "import_resolver.response_raw", {"raw": raw})
                _v_log_json(ws, "import_resolver.response_parsed", data)
        except Exception:
            pass
        # Normalize: coerce to valid import statements and dedupe
        raw_imports = [s.strip() for s in (data.get("imports") or []) if isinstance(s, str)]
        imps = normalize_import_lines(raw_imports)
        return {"imports": imps[:max_imports]}

    return RunnableLambda(lambda x: _run(x))

