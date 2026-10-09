"""Server tools + runtime facade — tool outputs against a fake client.

The FastMCP decorator is stubbed before importing the server module so
tests need no `mcp` install.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "server" / "notion_server.py"


def _load_server(token=""):
    """Import the server module with FastMCP stubbed and a token preset."""
    captured = {"tools": {}}

    class FakeMCP:
        def __init__(self, name):
            self.name = name

        def tool(self):
            def deco(fn):
                captured["tools"][fn.__name__] = fn
                return fn
            return deco

        def run(self):
            pass

    mcp_mod = types.ModuleType("mcp")
    server_mod = types.ModuleType("mcp.server")
    fastmcp_mod = types.ModuleType("mcp.server.fastmcp")
    fastmcp_mod.FastMCP = FakeMCP
    server_mod.fastmcp = fastmcp_mod
    mcp_mod.server = server_mod

    spec = importlib.util.spec_from_file_location("notion_server", SERVER_PATH)
    mod = importlib.util.module_from_spec(spec)
    old = {k: sys.modules.get(k) for k in ("mcp", "mcp.server", "mcp.server.fastmcp")}
    sys.modules.update(
        {"mcp": mcp_mod, "mcp.server": server_mod, "mcp.server.fastmcp": fastmcp_mod}
    )
    # The server does `from helpers.X import ...` meaning ITS plugin dir —
    # shadow conftest's host `helpers` stub for the duration of exec so the
    # plugin-dir package wins (it self-inserts on sys.path).
    helpers_keys = [k for k in sys.modules if k == "helpers" or k.startswith("helpers.")]
    saved_helpers = {k: sys.modules.pop(k) for k in helpers_keys}
    try:
        spec.loader.exec_module(mod)
    finally:
        for k in list(sys.modules):
            if k == "helpers" or k.startswith("helpers."):
                sys.modules.pop(k)
        sys.modules.update(saved_helpers)
        for k, v in old.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return mod, captured["tools"]


class FakeClient:
    def __init__(self):
        self.calls = []

    def search(self, q, filter_object=None, page_size=10):
        self.calls.append(("search", q, filter_object, page_size))
        return [{"id": "p1", "object": "page", "properties": {},
               "title": [{"text": {"content": "Doc"}}]}]

    def get_page(self, pid):
        return {"id": pid, "object": "page", "properties": {
            "Name": {"type": "title", "title": [{"text": {"content": "T"}}]},
            "Status": {"type": "select", "select": {"name": "Open"}},
        }}

    def get_block_children(self, bid, max_blocks=500):
        return [
            {"type": "heading_1", "heading_1": {"rich_text": [{"text": {"content": "Title"}}]}},
            {"type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "Body"}}]}},
        ]

    def query_database(self, dbid, filter_body=None, page_size=20):
        self.calls.append(("query", dbid, filter_body, page_size))
        return [{"id": "r1", "object": "page", "properties": {}}]


def _with_client(mod, client):
    mod._client = client
    return mod


def test_server_registers_expected_tools():
    mod, tools = _load_server()
    assert set(tools) == {
        "notion_search", "notion_get_page",
        "notion_get_page_content", "notion_query_database",
    }


def test_search_returns_summaries():
    mod, tools = _load_server()
    _with_client(mod, FakeClient())
    out = json.loads(tools["notion_search"]("docs"))
    assert out["count"] == 1
    assert out["results"][0]["id"] == "p1"


def test_get_page_compacts_properties():
    mod, tools = _load_server()
    _with_client(mod, FakeClient())
    out = json.loads(tools["notion_get_page"]("p1"))
    assert out["properties"]["Name"] == "T"
    assert out["properties"]["Status"] == "Open"


def test_page_content_flattens_blocks():
    mod, tools = _load_server()
    _with_client(mod, FakeClient())
    out = tools["notion_get_page_content"]("p1")
    assert out == "# Title\nBody"


def test_query_database_filter_validation():
    mod, tools = _load_server()
    client = _with_client(mod, FakeClient())._client
    out = tools["notion_query_database"]("db", filter_json="{bad")
    assert out.startswith("error: filter_json")
    out = tools["notion_query_database"]("db", filter_json="[1]")
    assert "must decode to an object" in out
    out = json.loads(tools["notion_query_database"]("db", filter_json='{"a":1}'))
    assert out["count"] == 1
    assert client.calls[-1][2] == {"a": 1}


def test_missing_token_errors_call_not_handshake(monkeypatch, tmp_path):
    mod, tools = _load_server()
    mod._client = None
    monkeypatch.setattr(mod, "resolve_token", lambda *a, **kw: "")
    out = tools["notion_search"]("x")
    assert out.startswith("error:")
    assert "token not configured" in out


def test_runtime_status_shape(enabled_cfg):
    from usr.plugins.notion.helpers import runtime

    runtime.configure(enabled_cfg)
    st = runtime.status()
    assert st["enabled"] is True and st["configured"] is True
    assert st["secret_name"] == "NOTION_TOKEN"
    # no token VALUE may appear — only names/flags
    for key in ("token_present", "mcp_registered", "server_name"):
        assert key in st


def test_runtime_disabled_is_inert():
    from usr.plugins.notion.helpers import runtime

    runtime.configure({"enabled": False})
    st = runtime.status()
    assert st["enabled"] is False
    assert runtime.is_active() is False


def test_configure_registers_mcp(enabled_cfg, settings_state):
    from usr.plugins.notion.helpers import runtime, mcp_register

    runtime.configure(enabled_cfg)
    data = json.loads(settings_state.get("mcp_servers", "{}"))
    assert mcp_register.SERVER_NAME in data.get("mcpServers", {})


def test_configure_disabled_no_register(settings_state):
    from usr.plugins.notion.helpers import runtime, mcp_register

    runtime.configure({"enabled": False, "auto_register_mcp": True})
    assert mcp_register.SERVER_NAME not in settings_state.get("mcp_servers", "")
