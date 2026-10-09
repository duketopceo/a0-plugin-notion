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
    assert "env" not in entry  # no secrets in settings.json — token resolves in-process
    assert mcp_register.register() is False  # idempotent


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
