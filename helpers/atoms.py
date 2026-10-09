"""Notion → Atom mapping — port of Khan's ``connectors/notion.py``.

Atoms are the flat knowledge units the Kurultai/device-sync pipelines
already speak (``id``, ``title``, ``content``, ``tags``, ``source``,
``extra``). Two ingestion shapes:

* ``notion://database/<database_id>`` — live query via NotionClient.
* ``file://…/<name>.notion.json`` — cached export (array of page objects).

Bulk/scheduled sync is deliberately out of scope (Khan#196: ingestion
jobs call dlt/readers); this module provides the mapping both paths use.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

from usr.plugins.notion.helpers.notion_client import NotionClient
from usr.plugins.notion.helpers.notion_fmt import extract_title


def page_to_atom(page: dict[str, Any], source_uri: str) -> dict[str, Any]:
    """Map a Notion page object to an Atom dict (Khan ``Atom.to_dict``)."""
    page_id = page.get("id")
    if not isinstance(page_id, str) or not page_id:
        raise ValueError("Notion page object missing 'id' field")

    atom: dict[str, Any] = {
        "id": page_id,
        "title": extract_title(page),
        "content": json.dumps(
            page.get("properties") or {}, ensure_ascii=False, sort_keys=True
        ),
        "tags": ["notion"],
        "source": source_uri,
        "extra": {"object": page.get("object", "page")},
    }
    parent = page.get("parent")
    if parent is not None:
        atom["extra"]["parent"] = parent
    return atom


def can_ingest(uri: str) -> bool:
    lower = str(uri or "").lower()
    return lower.startswith("notion://") or lower.endswith(".notion.json")


def ingest_file(path: Path) -> Iterator[dict[str, Any]]:
    """Parse a cached ``.notion.json`` export into atoms."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected array of page objects in {path}")
    for page in data:
        if not isinstance(page, dict):
            raise ValueError(f"Expected page object (dict) in {path}")
        yield page_to_atom(page, str(path))


def ingest_notion_uri(uri: str, client: NotionClient) -> Iterator[dict[str, Any]]:
    """``notion://database/<id>`` — live query through the client."""
    parsed = urlparse(uri)
    full_path = f"{parsed.netloc}{parsed.path}".strip("/")
    parts = full_path.split("/")
    if len(parts) != 2 or parts[0] != "database":
        raise ValueError(
            f"Unsupported notion:// path: {full_path}. "
            "Expected notion://database/<database_id>"
        )
    for page in client.query_database(parts[1]):
        yield page_to_atom(page, uri)


def ingest(uri: str, client: NotionClient | None = None) -> Iterator[dict[str, Any]]:
    """Dispatch by URI shape; client required for notion:// URIs."""
    if not can_ingest(uri):
        raise ValueError(f"Cannot ingest: {uri}")
    if str(uri).lower().startswith("notion://"):
        if client is None:
            raise ValueError("notion:// ingestion requires a NotionClient")
        yield from ingest_notion_uri(uri, client)
        return
    path = Path(str(uri)[len("file://"):] if str(uri).startswith("file://") else str(uri))
    if not path.is_file():
        raise FileNotFoundError(f"No such file: {path}")
    yield from ingest_file(path)
