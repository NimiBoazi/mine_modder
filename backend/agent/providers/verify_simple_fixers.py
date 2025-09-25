from __future__ import annotations

from typing import Optional, Dict, Any

from langchain_core.runnables import Runnable
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from backend.agent.providers.gpt5_provider import build_gpt5_chat_model


def build_import_line_fixer() -> Optional[Runnable]:
    """Return a Runnable that, given an error excerpt, returns ONE Java import line.

    Input keys: error_excerpt (str), symbol_hint (optional str), file_header (optional str)
    Output: str (a single line like "import com.example.Foo;")
    """
    model = build_gpt5_chat_model()
    if model is None:
        return None

    # Force JSON/text-only determinism: we instruct to return a single line.
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You generate exactly ONE valid Java import statement line given a compiler error.\n"
                   "- Output only the import line, no commentary.\n"
                   "- If multiple imports could fix it, choose the most canonical one.\n"
                   "- Format: 'import <package>.<Type>;'.\n"),
        ("human", "Target environment: {env_context}\n\n"
                  "Error excerpt:\n{error_excerpt}\n\n"
                  "File header (package+imports, optional):\n{file_header}\n\n"
                  "If helpful, symbol hint: {symbol_hint}"),
    ])

    chain: Runnable = prompt | model | StrOutputParser()
    return chain


def build_line_replacement_fixer() -> Optional[Runnable]:
    """Return a Runnable that, given error excerpt + full file content, returns JSON array
    of objects with keys 'old line' and 'new line'. No commentary.

    Input keys: error_excerpt (str), file_path (str), file_content (str)
    Output: str JSON like: [{"old line": "...", "new line": "..."}, ...]
    """
    model = build_gpt5_chat_model()
    if model is None:
        return None

    # Encourage strict JSON array with the exact keys.
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You fix Minecraft Neoforge compile errors by proposing strict line-by-line replacements.\n"
                   "Return ONLY a JSON array. Each element MUST have keys: 'old line' and 'new line'.\n"
                   "No markdown/code fences, no commentary, and no extra fields.\n"
                   "Preserve Java syntax, semicolons, and indentation.\n"
                   "Output format example (JSON exactly):\n"
                   "[\n"
                   "  {{\"old line\": \"Exact existing line\", \"new line\": \"Exact replacement line\"}}\n"
                   "]\n"
                   "Multiple edits example (two objects):\n"
                   "[\n"
                   "  {{\"old line\": \"Existing line A\", \"new line\": \"Replacement line A\"}},\n"
                   "  {{\"old line\": \"Existing line B\", \"new line\": \"Replacement line B\"}}\n"
                   "]\n"
                   "Each 'old line' MUST exactly match a full line from file_content.\n"),
        ("human", "Target environment: {env_context}\n\n"
                  "Provide minimal line replacements to fix the error.\n"
                  "- Use exact current lines for 'old line' (full line).\n"
                  "- 'new line' must be the full replacement line.\n\n"
                  "Error excerpt:\n{error_excerpt}\n\n"
                  "File path: {file_path}\n\n"
                  "File content:\n````java\n{file_content}\n````\n")
    ])

    # We want raw text back that is JSON; the node will parse JSON safely.
    chain: Runnable = prompt | model | StrOutputParser()
    return chain

