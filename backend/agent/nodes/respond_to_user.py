from __future__ import annotations

from typing import Dict, Any
from pathlib import Path

from backend.agent.state import AgentState
from backend.agent.wrappers.storage import STORAGE as storage
from backend.agent.wrappers.utils import insert_before_anchor
from backend.agent.tools.verify.verify_logger import log_json, log_text, log_exception

# Path resolution helpers
try:
    from backend.agent.wrappers.item_schema import (
        get_custom_item_class_path as _get_custom_item_class_path,
    )
except Exception:  # pragma: no cover
    _get_custom_item_class_path = None  # type: ignore

# Core workspace path resolvers (no hardcoding)
try:
    from backend.agent.providers.paths import (
        mod_items_file as _mod_items_file,
        mod_food_properties_file as _mod_food_properties_file,
        mod_item_model_provider_file as _mod_item_model_provider_file,
        mod_item_tag_provider_file as _mod_item_tag_provider_file,
        mod_recipe_provider_file as _mod_recipe_provider_file,
        main_class_file as _main_class_file,
        lang_file as _lang_file,
    )
except Exception:  # pragma: no cover
    _mod_items_file = None  # type: ignore
    _mod_food_properties_file = None  # type: ignore
    _mod_item_model_provider_file = None  # type: ignore
    _mod_item_tag_provider_file = None  # type: ignore
    _mod_recipe_provider_file = None  # type: ignore
    _main_class_file = None  # type: ignore
    _lang_file = None  # type: ignore

# Provider for the LLM wrapper
try:
    from backend.agent.providers.respond_to_user import build_respond_to_user
except Exception:  # pragma: no cover
    build_respond_to_user = None  # type: ignore


def _anchor_literal(anchor_name: str) -> str:
    """Map an anchor key (e.g., EXTRA_IMPORTS_END) to the literal marker used in files."""
    return f"// ==MM:{anchor_name}=="


def _apply_anchor_edits(ws: Path, path: str, edits: Dict[str, str]) -> Dict[str, Any]:
    target = (ws / path).resolve()
    if not storage.exists(target):
        return {"ok": False, "reason": "file_not_found", "path": path}
    src = storage.read_text(target, encoding="utf-8", errors="ignore")
    updated = src
    changed = False
    for anchor_key, code in (edits or {}).items():
        anchor_lit = _anchor_literal(anchor_key)
        # Insert before the anchor marker; anchors using *_END represent end of a block
        updated2 = insert_before_anchor(updated, anchor_lit, (code or "").rstrip("\n"))
        if updated2 != updated:
            updated = updated2
            changed = True
    if changed:
        storage.write_text(target, updated, encoding="utf-8")
    return {"ok": True, "changed": changed, "path": path}


def _extract_anchor_regions(text: str, anchors: list[str]) -> dict[str, str]:
    """Return a mapping of anchor_name -> snippet content for the requested anchors.
    If both *_BEGIN and *_END exist for a pair, returns the inner block. Otherwise returns
    up to 6 lines of context around the single anchor marker.
    """
    lines = text.splitlines()
    idx_by_name: dict[str, int] = {}
    for i, ln in enumerate(lines):
        ln_stripped = ln.strip()
        if ln_stripped.startswith("// ==MM:") and ln_stripped.endswith("=="):
            name = ln_stripped[len("// ==MM:"):-len("==")]
            idx_by_name[name] = i
    out: dict[str, str] = {}
    for name in anchors or []:
        begin = name if name.endswith("_BEGIN") else name.replace("_END", "_BEGIN")
        end = name if name.endswith("_END") else name.replace("_BEGIN", "_END")
        bi = idx_by_name.get(begin)
        ei = idx_by_name.get(end)
        if bi is not None and ei is not None and ei > bi:
            # inner block between the markers
            block = "\n".join(lines[bi+1:ei]).rstrip("\n")
            out[name] = block
        else:
            ai = idx_by_name.get(name)
            if ai is None:
                raise ValueError(f"Anchor not found: {name}")
            # Single-marker anchors have no inner block; provide empty content placeholder
            out[name] = ""
    return out



