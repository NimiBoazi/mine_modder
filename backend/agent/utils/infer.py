from __future__ import annotations

import re
from typing import List

JAVA_KEYWORDS = {
    "abstract","continue","for","new","switch","assert","default","goto","package","synchronized",
    "boolean","do","if","private","this","break","double","implements","protected","throw","byte",
    "else","import","public","throws","case","enum","instanceof","return","transient","catch","extends",
    "int","short","try","char","final","interface","static","void","class","finally","long","strictfp",
    "volatile","const","float","native","super","while"
}

RESERVED_MODIDS = {"minecraft","forge","fabric","neoforge"}


def slugify_modid(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "mod"
    if not s[0].isalpha():
        s = "m_" + s
    s = s[:32]
    if s in RESERVED_MODIDS:
        s = s + "_mod"
    return s


def derive_group_from_authors(authors: List[str]) -> str:
    primary = (authors or ["example"])[0]
    base = re.sub(r"[^a-z0-9]", "", primary.lower())
    if not base or not base[0].isalpha():
        base = "org_" + (base or "example")
    return f"io.{base}"


def sanitize_pkg_segment(seg: str) -> str:
    seg = re.sub(r"[^a-z0-9_]", "_", seg.lower())
    if not seg:
        seg = "x"
    if seg[0].isdigit():
        seg = "x_" + seg
    if seg in JAVA_KEYWORDS:
        seg = seg + "_"
    return seg


def make_package(group: str, modid: str) -> str:
    parts = group.split(".") + [modid]
    return ".".join(sanitize_pkg_segment(p) for p in parts)


def truncate_desc(s: str, limit: int = 160) -> str:
    s = (s or "").strip()
    return s if len(s) <= limit else s[:limit].rstrip() + "…"

