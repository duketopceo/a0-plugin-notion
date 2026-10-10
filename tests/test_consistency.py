"""Structural consistency — host-contract guards that don't need a0.

Sibling plugins carry a file like this because these invariants are what
break silently on the real host: a manifest name that isn't the dir name,
a yaml key no config field consumes, an ApiHandler file with two classes
(the host loader takes the FIRST subclass), an extension that returns an
awaitable into a sync sweep.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

from conftest import run
from usr.plugins.notion.helpers.config import NotionConfig


def _load(name: str, path: Path):
    """Exec a plugin module by file path (api/, hooks.py, extensions/
    live outside the helpers package)."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# -- manifest / config -------------------------------------------------------


def test_plugin_name_is_install_dir_safe():
    """plugin.yaml name must be a python identifier — it IS the import
    path segment (usr.plugins.<name>)."""
    meta = yaml.safe_load((ROOT / "plugin.yaml").read_text())
    assert meta["name"] == "notion"
    assert meta["name"].isidentifier()


def test_default_config_matches_dataclass():
    """Every yaml key must land on a NotionConfig field (dead keys are
    invisible) AND every yaml default must equal the dataclass default —
    a host config.json REPLACES default_config.yaml (no merge), so drift
    here means operators see different defaults than the code."""
    yaml_cfg = yaml.safe_load((ROOT / "default_config.yaml").read_text())
    fields = NotionConfig.__dataclass_fields__
    assert set(yaml_cfg) <= set(fields), "yaml-only keys are dead config"
    probe = NotionConfig()
    for key, val in yaml_cfg.items():
        assert val == getattr(probe, key), f"{key}: yaml {val!r} != code {getattr(probe, key)!r}"


def test_plugin_yaml_has_no_secret_keys():
    """The manifest must not declare settings that would land a secret in
    settings.json."""
    meta = yaml.safe_load((ROOT / "plugin.yaml").read_text())
    blob = json.dumps(meta).lower()
    for bad in ("notion_token", "api_key", "secret_value", "password"):
        assert bad not in blob


# -- api handlers -------------------------------------------------------------


def test_one_api_handler_per_file():
    """a0's load_classes_from_file registers only the FIRST ApiHandler
    subclass per file — a stray second class silently never routes."""
    for f in (ROOT / "api").glob("*.py"):
        if f.name == "__init__.py":
            continue
        mod = _load(f"api.{f.stem}", f)
        handlers = [
            c for _, c in inspect.getmembers(mod, inspect.isclass)
            if issubclass(c, _api_handler_cls()) and c is not _api_handler_cls()
        ]
        assert len(handlers) == 1, f"{f.name}: {len(handlers)} ApiHandler subclasses"


def _api_handler_cls():
    import helpers.api

    return helpers.api.ApiHandler


def test_status_handler_process(settings_state):
    from usr.plugins.notion.helpers import runtime

    runtime.configure({"enabled": True, "auto_register_mcp": False})
    mod = _load("api.notion_status", ROOT / "api" / "notion_status.py")
    handler = mod.NotionStatus(app=None, thread_lock=None)
    out = run(handler.process({}, request=None))
    assert out["ok"] is True and out["enabled"] is True
    assert out["token_present"] is False
    assert out["server_name"] == "a0_notion"
    # session auth on by default — this is a user-facing diagnostic
    assert handler.requires_auth() is True
    assert handler.requires_csrf() is True
    assert "NOTION_TOKEN=ntn" not in json.dumps(out)  # never a value


# -- hooks + extension --------------------------------------------------------


def test_hooks_install_uninstall_roundtrip(settings_state):
    hooks = _load("usr.plugins.notion.hooks", ROOT / "hooks.py")
    hooks.install()  # never raises

    from usr.plugins.notion.helpers import mcp_register, runtime

    runtime.configure({"enabled": True})
    assert mcp_register.is_registered(settings_state["mcp_servers"])
    hooks.uninstall()
    assert mcp_register.SERVER_NAME not in json.loads(
        settings_state["mcp_servers"])["mcpServers"]
    hooks.uninstall()  # idempotent — second call must not raise


def test_startup_extension_is_sync_and_never_raises():
    """a0's startup sweep is synchronous and unguarded — an awaitable
    return or a raised exception would fail boot."""
    mod = _load(
        "ext.75_notion_init",
        ROOT / "extensions" / "python" / "startup_migration" / "_75_notion_init.py",
    )
    ext = mod.NotionInit(agent=None)
    assert not inspect.iscoroutinefunction(ext.execute)
    ext.execute()  # real path: calls runtime.configure(None) — no raise

    # failure inside configure must also be swallowed
    from usr.plugins.notion.helpers import runtime

    def boom(_cfg=None):
        raise RuntimeError("config blew up")

    orig = runtime.configure
    runtime.configure = boom
    try:
        ext.execute()  # must not propagate
    finally:
        runtime.configure = orig


def test_server_is_read_only():
    """The whole point: no write/capability tool may exist in server/.
    Structural guard — scans source, not just registered names."""
    src = (ROOT / "server" / "notion_server.py").read_text()
    for bad in ("create", "update", "delete", "patch", "post_page"):
        for line in src.splitlines():
            code = line.split("#")[0]
            if "def notion_" in code:
                assert bad not in code.split("def ")[1], f"write-ish tool: {line}"
    mod, tools = _load_server_for_tools()
    assert set(tools) == {
        "notion_search", "notion_get_page",
        "notion_get_page_content", "notion_query_database",
    }


def _load_server_for_tools():
    """Re-exec the server with FastMCP stubbed (mirrors
    test_server_and_runtime._load_server)."""
    import importlib.util as iu
    import types

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

    spec = iu.spec_from_file_location(
        "notion_server_consistency", ROOT / "server" / "notion_server.py")
    mod = iu.module_from_spec(spec)
    old = {k: sys.modules.get(k)
           for k in ("mcp", "mcp.server", "mcp.server.fastmcp")}
    sys.modules.update({"mcp": mcp_mod, "mcp.server": server_mod,
                        "mcp.server.fastmcp": fastmcp_mod})
    helpers_keys = [k for k in sys.modules
                    if k == "helpers" or k.startswith("helpers.")]
    saved = {k: sys.modules.pop(k) for k in helpers_keys}
    try:
        spec.loader.exec_module(mod)
    finally:
        plugin_dir = str(ROOT)
        if plugin_dir in sys.path:
            sys.path.remove(plugin_dir)
        for k in list(sys.modules):
            if k == "helpers" or k.startswith("helpers."):
                sys.modules.pop(k)
        sys.modules.update(saved)
        for k, v in old.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return mod, captured["tools"]
