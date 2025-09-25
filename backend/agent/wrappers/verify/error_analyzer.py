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
from langchain_core.runnables import RunnableLambda


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

    parser = StrOutputParser()

    def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
        # Format messages
        msgs = prompt.format_messages(**payload)
        prev_id = str(payload.get("previous_response_id") or "").strip()
        call_model = model
        # Bind previous_response_id for reasoning continuity
        if prev_id:
            try:
                call_model = model.bind(previous_response_id=prev_id)
            except Exception:
                pass
        # Optional: set reasoning effort if supported
        try:
            call_model = call_model.bind(reasoning={"effort": "medium"})
        except Exception:
            pass

        resp = call_model.invoke(msgs)
        content = getattr(resp, "content", str(resp))
        # Extract response id (best-effort)
        rid = None
        try:
            rid = getattr(resp, "id", None)
            if not rid:
                meta = getattr(resp, "response_metadata", {}) or {}
                rid = meta.get("response_id") or meta.get("id")
        except Exception:
            rid = None
        try:
            analysis = parser.parse(content)
        except Exception:
            analysis = content
        return {"analysis": analysis, "_reasoning_response_id": rid}

    return RunnableLambda(lambda x: _run(x))


__all__ = ["make_error_analyzer"]

