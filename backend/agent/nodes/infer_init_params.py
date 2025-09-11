from ..state import AgentState
from ..utils.infer import slugify_modid, derive_group_from_authors, make_package, truncate_desc

def make_infer_init_params_node(name_desc_chain=None):
    def infer_init_params(state: AgentState) -> AgentState:
        user_prompt = state.get("user_input") or ""
        name = state.get("display_name")
        desc = state.get("description")

        authors_val = state.get("authors") or state.get("author")
        if isinstance(authors_val, str):
            authors = [authors_val.strip()] if authors_val.strip() else []
            state["authors"] = authors
        elif isinstance(authors_val, list):
            state["authors"] = [str(a).strip() for a in authors_val if str(a).strip()]
        else:
            state["authors"] = []

        if not name or not desc:
            try:
                if name_desc_chain is not None:
                    out = name_desc_chain.invoke(user_prompt)
                    name = name or out.get("name")
                    desc = desc or out.get("description")
                else:
                    raise RuntimeError("No name/desc chain configured")
            except Exception:
                name = name or "My Mod"
                desc = desc or "A Minecraft mod."

        desc = truncate_desc(desc or "")
        state["display_name"] = name
        state["description"] = desc

        modid = slugify_modid(name)
        authors = state.get("authors") or []
        group = derive_group_from_authors(authors)
        package = make_package(group, modid)

        state["modid"] = modid
        state["group"] = group
        state["package"] = package
        state.setdefault("version", "0.1.0")
        state.setdefault("timeout", 1800)

        state.setdefault("events", []).append({"node": "infer_init_params", "ok": True, "modid": modid, "group": group, "package": package})
        return state
    return infer_init_params