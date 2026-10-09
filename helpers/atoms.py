"""Notion → Atom mapping — port of Khan's ``connectors/notion.py``.

Atoms are the flat knowledge units the Kurultai/device-sync pipelines
already speak (``id``, ``title``, ``content``, ``tags``, ``source``,
``extra``). Two ingestion shapes:

* ``notion://database/<database_id>`` — live query via NotionClient.
* ``file://…/<name>.notion.json`` — cached export (array of page objects).

Bulk/scheduled sync is deliberately out of scope (Khan#196: ingestion
jobs call dlt/readers); this module provides the mapping both paths use.

SECURITY: ingest URIs are OPERATOR-TRUSTED. The file path is suffix-keyed
(``.notion.json``), not confined to a directory — a pipeline that feeds
untrusted URIs into ``ingest()`` is handing file-read to that source, and
crafted exports become atoms in downstream stores (indirect prompt
injection). Only ingest exports the operator placed deliberately.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import unquote, urlparse

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


def _uri_kind(uri: str) -> str | None:
    """Single classifier — 'notion' for live URIs, 'file' for cached
    exports, None for everything else. can_ingest/ingest share it so a
    new shape can't silently fall into the file branch."""
    lower = str(uri or "").lower()
    if lower.startswith("notion://"):
        return "notion"
    if lower.endswith(".notion.json"):
        # only file:// or a bare path is ingestible — an http(s) URL ending
        # in .notion.json would otherwise pass can_ingest and then die in
        # ingest() as a bogus local path
        scheme = urlparse(str(uri or "")).scheme.lower()
        return "file" if scheme in ("", "file") else None
    return None


def can_ingest(uri: str) -> bool:
    return _uri_kind(uri) is not None


_MAX_EXPORT_BYTES = 256 * 1024 * 1024  # exports materialize whole; refuse monsters


def ingest_file(path: Path) -> Iterator[dict[str, Any]]:
    """Parse a cached ``.notion.json`` export into atoms."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise FileNotFoundError(f"Cannot stat {path}: {exc}") from exc
    if size > _MAX_EXPORT_BYTES:
        raise ValueError(
            f"{path} is {size / 1e6:.0f} MB — over the {_MAX_EXPORT_BYTES // 2**20} MB "
            "export cap; split the export or stream it through dlt"
        )
    data = json.loads(path.read_text(encoding="utf-8-sig"))  # tolerate BOM
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
    if len(parts) != 2 or parts[0].lower() != "database":
        raise ValueError(
            f"Unsupported notion:// path: {full_path}. "
            "Expected notion://database/<database_id>"
        )
    for page in client.query_database(parts[1], page_size=None):  # full drain
        yield page_to_atom(page, uri)


def ingest(uri: str, client: NotionClient | None = None) -> Iterator[dict[str, Any]]:
    """Dispatch by URI shape; client required for notion:// URIs."""
    kind = _uri_kind(uri)
    if kind == "notion":
        if client is None:
            raise ValueError("notion:// ingestion requires a NotionClient")
        yield from ingest_notion_uri(uri, client)
        return
    if kind == "file":
        raw = str(uri)
        if raw.lower().startswith("file://"):
            parsed = urlparse(raw)
            if parsed.netloc.lower() not in ("", "localhost"):
                raise ValueError(
                    f"Remote file:// host not supported: {parsed.netloc}"
                )
            path = Path(unquote(parsed.path))
        else:
            path = Path(raw)
        if not path.is_file():
            raise FileNotFoundError(f"No such file: {path}")
        yield from ingest_file(path)
        return
    raise ValueError(f"Cannot ingest: {uri}")
