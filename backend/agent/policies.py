def tasklist_triggers(user_input: str, plan_needed: bool=False) -> bool:
    ui = (user_input or "").lower()
    return any(k in ui for k in ["plan","roadmap","next steps"]) or plan_needed

def pick_high_signal_tool(user_input: str) -> str:
    ui = (user_input or "").lower()
    if "why was" in ui or "how was" in ui or "commit" in ui: return "git-commit-retrieval"
    if any(t in ui for t in ["class ", "def ", "::", "symbol", "reference"]): return "grep-search"
    if any(t in ui for t in ["/", "\\", ".py", ".ts", ".java", ".json"]):     return "view"
    return "codebase-retrieval"
