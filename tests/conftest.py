"""Make ``usr.plugins.notion.*`` imports resolvable under pytest — the
same qualified path a0 uses — and stub the framework modules the plugin
touches (helpers.api / helpers.extension / helpers.plugins /
helpers.settings) so everything runs standalone, offline.

Stubs model a0's real contracts:

- helpers.settings: one in-memory dict; set_settings merges and returns.
- helpers.plugins: get_plugin_config returns the plugin's config dict.
- helpers.api: ApiHandler base; helpers.extension: Extension base.
- The `mcp` SDK is NOT stubbed — server tests import the server module
  with a fake FastMCP injected, or skip when `mcp` isn't installed.
"""

from __future__ import annotations

import io
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _pkg(name, path=None):
    mod = types.ModuleType(name)
    mod.__path__ = [str(path)] if path else []
    return mod


_usr = _pkg("usr")
_plugins = _pkg("usr.plugins")
_notion = _pkg("usr.plugins.notion", ROOT)
_usr.plugins = _plugins
_plugins.notion = _notion
sys.modules.setdefault("usr", _usr)
sys.modules.setdefault("usr.plugins", _plugins)
sys.modules["usr.plugins.notion"] = _notion


# --- minimal a0 framework stubs ---------------------------------------------


class Extension:
    """Matches host helpers/extension.py: agent is required, kwargs kept."""

    def __init__(self, agent, **kwargs):
        self.agent = agent
        self.kwargs = kwargs


class ApiHandler:
    """Matches host helpers/api.py: __init__(app, thread_lock) is
    required — handlers that forget it die at route registration."""

    def __init__(self, app, thread_lock):
        self.app = app
        self.thread_lock = thread_lock

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def requires_csrf(cls) -> bool:
        return cls.requires_auth()  # host ties CSRF to auth, not a blanket True

    @classmethod
    def requires_api_key(cls) -> bool:
        return False

    @classmethod
    def requires_loopback(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list:
        return ["POST"]

    async def process(self, input, request):
        raise NotImplementedError


import asyncio as _asyncio


def run(coro):
    return _asyncio.run(coro)


_ext_mod = types.ModuleType("helpers.extension")
_ext_mod.Extension = Extension

_api_mod = types.ModuleType("helpers.api")
_api_mod.ApiHandler = ApiHandler

_settings_state: dict = {}


def _get_settings():
    return dict(_settings_state)


def _set_settings(new):
    """Models the REAL host semantics: set_settings is a whole-settings
    replace (normalize_settings drops unknown keys + fills defaults).
    Plugins must never call it with a partial dict — set_settings_delta
    is the merge API."""
    _settings_state.clear()
    _settings_state.update(new or {})
    return dict(_settings_state)


def _set_settings_delta(delta):
    _settings_state.update(delta or {})
    return dict(_settings_state)


_settings_mod = types.ModuleType("helpers.settings")
_settings_mod.get_settings = _get_settings
_settings_mod.set_settings = _set_settings
_settings_mod.set_settings_delta = _set_settings_delta
_settings_mod._state = _settings_state

_plugin_config: dict = {}


def _get_plugin_config(name, *a, **kw):
    return dict(_plugin_config) if name == "notion" else {}


_plugins_mod = types.ModuleType("helpers.plugins")
_plugins_mod.get_plugin_config = _get_plugin_config

_helpers = _pkg("helpers")
_helpers.extension = _ext_mod
_helpers.api = _api_mod
_helpers.settings = _settings_mod
_helpers.plugins = _plugins_mod
sys.modules["helpers"] = _helpers
sys.modules["helpers.extension"] = _ext_mod
sys.modules["helpers.api"] = _api_mod
sys.modules["helpers.settings"] = _settings_mod
sys.modules["helpers.plugins"] = _plugins_mod


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Ambient NOTION_* env vars must never reach tests — _merge_env
    applies env over explicit config."""
    from usr.plugins.notion.helpers.config import _ENV_MAP

    for var in [env for env, _ in _ENV_MAP.values()] + ["NOTION_TOKEN"]:
        monkeypatch.delenv(var, raising=False)
    _settings_state.clear()
    _plugin_config.clear()
    from usr.plugins.notion.helpers import runtime

    runtime._reset()
    yield
    _settings_state.clear()
    _plugin_config.clear()
    runtime._reset()


@pytest.fixture()
def settings_state():
    return _settings_state


@pytest.fixture()
def plugin_config():
    return _plugin_config


@pytest.fixture()
def enabled_cfg(tmp_path):
    return {
        "enabled": True,
        "secret_name": "NOTION_TOKEN",
        "api_version": "2022-06-28",
        "http_timeout_s": 5,
        "max_search_results": 25,
        "max_page_blocks": 500,
        "auto_register_mcp": True,
    }


class FakeResponse:
    """urllib response stand-in: context manager + read()."""

    def __init__(self, payload: dict):
        import io
        import json

        self._buf = io.BytesIO(json.dumps(payload).encode())
        self.status = 200

    def read(self, *a):
        return self._buf.read(*a)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeNotionHTTP:
    """urlopen replacement routing {(method, path): dict|list[dict]} —
    a list yields successive pages (pagination tests)."""

    def __init__(self):
        self.routes: dict[tuple[str, str], object] = {}
        self.calls: list[tuple[str, str, bytes | None]] = []

    def open(self, req, timeout=None):
        path = req.full_url.split("api.notion.com")[-1].split("/v1", 1)[-1].split("?")[0]
        method = req.get_method()
        self.calls.append((method, path, req.data))
        for (m, suffix), payload in self.routes.items():
            if m == method and (path == suffix or path.endswith(suffix)):
                if isinstance(payload, list):
                    payload = payload.pop(0)
                return FakeResponse(payload)
        import urllib.error

        raise urllib.error.HTTPError(
            req.full_url, 404, "Not Found", {}, io.BytesIO(b'{"message":"missing"}')
        )
