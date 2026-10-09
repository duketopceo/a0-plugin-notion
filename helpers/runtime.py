"""Configured-runtime facade — configure/status/token for handlers and
the startup extension. Mirrors the sibling plugins' shape: module-level
singleton config, never raises into a0's sweep."""

from __future__ import annotations

import logging
import threading
from typing import Any

from usr.plugins.notion.helpers import LOG_NAME, mcp_register, secrets_env
from usr.plugins.notion.helpers.config import NotionConfig, get_config

log = logging.getLogger(LOG_NAME)

_lock = threading.Lock()
_cfg: NotionConfig | None = None


def configure(config: dict[str, Any] | NotionConfig | None = None) -> NotionConfig:
    """(Re)configure the plugin. Serialized — a reconfigure can never race
    a partial state into readers."""
    global _cfg
    with _lock:
        _cfg = config if isinstance(config, NotionConfig) else get_config(config)
        if _cfg.enabled and _cfg.auto_register_mcp:
            try:
                if mcp_register.register(_cfg):
                    log.info("notion: registered %s in mcp_servers", mcp_register.SERVER_NAME)
            except Exception:
                log.exception("notion: mcp registration failed (server can still be added manually)")
    return _cfg


def is_active() -> bool:
    return bool(_cfg and _cfg.enabled)


def cfg() -> NotionConfig | None:
    return _cfg


def token_configured() -> bool:
    """True when the server would find a token at spawn — env or vault.
    Reads are cheap; no caching so vault edits take effect on next spawn."""
    if _cfg is None:
        return False
    return bool(secrets_env.resolve_token(_cfg.secret_name))


def status() -> dict[str, Any]:
    """Safe-to-render status: no token values, no absolute paths."""
    if _cfg is None:
        return {"enabled": False, "configured": False}
    registered = False
    try:
        from helpers import settings as host_settings

        registered = mcp_register.is_registered(
            host_settings.get_settings().get("mcp_servers", "")
        )
    except Exception:
        pass
    return {
        "enabled": _cfg.enabled,
        "configured": True,
        "config": _cfg.to_dict(),
        "secret_name": _cfg.secret_name,
        "token_present": token_configured(),
        "mcp_registered": registered,
        "server_name": mcp_register.SERVER_NAME,
    }


def _reset() -> None:
    """Test seam — drop all configured state."""
    global _cfg
    with _lock:
        _cfg = None
