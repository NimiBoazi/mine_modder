from __future__ import annotations

from typing import Dict, Any, Optional
import json
import time

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda

from backend.agent.tools.project_structure import load_and_augment_project_structure
from backend.agent.tools.verify.verify_logger import log_json as _v_log_json


def _strip_md_fences(s: str) -> str:
    s = str(s).strip()
    if s.startswith("```"):
        i = s.find("\n")
        if i != -1:
            s = s[i + 1 :]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def make_respond_to_user(model: BaseChatModel) -> Runnable[Dict[str, Any], Dict[str, Any]]:
    """
    Multi-step LLM helper for user follow-ups with simpler prompts:
    - stage="decide": choose the action ONLY from the allowed list
    - stage="choose": (for EDIT_FILES/VIEW_FILES) pick one or more files and anchors (or full files)
    - stage="act": given the chosen file contexts, produce either edits or an answer

    Input (decide):
      {"stage":"decide", "user_prompt": str, "items_index": dict}
    Output (decide):
      {"action":"PLAN_NEXT_TASKS"|"EDIT_FILES"|"VIEW_FILES", "reason": str}

    Input (choose):
      {"stage":"choose", "action": "EDIT_FILES"|"VIEW_FILES", "user_prompt": str, "items_index": dict}
    Output (choose):
      {"files": [{"file_path": "<path>", "anchors": [str]|null, "request_full_file": bool|false}, ...]}

    Input (act):
      {"stage":"act", "decision": {"action": "EDIT_FILES"|"VIEW_FILES"}, "user_prompt": str,
       "context_files": {"<path>": "<content>"}}
    Output (act for EDIT_FILES):
      {"edits": {"<path>": {"<ANCHOR_NAME>": "<CODE>"}}}
    Output (act for VIEW_FILES):
      {"answer": "..."}
    """

    def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
        stage = (payload.get("stage") or "").strip().lower()
        print(f"[ENTER] wrapper:respond_to_user stage={stage}")

        if stage == "decide":
            user_prompt = str(payload.get("user_prompt") or "").strip()
            items_index: Dict[str, Any] = dict(payload.get("items_index") or {})

            # Build augmented manifest in-memory (not persisted)
            manifest = load_and_augment_project_structure(items_index=items_index)
            manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)

            system = SystemMessage(content=(
                "You are an expert assistant for a NeoForge Minecraft mod project. "
                "Given a user request and the project structure manifest (with anchors), decide ONLY the action. "
                "STRICT REQUIREMENTS: "
                "- Return STRICT JSON only (no Markdown). "
                "- The field 'action' MUST be EXACTLY one of: PLAN_NEXT_TASKS, EDIT_FILES, VIEW_FILES (UPPERCASE). "
                "- Do NOT invent any other action labels. "
                "- If the user wants to add/create a new item or broader features, choose PLAN_NEXT_TASKS (think: 'create new item')."
            ))
            user = HumanMessage(content=(
                "User follow-up request:\n" + user_prompt + "\n\n" +
                "PROJECT STRUCTURE MANIFEST (JSON):\n" + manifest_json + "\n\n" +
                "Decide ONLY the action (no file paths yet).\n" \
                "Rules:\n" \
                "- If the request implies adding/removing larger features or multiple files, choose 'PLAN_NEXT_TASKS'.\n" \
                "- If a single or small set of existing files can be changed within known anchors, choose 'EDIT_FILES'.\n" \
                "- If the user only needs to inspect/answer from existing files, choose 'VIEW_FILES'.\n" \
                "Always include a short 'reason'.\n" \
                "Return JSON EXACTLY: {\"action\":\"PLAN_NEXT_TASKS\"|\"EDIT_FILES\"|\"VIEW_FILES\", \"reason\": \"...\"}"
            ))

            # Optional workspace for logging (passed from node)
            ws = str(payload.get("workspace_path") or "").strip()
            try:
                if ws:
                    _v_log_json(ws, "respond_to_user.decide.prompt", {
                        "system": system.content,
                        "user": user.content,
                    })
            except Exception:
                pass

            t0 = time.time()
            print("[LLM] respond_to_user.decide: invoking")
            resp = model.invoke([system, user])
            print(f"[LLM] respond_to_user.decide: completed in {time.time()-t0:.2f}s")
            raw = _strip_md_fences(resp.content if hasattr(resp, "content") else str(resp))
            try:
                data = json.loads(raw)
            except Exception as e:
                raise ValueError(f"respond_to_user.decide: invalid JSON from model: {e}")
            try:
                if ws:
                    _v_log_json(ws, "respond_to_user.decide.response_raw", {"raw": raw})
                    _v_log_json(ws, "respond_to_user.decide.response_parsed", data)
            except Exception:
                pass
            return data

        elif stage == "choose":
            action = str(payload.get("action") or "").strip().upper()
            if action not in {"EDIT_FILES", "VIEW_FILES"}:
                raise ValueError(f"respond_to_user.choose: invalid action '{action}'")
            user_prompt = str(payload.get("user_prompt") or "").strip()
            items_index: Dict[str, Any] = dict(payload.get("items_index") or {})
            manifest = load_and_augment_project_structure(items_index=items_index)
            manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)

            system = SystemMessage(content=(
                "Select one or more target files and anchors (or full files) needed for the chosen action. "
                "Return STRICT JSON only."
            ))
            user = HumanMessage(content=(
                "Action: " + action + "\n" +
                "User request:\n" + user_prompt + "\n\n" +
                "PROJECT STRUCTURE MANIFEST (JSON):\n" + manifest_json + "\n\n" +
                "Guidance: For file_path you may return a manifest alias key from the above manifest (e.g., mod_items_file, main_class_file, lang_file, mod_item_model_provider_file) "
                "or a per-item alias like custom_item_class:<item_id>.\n" +
                "Return JSON exactly: {\"files\":[{\"file_path\":\"<path>\", \"anchors\": null|[\"<ANCHOR_NAME>\"], \"request_full_file\": false}]}"
            ))
            ws = str(payload.get("workspace_path") or "").strip()
            try:
                if ws:
                    _v_log_json(ws, "respond_to_user.choose.prompt", {"system": system.content, "user": user.content})
            except Exception:
                pass
            t0 = time.time()
            print("[LLM] respond_to_user.choose: invoking")
            resp = model.invoke([system, user])
            print(f"[LLM] respond_to_user.choose: completed in {time.time()-t0:.2f}s")
            raw = _strip_md_fences(resp.content if hasattr(resp, "content") else str(resp))
            try:
                data = json.loads(raw)
            except Exception as e:
                raise ValueError(f"respond_to_user.choose: invalid JSON from model: {e}")
            try:
                if ws:
                    _v_log_json(ws, "respond_to_user.choose.response_raw", {"raw": raw})
                    _v_log_json(ws, "respond_to_user.choose.response_parsed", data)
            except Exception:
                pass
            return data

        elif stage == "act":
            decision = dict(payload.get("decision") or {})
            user_prompt = str(payload.get("user_prompt") or "").strip()
            context_files = dict(payload.get("context_files") or {})

            action = (decision.get("action") or "").strip().upper()
            system = SystemMessage(content=(
                "Continue for the user's follow-up using the provided file context."
            ))
            user = HumanMessage(content=(
                "User request:\n" + user_prompt + "\n\n" +
                "DECISION JSON:\n" + json.dumps(decision, ensure_ascii=False) + "\n\n" +
                "CONTEXT FILES (path->content):\n" + json.dumps(context_files, ensure_ascii=False) + "\n\n" +
                ("Respond with JSON: {\"edits\": {\"<path>\": {\"ANCHOR\": \"CODE\"}}} (strictly inside anchors)."
                 if action == "EDIT_FILES" else
                 "Respond with JSON: {\"answer\": \"...\"}")
            ))
            ws = str(payload.get("workspace_path") or "").strip()
            try:
                if ws:
                    _v_log_json(ws, "respond_to_user.act.prompt", {
                        "system": system.content,
                        "user": user.content,
                    })
            except Exception:
                pass

            t0 = time.time()
            print("[LLM] respond_to_user.act: invoking")
            resp = model.invoke([system, user])
            print(f"[LLM] respond_to_user.act: completed in {time.time()-t0:.2f}s")
            raw = _strip_md_fences(resp.content if hasattr(resp, "content") else str(resp))
            try:
                data = json.loads(raw)
            except Exception as e:
                raise ValueError(f"respond_to_user.act: invalid JSON from model: {e}")
            try:
                if ws:
                    _v_log_json(ws, "respond_to_user.act.response_raw", {"raw": raw})
                    _v_log_json(ws, "respond_to_user.act.response_parsed", data)
            except Exception:
                pass
            return data

        else:
            raise ValueError("respond_to_user wrapper requires stage to be 'decide', 'choose', or 'act'")

    return RunnableLambda(lambda x: _run(x))

