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


def test_register_refuses_on_malformed_settings(settings_state):
    """A corrupt mcp_servers blob must NOT be 'rebuilt' — writing over it
    silently deletes every other server. Safe direction: don't touch."""
    settings_state["mcp_servers"] = "{not json"
    assert mcp_register.register() is False
    assert settings_state["mcp_servers"] == "{not json"  # untouched
    assert mcp_register.unregister() is False
    assert settings_state["mcp_servers"] == "{not json"


def test_register_on_absent_or_empty_settings_writes(settings_state):
    """Empty/absent mcp_servers is safe to initialize — distinct from
    the unparseable case."""
    for empty in ("", "{}", '{"mcpServers": {}}', '{"mcpServers": []}'):
        settings_state["mcp_servers"] = empty
        assert mcp_register.register() is True
        assert mcp_register.SERVER_NAME in json.loads(
            settings_state["mcp_servers"])["mcpServers"]


def test_register_preserves_user_owned_keys(settings_state):
    """A user who disables the server or trims tools via the MCP UI must
    not get that erased on the next startup re-register."""
    entry = mcp_register.build_entry()
    entry.update({"disabled": True, "disabled_tools": ["notion_search"],
                  "init_timeout": 99})
    settings_state["mcp_servers"] = json.dumps(
        {"mcpServers": {mcp_register.SERVER_NAME: entry}})
    assert mcp_register.register() is False  # identical incl. user keys
    # drift in OUR keys re-registers but keeps the user's
    entry["command"] = "/old/gone/python"
    settings_state["mcp_servers"] = json.dumps(
        {"mcpServers": {mcp_register.SERVER_NAME: entry}})
    assert mcp_register.register() is True
    new = json.loads(settings_state["mcp_servers"])["mcpServers"][
        mcp_register.SERVER_NAME]
    assert new["command"] != "/old/gone/python"  # repaired
    assert new["disabled"] is True
    assert new["disabled_tools"] == ["notion_search"]
    assert new["init_timeout"] == 99


def test_parse_config_folds_bare_single_server():
    """a0's normalize_config accepts {"name":…,"command":…} with no
    mcpServers key — it must survive our normalization, not vanish."""
    data = mcp_register._parse_config(
        '{"name": "solo", "command": "x", "type": "stdio"}')
    assert data["mcpServers"]["solo"]["command"] == "x"


def test_register_preserves_unrelated_settings(settings_state):
    """P0 regression: a naive set_settings({"mcp_servers": ...}) replaces
    the WHOLE settings object in real a0 — wiping every other key and
    deleting the secrets vault via the sensitive-write path. Registering
    must go through set_settings_delta."""
    settings_state.update({
        "chat_model": "gpt-x", "api_keys": "…", "mcp_servers": "",
        "secrets": "KEEPME",
    })
    mcp_register.register()
    assert settings_state["chat_model"] == "gpt-x"
    assert settings_state["api_keys"] == "…"
    assert settings_state["secrets"] == "KEEPME"


def test_parse_config_tolerates_non_dict_json():
    """a0 writes mcp_servers='[]' transiently; non-dict JSON must not
    crash the parser."""
    assert mcp_register._parse_config("[]")["mcpServers"] == {}
    assert mcp_register._parse_config('"x"')["mcpServers"] == {}
    assert mcp_register._parse_config("5")["mcpServers"] == {}
    assert mcp_register._parse_config(None)["mcpServers"] == {}


def test_parse_config_keeps_list_form_servers():
    """a0 accepts mcpServers as a LIST of named dicts — normalizing must
    keep them, not drop every other server."""
    raw = json.dumps({"mcpServers": [
        {"name": "other", "type": "stdio", "command": "x"},
        {"name": "", "type": "stdio"},          # nameless — dropped
        "not-a-dict",                            # malformed — dropped
    ]})
    data = mcp_register._parse_config(raw)
    assert set(data["mcpServers"]) == {"other"}


def test_unregister_removes_only_ours(settings_state):
    settings_state.update({
        "chat_model": "keep",
        "mcp_servers": json.dumps(
            {"mcpServers": {
                "other": {"type": "stdio", "command": "x"},
                mcp_register.SERVER_NAME: mcp_register.build_entry(),
            }}
        ),
    })
    assert mcp_register.unregister() is True
    data = json.loads(settings_state["mcp_servers"])
    assert "other" in data["mcpServers"]
    assert mcp_register.SERVER_NAME not in data["mcpServers"]
    assert settings_state["chat_model"] == "keep"


def test_vault_falls_back_to_dot_env(tmp_path):
    """a0's secret store covers usr/secrets.env AND usr/.env — a token
    in either must resolve."""
    (tmp_path / "usr" / "plugins").mkdir(parents=True)
    (tmp_path / "usr" / ".env").write_text("NOTION_TOKEN=from_dot_env")
    assert secrets_env.read_vault("NOTION_TOKEN", a0_root=tmp_path) == "from_dot_env"
    # secrets.env wins over .env when both exist
    (tmp_path / "usr" / "secrets.env").write_text("NOTION_TOKEN=from_secrets")
    assert secrets_env.read_vault("NOTION_TOKEN", a0_root=tmp_path) == "from_secrets"


def test_a0_root_detects_symlink_install(tmp_path):
    """usr/plugins/notion -> repo checkout: __file__ keeps the usr/plugins
    component; resolve() follows the link OUT and misses the a0 root —
    the vault silently goes unread."""
    a0 = tmp_path / "a0"
    (a0 / "usr" / "plugins").mkdir(parents=True)
    repo = tmp_path / "a0-plugin-notion"
    (repo / "helpers").mkdir(parents=True)
    (a0 / "usr" / "plugins" / "notion").symlink_to(repo)

    imported = (a0 / "usr" / "plugins" / "notion" / "helpers"
                / "secrets_env.py")
    assert secrets_env.a0_root_from(imported) == a0