def _list_anchor_names(text: str) -> set[str]:
    lines = text.splitlines()
    names: set[str] = set()
    for ln in lines:
        s = ln.strip()
        if s.startswith("// ==MM:") and s.endswith("=="):
            names.add(s[len("// ==MM:"):-len("==")])
    return names


def _camel_case_modid(modid: str) -> str:
    parts = [p for p in str(modid or "").split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def _try_resolve_project_alias(ws: Path, state: AgentState, file_id: str) -> Path | None:
    """Resolve known manifest aliases (e.g., custom_item_class:<item_id>) to real workspace paths.
    Uses providers.paths helpers—no hardcoded strings. Returns absolute Path or None.
    """
    try:
        alias = str(file_id).strip()
        base_package = str(state.get("package") or "").strip()
        modid = str(state.get("modid") or "").strip()

        # 1) Per-item custom class alias
        if alias.startswith("custom_item_class:"):
            item_id = alias.split(":", 1)[1]
            items_index = dict(state.get("items") or {})
            schema = items_index.get(item_id)
            if not isinstance(schema, dict) or not base_package or _get_custom_item_class_path is None:
                return None
            p = _get_custom_item_class_path(ws, base_package, schema)
            return p.resolve()

        # 2) Static project files from base manifest
        if alias == "mod_items_file" and base_package and _mod_items_file is not None:
            return _mod_items_file(ws, base_package).resolve()
        if alias == "mod_food_properties_file" and base_package and _mod_food_properties_file is not None:
            return _mod_food_properties_file(ws, base_package).resolve()
        if alias == "mod_item_model_provider_file" and base_package and _mod_item_model_provider_file is not None:
            return _mod_item_model_provider_file(ws, base_package).resolve()
        if alias == "mod_item_tag_provider_file" and base_package and _mod_item_tag_provider_file is not None:
            return _mod_item_tag_provider_file(ws, base_package).resolve()
        if alias == "mod_recipe_provider_file" and base_package and _mod_recipe_provider_file is not None:
            return _mod_recipe_provider_file(ws, base_package).resolve()
        if alias == "lang_file" and modid and _lang_file is not None:
            return _lang_file(ws, modid).resolve()
        if alias == "main_class_file" and base_package and modid and _main_class_file is not None:
            mcn = _camel_case_modid(modid)
            return _main_class_file(ws, base_package, mcn).resolve()
    except Exception:
        return None
    return None


def respond_to_user(state: AgentState) -> AgentState:
    print("[ENTER] node:respond_to_user")

    ws = Path(state.get("workspace_path") or "").resolve()
    print(f"[RESPOND] workspace={ws}")
    # Debug: print a snapshot of agent state for troubleshooting
    try:
        import json as _json
        print("[RESPOND] state snapshot:", _json.dumps(state, ensure_ascii=False)[:4000])
    except Exception:
        try:
            print("[RESPOND] state keys:", list(state.keys()))
        except Exception:
            pass

    # Note: Path truthiness is always True; validate string source too
    if not (state.get("workspace_path") or "").strip():
        # Try to recover from prior events (init_subgraph logs workspace_path there)
        try:
            for ev in reversed(list(state.get("events") or [])):
                wp = (ev.get("workspace_path") or "").strip()
                if wp:
                    state["workspace_path"] = wp
                    ws = Path(wp).resolve()
                    print(f"[RESPOND] recovered workspace from events: {ws}")
                    break
        except Exception:
            pass
    if not (state.get("workspace_path") or "").strip():
        raise RuntimeError("respond_to_user: missing workspace_path")

    # Normalize follow-up from either 'followup_message' (preferred) or legacy 'followup_user_input'
    followup = ((state.get("followup_message") or state.get("followup_user_input") or "")).strip()
    print(f"[RESPOND] followup_len={len(followup)} preview={followup[:120]!r}")
    if not followup:
        raise RuntimeError("respond_to_user: empty follow-up user input")
    # Clear both keys once we begin processing so routers don't loop on stale input
    state["followup_user_input"] = ""
    state["followup_message"] = ""

    items_index = dict(state.get("items") or {})

    print("[RESPOND] building respond_to_user provider")
    ru = build_respond_to_user() if build_respond_to_user else None
    if ru is None:
        raise RuntimeError("respond_to_user: provider unavailable")
    print("[RESPOND] provider ready")

    # Stage 1: decide
    decide_payload = {
        "stage": "decide",
        "user_prompt": followup,
        "items_index": items_index,
        "workspace_path": str(ws),
    }
    try:
        log_json(ws, "respond_to_user.decide.payload", decide_payload)
    except Exception:
        pass
    print("[RESPOND] invoking decide")
    decision = ru.invoke(decide_payload)
    print(f"[RESPOND] decide completed action={decision.get('action')!r}")
    try:
        log_json(ws, "respond_to_user.decide.response", decision)
    except Exception:
        pass

    action_raw = str(decision.get("action") or "").strip().upper()
    # Normalize common synonyms to keep graph edges stable
    synonyms = {
        "CREATE_NEW_ITEM": "PLAN_NEXT_TASKS",
        "CREATE_ITEM": "PLAN_NEXT_TASKS",
        "ADD_ITEM": "PLAN_NEXT_TASKS",
        "NEW_ITEM": "PLAN_NEXT_TASKS",
        "EDIT_FILE": "EDIT_FILES",
        "VIEW_FILE": "VIEW_FILES",
    }
    action = synonyms.get(action_raw, action_raw)
    allowed_actions = {"PLAN_NEXT_TASKS", "EDIT_FILES", "VIEW_FILES"}
    if action not in allowed_actions:
        raise ValueError(f"respond_to_user: invalid action '{action_raw}' from provider (normalized to '{action}' but not allowed)")
    # Persist normalized decision
    decision = dict(decision or {})
    decision["action"] = action
    state["respond_decision"] = decision

    if action == "PLAN_NEXT_TASKS":
        # Route back to planner with the new prompt
        state["user_input"] = followup
        state["route_after_respond"] = "plan_next_tasks"
        # Always mark awaiting_user_input True at the end of this node
        state["awaiting_user_input"] = True
        state.setdefault("events", []).append({"node": "respond_to_user", "ok": True, "action": action})
        return state

    if action in {"EDIT_FILES", "VIEW_FILES"}:
        # Stage 1.5: choose files and anchors
        choose_payload = {
            "stage": "choose",
            "action": action,
            "user_prompt": followup,
            "items_index": items_index,
            "workspace_path": str(ws),
        }
        try:
            log_json(ws, "respond_to_user.choose.payload", choose_payload)
        except Exception:
            pass
        print("[RESPOND] invoking choose")
        choose_out = ru.invoke(choose_payload)
        print(f"[RESPOND] choose completed files={len(choose_out.get('files') or [])}")
        try:
            log_json(ws, "respond_to_user.choose.response", choose_out)
        except Exception:
            pass

        files_list = choose_out.get("files") or []
        if not isinstance(files_list, list) or not files_list:
            raise ValueError(f"respond_to_user.choose returned no files for action {action}")

        import json as _json
        context_files: Dict[str, str] = {}
        event_files = []
        for entry in files_list:
            if not isinstance(entry, dict):
                continue
            file_path = str(entry.get("file_path") or "").strip()
            if not file_path:
                continue
            request_full = bool(entry.get("request_full_file", False))
            anchors = entry.get("anchors") or []
            # Resolve aliases from the project manifest to concrete paths, else accept explicit relative paths
            if ":" in file_path and not any(sep in file_path for sep in ["/", "\\"]):
                # Alias form, e.g., custom_item_class:<item_id>
                full_path = _try_resolve_project_alias(ws, state, file_path)
                if full_path is None:
                    raise RuntimeError(
                        f"respond_to_user.choose returned alias '{file_path}' that cannot be resolved. "
                        "Use a known manifest alias (e.g., custom_item_class:<item_id>) that maps to a real file, or provide a real path."
                    )
                try:
                    full_path = full_path.resolve()
                    full_path.relative_to(ws)
                except Exception:
                    raise RuntimeError(
                        f"respond_to_user: resolved alias '{file_path}' points outside workspace. Rejecting."
                    )
                # Keep the key as a workspace-relative string for downstream mapping
                try:
                    file_path = str(full_path.relative_to(ws))
                except Exception:
                    file_path = str(full_path)
            else:
                full_path = (ws / file_path).resolve()
                try:
                    full_path.relative_to(ws)
                except Exception:
                    raise RuntimeError(
                        f"respond_to_user: file '{file_path}' resolves outside workspace. Rejecting."
                    )
            try:
                if not full_path.exists() or not full_path.is_file():
                    raise RuntimeError(
                        f"respond_to_user: file '{file_path}' does not exist under workspace {ws}."
                    )
                src_text = storage.read_text(full_path, encoding="utf-8", errors="ignore")
            except Exception as e:
                raise RuntimeError(f"respond_to_user: failed to read file '{file_path}': {e}") from e
            if request_full or not anchors:
                context_payload = src_text
            else:
                req = [str(a) for a in anchors if isinstance(a, (str, bytes))]
                available = _list_anchor_names(src_text)
                missing = [a for a in req if not (a in available or f"{a}_BEGIN" in available or f"{a}_END" in available)]
                if missing:
                    raise ValueError(
                        f"respond_to_user: requested anchors not found in {file_path}: {missing}. "
                        f"Available: {sorted(list(available))[:50]}"
                    )
                anchor_map = _extract_anchor_regions(src_text, req)
                context_payload = _json.dumps({"anchors": anchor_map}, ensure_ascii=False, indent=2)
            context_files[file_path] = context_payload
            event_files.append({"path": file_path, "anchors": anchors})

        # Stage 2: act with multi-file context
        act_payload = {
            "stage": "act",
            "decision": {"action": action},
            "user_prompt": followup,
            "context_files": context_files,
            "workspace_path": str(ws),
        }
        try:
            log_json(ws, "respond_to_user.act.payload", act_payload)
        except Exception:
            pass
        print("[RESPOND] invoking act")
        act_out = ru.invoke(act_payload)
        print("[RESPOND] act completed")
        try:
            log_json(ws, "respond_to_user.act.response", act_out)
        except Exception:
            pass
        state["respond_action_output"] = act_out

        if action == "VIEW_FILES":
            answer = act_out.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("respond_to_user.act returned no 'answer' for VIEW_FILES")
            state["last_user_response"] = answer
            # After VIEW_FILES, immediately return to awaiting user input
            state["awaiting_user_input"] = True
            state["route_after_respond"] = "await_user_input"
            state.setdefault("events", []).append({
                "node": "respond_to_user",
                "ok": True,
                "action": action,
                "files": event_files,
            })
            return state

        if action == "EDIT_FILES":
            edits_by_file = act_out.get("edits") or {}
            if not isinstance(edits_by_file, dict) or not edits_by_file:
                raise ValueError("respond_to_user.act returned invalid 'edits' for EDIT_FILES")
            results = []
            for fpath, edits in edits_by_file.items():
                if not isinstance(edits, dict):
                    raise ValueError(f"respond_to_user.act provided non-dict edits for file {fpath}")
                # Allow alias keys here too; resolve to concrete workspace path string
                if ":" in fpath and not any(sep in fpath for sep in ["/", "\\"]):
                    resolved = _try_resolve_project_alias(ws, state, fpath)
                    if resolved is None:
                        raise RuntimeError(
                            f"respond_to_user.act returned alias '{fpath}' that cannot be resolved to a file path."
                        )
                    try:
                        fpath = str(resolved.resolve().relative_to(ws))
                    except Exception:
                        fpath = str(resolved.resolve())
                res = _apply_anchor_edits(ws, fpath, edits)
                results.append({"path": fpath, **res})
            state["last_edit_summary"] = {"results": results}
            # Mark that the last follow-up action was EDIT_FILES (affects post-verify routing)
            state["last_followup_action"] = "EDIT_FILES"
            state["route_after_respond"] = "verify_task"
            # Always mark awaiting_user_input True at the end of this node
            state["awaiting_user_input"] = True
            any_ok = any(bool(r.get("ok")) for r in results)
            state.setdefault("events", []).append({
                "node": "respond_to_user",
                "ok": any_ok,
                "action": action,
                "files": event_files,
            })
            return state

    # No fallbacks: unhandled state is an error
    raise RuntimeError(f"respond_to_user: unsupported or unhandled action '{action}'")

