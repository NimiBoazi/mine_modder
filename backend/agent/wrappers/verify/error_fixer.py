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
- ONLY two actions are allowed: "replace_range" and "insert". Do not use any other action.
- Do NOT create, delete, or move files. Modify only existing files via replace/insert.
- Keep edits minimal; prefer localized changes over large rewrites.
- Ensure Java version (21) and MC 1.21/NeoForge APIs are correct.
- All paths must be workspace-relative.
"""

from typing import Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser


def make_error_fixer(model) -> Any:
    print("[ENTER] wrapper:error_fixer.make_error_fixer")
    system = (
        "You are GPT-5, a precise Minecraft 1.21 (NeoForge) mod engineer. Given an error, "
        "propose the smallest-possible code edits to fix it. Output ONLY the required JSON, "
        "no commentary. Use ONLY actions 'replace_range' or 'insert' as defined, and do not "
        "create/delete/move files."
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
        "- You may only output edits using actions 'replace_range' or 'insert'.\n"
        "- For replace_range: include start_line,end_line (1-based inclusive).\n"
        "- For insert: include at_line (1-based; may be len(file)+1 to append).\n"
        "- Do NOT create, delete, or move files. Modify only existing files.\n"
        "- Paths must be workspace-relative.\n\n"
        "Return JSON with keys 'explanation' and 'edits' as specified."
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        ("human", human),
    ])
    chain = prompt | model | JsonOutputParser()
    return chain


__all__ = ["make_error_fixer"]

