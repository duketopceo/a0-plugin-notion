"""Register the bundled stdio MCP server in ``settings["mcp_servers"]``.

a0 keeps MCP servers in the ``mcp_servers`` settings key — a JSON string
of shape ``{"mcpServers": {"<name>": {<MCPServerLocal fields>}}}`` — and
re-initializes ``MCPConfig`` on change. The plugin adds (idempotently)
and removes (on uninstall) its own entry while preserving every other
server. The entry carries NO secrets: the server resolves its token
inside the spawned process (see ``secrets_env.py``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SERVER_NAME = "a0_notion"
SERVER_ENTRYPOINT = "notion_server.py"


def server_relpath() -> str:
    """Absolute path to the bundled server script."""
    return str(Path(__file__).resolve().parent.parent / "server" / SERVER_ENTRYPOINT)


def build_entry() -> dict[str, Any]:
    """The mcp_servers entry for our stdio server — non-secret config
    only. `env` deliberately absent: a token here would sit plaintext in
    settings.json (MCP merges this dict verbatim into the spawn env)."""
    return {
        "name": SERVER_NAME,
        "description": "Notion read/search tools (a0-plugin-notion)",
        "type": "stdio",
        "command": sys.executable,
        "args": [server_relpath()],
    }


def _parse_config(raw: Any) -> dict[str, Any]:
    """Best-effort parse of the mcp_servers settings value. Anything
    malformed returns a fresh shape — a broken config must not wedge
    plugin startup (a0 already surfaces the parse error separately)."""
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(str(raw or ""))
        except (json.JSONDecodeError, TypeError):
            data = {}
    if not isinstance(data.get("mcpServers"), dict):
        data["mcpServers"] = {}
    return data


def is_registered(raw: Any) -> bool:
    return SERVER_NAME in _parse_config(raw)["mcpServers"]


def merged_config(raw: Any) -> str:
    """The mcp_servers JSON with our entry added/updated in place."""
    data = _parse_config(raw)
    data["mcpServers"][SERVER_NAME] = build_entry()
    return json.dumps(data, indent=2)


def without_server(raw: Any) -> str:
    """The mcp_servers JSON with our entry removed (others preserved)."""
    data = _parse_config(raw)
    data["mcpServers"].pop(SERVER_NAME, None)
    return json.dumps(data, indent=2)


def register() -> bool:
    """Write the entry into live settings if missing/stale. Lazy host
    import so this module never aborts a0's sweep."""
    from helpers import settings as host_settings

    current = host_settings.get_settings().get("mcp_servers", "")
    data = _parse_config(current)
    existing = data["mcpServers"].get(SERVER_NAME)
    if existing == build_entry():
        return False
    host_settings.set_settings({"mcp_servers": merged_config(current)})
    return True


def unregister() -> bool:
    """Remove the entry from live settings (hooks.py uninstall)."""
    from helpers import settings as host_settings

    current = host_settings.get_settings().get("mcp_servers", "")
    if not is_registered(current):
        return False
    host_settings.set_settings({"mcp_servers": without_server(current)})
    return True
