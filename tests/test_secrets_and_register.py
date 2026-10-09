"""secrets_env + mcp_register — the token path and settings mutation."""

from __future__ import annotations

import json

from usr.plugins.notion.helpers import mcp_register, secrets_env


def test_parse_env_file():
    text = """# comment
NOTION_TOKEN=ntn_abc
export OTHER="quoted value"
SINGLE='sq'
EMPTY=
malformed line
"""
    out = secrets_env.parse_env_file(text)
    assert out["NOTION_TOKEN"] == "ntn_abc"
    assert out["OTHER"] == "quoted value"
    assert out["SINGLE"] == "sq"
    assert out["EMPTY"] == ""
    assert "malformed line" not in out


def test_resolve_token_env_wins(tmp_path):
    root = tmp_path / "a0"
    (root / "usr" / "plugins").mkdir(parents=True)
    (root / "usr" / "secrets.env").write_text("NOTION_TOKEN=vault-tok\n")
    tok = secrets_env.resolve_token(
        "NOTION_TOKEN", a0_root=root, environ={"NOTION_TOKEN": "env-tok"}
    )
    assert tok == "env-tok"


def test_resolve_token_vault_fallback(tmp_path):
    root = tmp_path / "a0"
    (root / "usr" / "plugins").mkdir(parents=True)
    (root / "usr" / "secrets.env").write_text("NOTION_TOKEN=vault-tok\n")
    assert secrets_env.resolve_token("NOTION_TOKEN", a0_root=root, environ={}) == "vault-tok"


def test_resolve_token_missing_everything(tmp_path):
    root = tmp_path / "a0"
    (root / "usr" / "plugins").mkdir(parents=True)
    assert secrets_env.resolve_token("NOTION_TOKEN", a0_root=root, environ={}) == ""


def test_a0_root_from_install_layout(tmp_path):
    root = tmp_path / "a0"
    nested = root / "usr" / "plugins" / "notion" / "server"
    nested.mkdir(parents=True)
    f = nested / "notion_server.py"
    f.write_text("# server")
    assert secrets_env.a0_root_from(f) == root


def test_a0_root_from_non_layout(tmp_path):
    f = tmp_path / "random" / "script.py"
    f.parent.mkdir()
    f.write_text("x")
    assert secrets_env.a0_root_from(f) is None  # not under usr/plugins → / would match bare usr — must NOT


def test_register_merges_into_existing_settings(settings_state):
    settings_state["mcp_servers"] = json.dumps(
        {"mcpServers": {"other": {"type": "stdio", "command": "x"}}}
    )
    assert mcp_register.register() is True
    data = json.loads(settings_state["mcp_servers"])
    assert "other" in data["mcpServers"]  # preserved
    entry = data["mcpServers"][mcp_register.SERVER_NAME]
    assert entry["type"] == "stdio"
    assert entry["args"][0].endswith("notion_server.py")
    # env carries only non-secret NOTION_* config — the token itself never
    # lands in settings.json (it's resolved inside the spawned process)
    assert "NOTION_TOKEN" not in json.dumps(entry)
    assert set(entry.get("env", {})) <= {
        "NOTION_SECRET_NAME", "NOTION_API_VERSION", "NOTION_HTTP_TIMEOUT_S",
        "NOTION_MAX_SEARCH_RESULTS", "NOTION_MAX_PAGE_BLOCKS",
    }
    assert mcp_register.register() is False  # idempotent


def test_register_propagates_non_secret_config(settings_state):
    """Plugin config must reach the spawned server via the entry env —
    the safe-listed child env makes it the only channel. Token: never."""
    from usr.plugins.notion.helpers.config import NotionConfig

    cfg = NotionConfig(secret_name="MY_NOTION_KEY", api_version="2025-01-01",
                       http_timeout_s=45.0, max_search_results=10,
                       max_page_blocks=100)
    assert mcp_register.register(cfg) is True
    entry = json.loads(settings_state["mcp_servers"])["mcpServers"][
        mcp_register.SERVER_NAME]
    env = entry["env"]
    assert env["NOTION_SECRET_NAME"] == "MY_NOTION_KEY"
    assert env["NOTION_HTTP_TIMEOUT_S"] == "45.0"
    assert "NOTION_TOKEN" not in json.dumps(entry)
    # a different cfg → re-register (not idempotent on stale entries)
    cfg2 = NotionConfig(secret_name="OTHER_KEY")
    assert mcp_register.register(cfg2) is True
    env2 = json.loads(settings_state["mcp_servers"])["mcpServers"][
        mcp_register.SERVER_NAME]["env"]
    assert env2["NOTION_SECRET_NAME"] == "OTHER_KEY"


def test_register_on_malformed_settings_rebuilds(settings_state):
    settings_state["mcp_servers"] = "{not json"
    assert mcp_register.register() is True
    data = json.loads(settings_state["mcp_servers"])
    assert mcp_register.SERVER_NAME in data["mcpServers"]


def test_unregister_removes_only_ours(settings_state):
    settings_state["mcp_servers"] = json.dumps(
        {"mcpServers": {
            "other": {"type": "stdio", "command": "x"},
            mcp_register.SERVER_NAME: mcp_register.build_entry(),
        }}
    )
    assert mcp_register.unregister() is True
    data = json.loads(settings_state["mcp_servers"])
    assert "other" in data["mcpServers"]
    assert mcp_register.SERVER_NAME not in data["mcpServers"]
    assert mcp_register.unregister() is False
