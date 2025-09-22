from __future__ import annotations

"""
GPT-5 error analyzer runnable for verify task.

Takes a structured payload:
{
  error_type: "compile" | "datagen" | "runtime" | "unknown",
  command: "./gradlew <task>",
  versions: { mc: str, neoforge: str | None, java: str | None },
  errors: [...],            # compile: list of {path,line,message}
  stack_head: [...],        # datagen/runtime: leading lines of stack
  caused_by: [...],         # datagen/runtime: all 'Caused by:' lines
  resource_lines: [...],    # runtime: missing texture/model lines
  code_snippets: [ {path,start_line,end_line,code} ]
}

Returns a short analysis with likely cause(s) and precise suggested fix steps.
"""

from typing import Any, Dict
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


def make_error_analyzer(model) -> Any:
    print("[ENTER] wrapper:error_analyzer.make_error_analyzer")
    system = (
        "You are GPT-5, an expert Minecraft 1.21 (NeoForge) mod engineer.\n"
        "Analyze the provided Gradle/MC error and produce:\n"
        "1) Likely cause in 1-2 sentences.\n"
        "2) Exact file:line edits or JSON/resource fixes (be explicit).\n"
        "3) If datagen, specify which provider/method and resource path to adjust.\n"
        "4) If runtime missing textures/models, give the exact expected file path(s).\n"
        "Keep it concise; avoid boilerplate.\n"
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        (
            "human",
            "Command: {command}\n"
            "Error type: {error_type}\n"
            "Versions: MC={mc_version} NeoForge={neoforge_version} Java={java_version}\n"
            "Errors: {errors}\n"
            "Stack head: {stack_head}\n"
            "Caused by: {caused_by}\n"
            "Missing resource lines: {resource_lines}\n"
            "Code snippets (brief):\n{code_snippets}"
        ),
    ])

    chain = prompt | model | StrOutputParser()
    return chain


__all__ = ["make_error_analyzer"]

