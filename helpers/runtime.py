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
            # register() is write-free when the entry is already correct,
            # so call unconditionally — it also repairs a stale/dead entry
            # (moved plugin dir, rebuilt venv, config drift).
            try:
                if mcp_register.register(_cfg):
                    log.info("notion: registered %s in mcp_servers", mcp_register.SERVER_NAME)
            except Exception:
                log.exception("notion: mcp registration failed (server can still be added manually)")
        elif not _cfg.enabled and _cfg.auto_register_mcp:
            # disabling must tear OUR entry down — otherwise the spawned
            # server and its tools stay live behind a "disabled" plugin.
            # (Only in auto-manage mode: operators who hand-manage the
            # entry via auto_register_mcp:false keep it.)
            try:
                from helpers import settings as host_settings

                if mcp_register.is_registered(
                    host_settings.get_settings().get("mcp_servers", "")
                ):
                    mcp_register.unregister()
                    log.info("notion: unregistered %s (plugin disabled)", mcp_register.SERVER_NAME)
            except Exception:
                log.exception("notion: unregister on disable failed")
    return _cfg


def is_active() -> bool:
    return bool(_cfg and _cfg.enabled)


def cfg() -> NotionConfig | None:
    return _cfg


def token_configured() -> bool:
    """True when the spawned server would find a token. The child's env
    is a safe-list + the entry's env dict — a host-process NOTION_TOKEN
    never reaches it, so the honest signal is the vault file alone.
    Reads are cheap; no caching so vault edits show on next status."""
    if _cfg is None:
        return False
    return bool(secrets_env.read_vault(_cfg.secret_name))


def status() -> dict[str, Any]:
    """Safe-to-render status: same key set regardless of configuration —
    consumers never need presence checks. No token values, no paths."""
    if _cfg is None:
        return {
            "enabled": False, "configured": False,
            "secret_name": "NOTION_TOKEN", "token_present": False,
            "mcp_registered": False, "server_name": mcp_register.SERVER_NAME,
        }
    registered = False
    token = False
    try:
        from helpers import settings as host_settings

        registered = mcp_register.is_registered(
            host_settings.get_settings().get("mcp_servers", "")
        )
    except Exception:
        pass
    try:
        token = token_configured()
    except Exception:
        pass
    return {
        "enabled": _cfg.enabled,
        "configured": True,
        "config": _cfg.to_dict(),
        "secret_name": _cfg.secret_name,
        "token_present": token,
        "mcp_registered": registered,
        "server_name": mcp_register.SERVER_NAME,
    }


def _reset() -> None:
    """Test seam — drop all configured state."""
    global _cfg
    with _lock:
        _cfg = None
