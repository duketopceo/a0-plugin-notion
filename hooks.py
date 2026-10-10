"""a0-plugin-notion lifecycle hooks. Never raise — a0 calls these on
install/uninstall/update paths and a failure must not wedge the host."""

from __future__ import annotations

import logging

log = logging.getLogger("a0.notion")


def install(**kwargs):
    log.info("a0-plugin-notion installed")


def uninstall(**kwargs):
    """Remove our mcp_servers entry so the server stops spawning; the
    secrets vault is untouched (token stays where the user put it)."""
    try:
        from usr.plugins.notion.helpers import mcp_register

        if mcp_register.unregister():
            log.info("notion: removed %s from mcp_servers", mcp_register.SERVER_NAME)
    except Exception:
        log.exception("notion: uninstall cleanup failed")
    try:
        from usr.plugins.notion.helpers import runtime

        runtime._reset()
    except Exception:
        pass
