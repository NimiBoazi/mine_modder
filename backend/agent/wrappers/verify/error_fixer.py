from __future__ import annotations

"""
GPT-5 error fixer: propose minimal code edits to fix the build/runtime error.

Input fields (dict):
- command: "./gradlew <task>"
- error_type: "compile" | "datagen" | "runtime" | "unknown"
- mc_version, neoforge_version, java_version
- errors / stack_head / caused_by / resource_lines (from triage)
- code_snippets: [{path,start_line,end_line,code}]

Output JSON (strict):
{
  "explanation": "1-2 sentence cause and fix idea",
  "edits": [
    {
      "path": "<workspace-relative path>",
      "action": "replace_line",
      "old_line": "<exact line text to replace>",
      "new_line": "<exact replacement line>",
      "occurrence": 1
    },
    {
      "path": "<workspace-relative path>",
      "action": "replace_range",
      "start_line": <int>,
      "end_line": <int>,
      "new_code": "..."
    },
    {
      "path": "<workspace-relative path>",
      "action": "insert",
      "at_line": <int>,
      "new_code": "..."
    }
  ]
}

Rules:
- Allowed actions: "replace_line" (preferred for single-line fixes), "replace_range", and "insert".
- For replace_line: old_line must match the current line EXACTLY (including whitespace). Prefer this when a single line change fixes the error.
- Do NOT create, delete, or move files. Modify only existing files.
- Keep edits minimal; prefer localized changes over large rewrites.
- Ensure Java version (21) and MC 1.21/NeoForge APIs are correct.
- All paths must be workspace-relative.
"""

from typing import Any
from pathlib import Path
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import RunnableLambda
from backend.agent.tools.verify.verify_logger import log_text as _v_log_text


def make_error_fixer(model) -> Any:
    print("[ENTER] wrapper:error_fixer.make_error_fixer")
    system = (
        "You are GPT-5, a precise Minecraft 1.21 (NeoForge) mod engineer. Given an error, "
        "propose the smallest-possible code edits to fix it. Output ONLY the required JSON, "
        "no commentary. Fixes must be line-by-line replacements ONLY (no ranges, no inserts). "
        "Do not create/delete/move files."
    )
    human = (
        "Command: {command}\n"
        "Error type: {error_type}\n"
        "Versions: MC={mc_version} NeoForge={neoforge_version} Java={java_version}\n"
        "Errors: {errors}\n"
        "Stack head: {stack_head}\n"
        "Caused by: {caused_by}\n"
        "Missing resource lines: {resource_lines}\n"
        "Code snippets:\n{code_snippets}\n\n"
        "IMPORTANT:\n"
        "- Fixes must be LINE-BY-LINE replacements ONLY. Do NOT use ranges or inserts.\n"
        "- For EACH changed line, return ONE object with keys: path, 'old line', 'new line', and optional occurrence (1-based).\n"
        "- 'old line' must be the exact CURRENT line text in the file (full line). 'new line' must be the FULL replacement line.\n"
        "- Do NOT create, delete, or move files. Modify only existing files.\n"
        "- In Java files with anchors (// ==MM:NAME_BEGIN== ... // ==MM:NAME_END==), edits outside anchors will be rejected.\n"
        "- Paths must be workspace-relative.\n\n"
        "Return ONLY JSON with keys 'explanation' and 'edits' as specified; no extra text."
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        ("human", human),
    ])

    parser = JsonOutputParser()

    def _run(payload: dict) -> dict:
        # Format messages
        msgs = prompt.format_messages(**payload)
        prev_id = str(payload.get("previous_response_id") or "").strip()
        call_model = model
        # Bind previous_response_id to leverage GPT-5 reasoning item threading
        if prev_id:
            try:
                call_model = model.bind(previous_response_id=prev_id)
            except Exception:
                pass
        # Optionally set reasoning effort if supported
        try:
            call_model = call_model.bind(reasoning={"effort": "medium"})
        except Exception:
            pass

        # Ask model for JSON; attempt to bias to JSON mode when supported
        try:
            call_model = call_model.bind(response_format={"type": "json_object"})
        except Exception:
            pass
        resp = call_model.invoke(msgs)
        content = getattr(resp, "content", str(resp))
        try:
            _v_log_text(Path(payload.get("workspace_path") or "."), f"LLM_FIX_RAW len={len(str(content) or '')}")
        except Exception:
            pass
        # Extract response id (best-effort)
        rid = None
        try:
            rid = getattr(resp, "id", None)
            if not rid:
                meta = getattr(resp, "response_metadata", {}) or {}
                rid = meta.get("response_id") or meta.get("id")
        except Exception:
            rid = None
        out = {}
        try:
            out = parser.parse(content)
        except Exception as e:
            try:
                _v_log_text(Path(payload.get("workspace_path") or "."), f"LLM_FIX_PARSE_ERROR: {e}")
            except Exception:
                pass
            out = {"explanation": "", "edits": []}
        out["_reasoning_response_id"] = rid
        return out

    return RunnableLambda(lambda x: _run(x))


__all__ = ["make_error_fixer"]

