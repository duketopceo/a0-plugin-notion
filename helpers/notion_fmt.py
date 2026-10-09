"""Notion object → text/dict formatting — pure stdlib, zero imports.

Shared by the MCP server (which runs in a subprocess where only the
plugin dir is on sys.path) and by host-side helpers. Keep this module
free of any a0 or ``usr.plugins`` imports — both namespaces must be able
to load it standalone.
"""

from __future__ import annotations

from typing import Any


def extract_title(page: dict[str, Any]) -> str:
    """Best available title for a Notion page object."""
    properties = page.get("properties") or {}
    title_prop = properties.get("title")
    if isinstance(title_prop, dict):
        title_entries = title_prop.get("title") or []
        if isinstance(title_entries, list) and title_entries:
            first = title_entries[0]
            if isinstance(first, dict):
                text = first.get("text") or {}
                content = text.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()

    top_title = page.get("title")
    if isinstance(top_title, str) and top_title.strip():
        return top_title.strip()
    if isinstance(top_title, list) and top_title:
        first = top_title[0]
        if isinstance(first, dict):
            text = first.get("text") or {}
            content = text.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()

    # Fallback: any title-typed property (database title columns can be
    # named anything).
    for prop in properties.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            entries = prop.get("title") or []
            if entries and isinstance(entries[0], dict):
                content = (entries[0].get("text") or {}).get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
    return "Untitled"


def rich_text(rich: list[dict[str, Any]] | None) -> str:
    """Flatten a Notion rich_text array to plain text."""
    parts: list[str] = []
    for item in rich or []:
        if not isinstance(item, dict):
            continue
        content = (item.get("text") or {}).get("content")
        if content is None:
            content = item.get("plain_text", "")
        parts.append(str(content or ""))
    return "".join(parts)


_BLOCK_TYPES_WITH_RICH_TEXT = {
    "paragraph", "heading_1", "heading_2", "heading_3",
    "bulleted_list_item", "numbered_list_item", "to_do", "toggle",
    "quote", "callout", "equation",
}

_PREFIX = {
    "heading_1": "# ", "heading_2": "## ", "heading_3": "### ",
    "bulleted_list_item": "- ", "numbered_list_item": "1. ",
    "quote": "> ", "toggle": "▸ ",
}


def block_to_line(block: dict[str, Any]) -> str | None:
    """One block → one text line (or None for ignorable types)."""
    btype = block.get("type")
    if not isinstance(btype, str):
        return None
    body = block.get(btype)
    if not isinstance(body, dict):
        return None

    if btype == "code":
        lang = (body.get("language") or "").strip()
        return f"```{lang}\n{rich_text(body.get('rich_text'))}\n```"
    if btype == "to_do":
        mark = "x" if body.get("checked") else " "
        return f"- [{mark}] {rich_text(body.get('rich_text'))}"
    if btype == "divider":
        return "---"
    if btype == "child_page":
        return f"[page] {body.get('title', 'Untitled')}"
    if btype == "child_database":
        return f"[database] {body.get('title', 'Untitled')}"
    if btype in ("image", "file", "video", "pdf"):
        kind = body.get("type", "external")
        inner = body.get(kind)
        url = inner.get("url", "") if isinstance(inner, dict) else ""
        return f"[{btype}] {url}"
    if btype in _BLOCK_TYPES_WITH_RICH_TEXT:
        return f"{_PREFIX.get(btype, '')}{rich_text(body.get('rich_text'))}"
    if btype == "table_row":
        cells = body.get("cells") or []
        return " | ".join(rich_text(c) for c in cells)
    return f"[{btype}]"


def page_summary(page: dict[str, Any]) -> dict[str, Any]:
    """Compact search/row result: id + title + location metadata."""
    return {
        "id": page.get("id"),
        "title": extract_title(page),
        "object": page.get("object"),
        "url": page.get("url"),
        "last_edited_time": page.get("last_edited_time"),
        "parent": page.get("parent"),
    }


def prop_value(prop: dict[str, Any]) -> Any:
    """Compact a Notion property object to its display value."""
    ptype = prop.get("type")
    body = prop.get(ptype) if isinstance(ptype, str) else None
    if ptype in ("title", "rich_text"):
        return rich_text(body if isinstance(body, list) else [])
    if ptype == "select" and isinstance(body, dict):
        return body.get("name")
    if ptype == "multi_select" and isinstance(body, list):
        return [o.get("name") for o in body if isinstance(o, dict)]
    if ptype in ("number", "checkbox", "url", "email", "phone_number", "date",
                 "created_time", "last_edited_time"):
        return body
    if ptype == "people" and isinstance(body, list):
        return [p.get("name") for p in body if isinstance(p, dict)]
    if ptype == "status" and isinstance(body, dict):
        return body.get("name")
    return f"[{ptype}]" if ptype else None
