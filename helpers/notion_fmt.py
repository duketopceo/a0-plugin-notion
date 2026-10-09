"""Notion object → text/dict formatting — stdlib only, no a0 imports.

Shared by the MCP server (which runs in a subprocess where only the
plugin dir is on sys.path) and by host-side helpers. Keep this module
free of any a0 or ``usr.plugins`` imports — both namespaces must be able
to load it standalone.
"""

from __future__ import annotations

from typing import Any


def _title_of(entries: Any) -> str:
    """First non-empty rich_text flatten — handles multi-segment titles
    (formatting splits the array) and the plain_text fallback."""
    text = rich_text(entries if isinstance(entries, list) else []).strip()
    return text


def extract_title(page: dict[str, Any]) -> str:
    """Best available title for a Notion page object."""
    properties = page.get("properties") or {}
    title_prop = properties.get("title")
    if isinstance(title_prop, dict):
        t = _title_of(title_prop.get("title"))
        if t:
            return t

    top_title = page.get("title")
    if isinstance(top_title, str) and top_title.strip():
        return top_title.strip()
    t = _title_of(top_title)
    if t:
        return t

    # Fallback: any title-typed property (database title columns can be
    # named anything).
    for prop in properties.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            t = _title_of(prop.get("title"))
            if t:
                return t
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


def page_detail(page: dict[str, Any]) -> dict[str, Any]:
    """page_summary + compacted property values (get_page tool shape)."""
    out = page_summary(page)
    props = page.get("properties") or {}
    out["properties"] = {
        name: prop_value(p) for name, p in props.items() if isinstance(p, dict)
    }
    return out


def results_payload(items: list[dict[str, Any]]) -> dict[str, Any]:
    """The {count, results:[summary]} envelope both list-tools emit."""
    return {"count": len(items), "results": [page_summary(i) for i in items]}


_TEXT_BUDGET = 100_000  # chars — flattened text lands in an agent context


def blocks_to_text(
    blocks: list[dict[str, Any]], *, text_budget: int = _TEXT_BUDGET
) -> str:
    """Flatten a block list to readable text with a cumulative char
    budget — block *count* caps don't bound rich_text size."""
    lines: list[str] = []
    total = 0
    for block in blocks:
        line = block_to_line(block)
        if line is None:
            continue
        if total + len(line) > text_budget:
            lines.append("…[truncated]")
            break
        lines.append(line)
        total += len(line) + 1
    return "\n".join(lines)


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
