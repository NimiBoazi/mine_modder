from __future__ import annotations

from typing import Any, Dict, List

from ..state import AgentState

try:
    from backend.agent.providers.summarize_user_message import build_summarize_user_message
except Exception:  # pragma: no cover
    build_summarize_user_message = None  # type: ignore


def _collect_items_for_summary(items_map: Dict[str, Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not isinstance(items_map, dict):
        return items
    for _iid, schema in items_map.items():
        if not isinstance(schema, dict):
            continue
        items.append({
            "item_id": schema.get("item_id") or _iid,
            "display_name": schema.get("display_name"),
            "description": schema.get("description"),
            "recipe_ingredients": schema.get("recipe_ingredients"),
            "is_consumable": schema.get("is_consumable"),
            "tags": schema.get("tags"),
            "tooltip_text": schema.get("tooltip_text"),
        })
    return items


def _max_attempts_reached_from_events(events: List[Dict[str, Any]] | None) -> bool:
    if not isinstance(events, list):
        return False
    for ev in events:
        try:
            if (ev.get("node") == "verify_task" and ev.get("ok") is False and int(ev.get("attempts") or 0) >= 3):
                return True
        except Exception:
            continue
    return False



def summarize_and_finish(state: AgentState) -> AgentState:
    print("[ENTER] node:summarize_and_finish")

    # Prepare payload from state (mod + items + events)
    mod_name = (state.get("display_name") or state.get("modid") or "Your Mod")
    mod_desc = state.get("description") or ""
    modid = state.get("modid") or ""
    items_payload = _collect_items_for_summary(state.get("items"))
    events = state.get("events") or []

    summary_text: str | None = None

    # If verification exhausted attempts, show a generic helpful message instead of detailed summary
    try:
        maxed = bool(state.get("max_verify_attempts_reached")) or _max_attempts_reached_from_events(events)
    except Exception:
        maxed = bool(state.get("max_verify_attempts_reached"))

    if maxed:
        summary_text = (
            f"Thanks for using MineModder! We weren’t able to successfully build your mod '{mod_name}' "
            "after several automated fix attempts. This can happen when code changes conflict or when the "
            "request needs a clearer specification. Please try again with a more specific or differently "
            "phrased request. A downloadable copy of your project is attached so you can review or continue iterating."
        )
    else:
        # Try LLM-based summary if available
        try:
            builder = build_summarize_user_message if build_summarize_user_message else None
            runnable = builder() if builder else None
            if runnable is not None:
                payload = {
                    "mod_name": mod_name,
                    "mod_description": mod_desc,
                    "modid": modid,
                    "items": items_payload,
                    "events": events,
                }
                result = runnable.invoke(payload)
                txt = "" if result is None else str(result).strip()
                # Guard against useless bracket-only outputs like [] or {}
                if txt in {"[]", "{}", "[ ]", "{ }"}:
                    txt = ""
                summary_text = txt
        except Exception as e:
            # Fallback below
            print(f"[WARN] summarize LLM failed: {e}")

    # Deterministic fallback if LLM unavailable
    if not summary_text:
        lines: List[str] = []
        lines.append(f"Thanks for using MineModder! Your mod '{mod_name}' is ready.")
        if mod_desc:
            lines.append(mod_desc)
        if items_payload:
            lines.append("")
            lines.append("Here are the items we created:")
            for it in items_payload:
                dn = it.get("display_name") or it.get("item_id")
                desc = it.get("description") or ""
                rec = it.get("recipe_ingredients") or []
                cons = it.get("is_consumable")
                bullet = f"- {dn}: {desc}"
                if rec:
                    bullet += f" | Recipe: {', '.join([str(x) for x in rec])}"
                if cons is True:
                    bullet += " | Consumable"
                lines.append(bullet)
        summary_text = "\n".join(lines)

    # Append packaging + launch instructions for the user (Prism Launcher + MDK)
    try:
        mc_ver = state.get("mc_version") or ""
        instructions: list[str] = []
        instructions.append("")
        instructions.append("How to build your JAR and load it in Prism Launcher:")
        instructions.append("1) Download and unzip the MDK project (the ZIP provided above).")
        instructions.append("2) Open a terminal in the unzipped project folder.")
        instructions.append("3) Build the mod: ./gradlew runData build   (on Windows: gradlew.bat runData build)")
        instructions.append("4) After it finishes, your mod JAR will be here: build/libs/")
        if mc_ver:
            instructions.append(f"5) In Prism Launcher: create/select a Minecraft {mc_ver} instance with NeoForge, open the instance mods folder, and drop the JAR in. Then launch.")
        else:
            instructions.append("5) In Prism Launcher: create/select a matching Minecraft instance with NeoForge, open the instance mods folder, and drop the JAR in. Then launch.")
        instructions.append("")
        instructions.append("Tip: The ZIP contains the full MDK project; you can open it in your IDE to continue editing.")
        summary_text = (summary_text or "").rstrip() + "\n\n" + "\n".join(instructions)
    except Exception:
        pass

    state["summary"] = summary_text
    # After finishing, explicitly clear any stale follow-up input and mark awaiting
    state["followup_user_input"] = ""
    state["followup_message"] = ""
    state["awaiting_user_input"] = True
    state.setdefault("events", []).append({"node": "summarize_and_finish", "ok": True})
    return state