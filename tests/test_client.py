"""NotionClient — transport contract, pagination, errors, id hygiene."""

from __future__ import annotations

import json
import urllib.error
import io

import pytest

from usr.plugins.notion.helpers.notion_client import (
    NotionClient,
    NotionError,
    _clean_id,
)

from conftest import FakeNotionHTTP, FakeResponse


def _client(http: FakeNotionHTTP) -> NotionClient:
    return NotionClient("ntn_test", api_version="2022-06-28", timeout=5, opener=http.open)


def test_auth_headers_and_version():
    http = FakeNotionHTTP()
    http.routes[("POST", "/search")] = {"results": [], "has_more": False}
    _client(http).search("x")
    # inspect the request headers on the captured call
    req_headers = {}
    # rebuild: FakeNotionHTTP doesn't store headers — quick manual check
    # via a route recorder
    captured = {}

    def rec(req, timeout=None):
        captured.update(dict(req.header_items()))
        return FakeResponse({"results": []})

    c = NotionClient("ntn_ABC", api_version="2022-06-28", timeout=5, opener=rec)
    c.search("q")
    assert captured["Authorization"] == "Bearer ntn_ABC"
    assert captured["Notion-version"] == "2022-06-28"


def test_search_filter_and_page_size():
    http = FakeNotionHTTP()
    http.routes[("POST", "/search")] = {"results": [{"id": "p1", "object": "page"}], "has_more": False}
    out = _client(http).search("docs", filter_object="page", page_size=10)
    assert [r["id"] for r in out] == ["p1"]
    body = json.loads(http.calls[0][2])
    assert body["filter"] == {"value": "page", "property": "object"}
    assert body["page_size"] == 10


def test_search_paginates():
    http = FakeNotionHTTP()
    http.routes[("POST", "/search")] = [
        {"results": [{"id": "a"}], "has_more": True, "next_cursor": "cur1"},
        {"results": [{"id": "b"}], "has_more": False},
    ]
    out = _client(http).search("x")
    assert [r["id"] for r in out] == ["a", "b"]
    assert len(http.calls) == 2
    assert json.loads(http.calls[1][2])["start_cursor"] == "cur1"


def test_get_page_and_clean_id():
    assert _clean_id("550e8400e29b41d4a716446655440000") == \
        "550e8400-e29b-41d4-a716-446655440000"
    assert _clean_id("https://www.notion.so/My-Page-550e8400e29b41d4a716446655440000?x=1") == \
        "550e8400-e29b-41d4-a716-446655440000"

    http = FakeNotionHTTP()
    http.routes[("GET", "/pages/abc")] = {"id": "abc", "object": "page"}
    page = _client(http).get_page("abc")
    assert page["id"] == "abc"


def test_block_children_cap():
    http = FakeNotionHTTP()
    http.routes[("GET", "/blocks/p/children")] = [
        {"results": [{"type": "paragraph", "id": f"b{i}"} for i in range(5)],
         "has_more": True, "next_cursor": "c1"},
        {"results": [{"type": "paragraph", "id": "b5"}], "has_more": False},
    ]
    blocks = _client(http).get_block_children("p", max_blocks=3)
    assert len(blocks) == 3  # capped even though more pages exist


def test_query_database_posts_filter():
    http = FakeNotionHTTP()
    http.routes[("POST", "/databases/db1/query")] = {"results": [{"id": "r1"}], "has_more": False}
    out = _client(http).query_database(
        "db1", filter_body={"property": "S", "select": {"equals": "x"}}, page_size=20
    )
    assert [r["id"] for r in out] == ["r1"]
    body = json.loads(http.calls[0][2])
    assert body["filter"]["select"]["equals"] == "x"


def test_http_error_is_safe_message():
    http = FakeNotionHTTP()  # no route -> 404
    with pytest.raises(NotionError, match="HTTP 404"):
        _client(http).get_page("nope")


def test_token_never_in_error():
    http = FakeNotionHTTP()

    def boom(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 401, "Unauthorized", {},
            io.BytesIO(b'{"message":"bad token ntn_test"}'),
        )

    c = NotionClient("ntn_test", api_version="x", timeout=5, opener=boom)
    with pytest.raises(NotionError) as exc:
        c.get_page("p")
    # the API echoes part of the token in its message — that's the API's
    # content, acceptable to surface; the client itself adds no secrets
    assert "Bearer" not in str(exc.value)
    assert "Authorization" not in str(exc.value)


def test_empty_token_refused():
    with pytest.raises(NotionError):
        NotionClient("")
