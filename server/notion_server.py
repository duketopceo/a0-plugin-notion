"""a0-plugin-notion — bundled stdio MCP server.

Spawned by a0's MCP layer as:
``<sys.executable> usr/plugins/notion/server/notion_server.py``

Read-only by design: search + page metadata + page content + database
query. No write tools exist — a misconfigured or compromised session can
only read what the integration already can.

Token: resolved inside this process (env → usr/secrets.env) — see
``helpers/secrets_env.py``. The ``mcp_servers`` entry carries no secrets.

Standalone use is supported too::

    NOTION_TOKEN=ntn_... python server/notion_server.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# The server runs inside the a0 venv (sys.executable in the mcp entry) so
# `mcp` is guaranteed importable; plugin helpers resolve relative to this
# file regardless of cwd.
_PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PLUGIN_DIR))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - only outside the a0 venv
    sys.stderr.write(
        "a0-plugin-notion: the 'mcp' package is required (it ships with "
        "Agent Zero). Install it or run inside the a0 runtime.\n"
    )
    raise

from helpers.config import get_config  # noqa: E402
from helpers.notion_client import NotionClient, NotionError  # noqa: E402
from helpers.notion_fmt import (  # noqa: E402
    blocks_to_text,
    page_detail,
    results_payload,
)
from helpers.secrets_env import a0_root_from, resolve_token  # noqa: E402

# get_config({}) applies the NOTION_* env overrides with coercion/clamps —
# the same NotionConfig the host side uses (helpers.plugins is absent in
# this namespace, so the host lookup silently no-ops to env+defaults).
CFG = get_config({})

mcp = FastMCP("a0-notion")

_client: NotionClient | None = None


def _get_client() -> NotionClient:
    """Lazily build the client so a missing token only fails the call,
    not the whole MCP handshake (a0 would otherwise show a dead server)."""
    global _client
    if _client is None:
        token = resolve_token(CFG.secret_name, a0_root=a0_root_from(__file__))
        if not token:
            raise NotionError(
                f"Notion token not configured — add '{CFG.secret_name}' to the a0 "
                "secrets vault (usr/secrets.env) or set it in the environment."
            )
        _client = NotionClient(
            token, api_version=CFG.api_version, timeout=CFG.http_timeout_s
        )
    return _client


def _err(exc: Exception) -> str:
    """Tool-level errors must be helpful, never leak the token."""
    return f"error: {exc}"


def page_content_text(client: NotionClient, page_id: str, max_blocks: int) -> str:
    """Fetch + flatten a page's block tree to readable text."""
    return blocks_to_text(
        client.get_block_children(page_id, max_blocks=max_blocks)
    )


# ------------------------------- tools ------------------------------------


@mcp.tool()
def notion_search(query: str, filter_object: str = "", page_size: int = 10) -> str:
    """Search the Notion workspace for pages/databases.

    query:        free-text search (empty string lists everything visible).
    filter_object: "page" or "database" to narrow; anything else = both.
    page_size:    results cap (server-side max applies).
    """
    try:
        results = _get_client().search(
            query, filter_object=filter_object or None,
            page_size=max(1, min(page_size, CFG.max_search_results)),
        )
        return json.dumps(results_payload(results), ensure_ascii=False, indent=2)
    except Exception as exc:
        return _err(exc)


@mcp.tool()
def notion_get_page(page_id: str) -> str:
    """Fetch a Notion page's metadata: title, url, parent, properties."""
    try:
        return json.dumps(
            page_detail(_get_client().get_page(page_id)),
            ensure_ascii=False, indent=2,
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool()
def notion_get_page_content(page_id: str, max_blocks: int = 0) -> str:
    """Read a page's content as flattened text (headings, lists, code,
    todos, quotes). One fetch level: nested content inside tables,
    toggles, and child_page / child_database blocks appears as [type]
    stubs to open with their own ids."""
    try:
        cap = max(1, min(max_blocks or CFG.max_page_blocks, CFG.max_page_blocks))
        return page_content_text(_get_client(), page_id, cap) or "(empty page)"
    except Exception as exc:
        return _err(exc)


@mcp.tool()
def notion_query_database(
    database_id: str, filter_json: str = "", page_size: int = 20
) -> str:
    """Query a Notion database; rows returned as page summaries.

    filter_json: optional Notion filter object as JSON (e.g.
      {"property":"Status","select":{"equals":"Done"}}).
    """
    try:
        filt = None
        if filter_json.strip():
            try:
                filt = json.loads(filter_json)
            except json.JSONDecodeError as exc:
                return f"error: filter_json is not valid JSON: {exc}"
            if not isinstance(filt, dict):
                return "error: filter_json must decode to an object"
        rows = _get_client().query_database(
            database_id, filter_body=filt,
            page_size=max(1, min(page_size, CFG.max_search_results)),
        )
        return json.dumps(results_payload(rows), ensure_ascii=False, indent=2)
    except Exception as exc:
        return _err(exc)


if __name__ == "__main__":
    mcp.run()
