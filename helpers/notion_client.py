"""Minimal Notion REST client — stdlib only (urllib).

Port of the fetch half of Khan's ``connectors/notion.py`` with the
additions the MCP tools need (search + block children). Reads never
mutate; the plugin's contract is read-only by design — no write tools
are exposed, so a leaked token can only read what the integration can
already see.

The client is deliberately transport-tiny: one ``urlopen`` seam so
tests can fake the whole API without a network.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from urllib.parse import quote
from typing import Any, Iterator

NOTION_API_ROOT = "https://api.notion.com/v1"
DEFAULT_API_VERSION = "2022-06-28"  # stable dated API (same as Khan)


class NotionError(RuntimeError):
    """API failure with a safe message — never echoes the token."""


def _clean_id(raw: str) -> str:
    """Notion accepts ids with or without dashes; normalize to dashed.
    Tolerates a pasted URL — the id is always the trailing 32-hex token
    of the last path segment (``…/My-Page-<id32>``)."""
    s = str(raw or "").strip()
    s = s.split("?")[0].split("#")[0].rstrip("/")
    if "/" in s:
        s = s.rsplit("/", 1)[-1]
    compact = s.replace("-", "")
    m = re.search(r"([0-9a-fA-F]{32})$", compact)
    if m:
        c = m.group(1).lower()
        return f"{c[:8]}-{c[8:12]}-{c[12:16]}-{c[16:20]}-{c[20:]}"
    return s


class NotionClient:
    """Read-only Notion REST client.

    Parameters
    ----------
    token:    Notion integration token (``ntn_…``/``secret_…``).
    api_version: ``Notion-Version`` header.
    timeout:  per-request seconds.
    opener:   urlopen replacement — the single test seam.
    """

    def __init__(
        self,
        token: str,
        *,
        api_version: str = DEFAULT_API_VERSION,
        timeout: float = 30.0,
        opener=None,
    ) -> None:
        if not token:
            raise NotionError("Notion token is empty")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": api_version,
            "Content-Type": "application/json",
        }
        self._timeout = timeout
        self._opener = opener or urllib.request.urlopen

    # -- transport -----------------------------------------------------------

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            f"{NOTION_API_ROOT}{path}", data=data, headers=self._headers, method=method
        )
        try:
            with self._opener(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read(8192).decode("utf-8", errors="replace")[:300]
            except Exception:
                detail = ""
            code = exc.code
            raise NotionError(
                f"Notion API {method} {path} failed (HTTP {code}): {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise NotionError(f"Notion API unreachable: {exc.reason}") from exc
        if not isinstance(payload, dict):
            raise NotionError("Unexpected Notion API response shape")
        return payload

    def _paginate(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        limit: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield result objects across cursors. ``limit`` bounds TOTAL
        results — Notion's page_size is per-request; without a total cap a
        search could walk every page in the workspace."""
        payload: dict[str, Any] = dict(body or {})
        seen = 0
        cursor: str | None = None
        while True:
            if method == "GET":
                # GET pagination rides the query string, not the body.
                sep = "&" if "?" in path else "?"
                p = (
                    f"{path}{sep}start_cursor={quote(str(cursor), safe='')}"
                    if cursor else path
                )
                page = self._request(method, p, None)
            else:
                page = self._request(method, path, payload)
            for item in page.get("results") or []:
                if not isinstance(item, dict):
                    continue
                yield item
                seen += 1
                if limit is not None and seen >= limit:
                    return
            next_cursor = page.get("next_cursor")
            if (
                not page.get("has_more")
                or not next_cursor
                or next_cursor == cursor  # same-cursor guard: no livelock
            ):
                return
            cursor = next_cursor
            payload = dict(payload, start_cursor=cursor)

    # -- API surface ----------------------------------------------------------

    def search(
        self,
        query: str = "",
        *,
        filter_object: str | None = None,
        page_size: int = 10,
    ) -> list[dict[str, Any]]:
        """POST /search — pages and/or databases matching *query*."""
        cap = max(1, min(int(page_size), 100))
        body: dict[str, Any] = {"query": query, "page_size": cap}
        if filter_object in ("page", "database"):
            body["filter"] = {"value": filter_object, "property": "object"}
        return list(self._paginate("POST", "/search", body, limit=cap))

    def get_page(self, page_id: str) -> dict[str, Any]:
        return self._request("GET", f"/pages/{_clean_id(page_id)}")

    def get_block_children(
        self, block_id: str, *, max_blocks: int = 500
    ) -> list[dict[str, Any]]:
        """GET /blocks/<id>/children; *max_blocks* bounds TOTAL blocks
        (<=0 means "server default" upstream — callers clamp first)."""
        return list(
            self._paginate(
                "GET", f"/blocks/{_clean_id(block_id)}/children", limit=max_blocks
            )
        )

    def query_database(
        self,
        database_id: str,
        *,
        filter_body: dict[str, Any] | None = None,
        page_size: int | None = 20,
    ) -> list[dict[str, Any]]:
        """POST /databases/<id>/query. ``page_size`` bounds TOTAL rows;
        pass ``None`` for a full-database drain (ingestion path only)."""
        if page_size is None:
            body: dict[str, Any] = {"page_size": 100}
            limit = None
        else:
            limit = max(1, min(int(page_size), 100))
            body = {"page_size": limit}
        if filter_body:
            body["filter"] = filter_body
        return list(
            self._paginate(
                "POST", f"/databases/{_clean_id(database_id)}/query", body, limit=limit
            )
        )
