"""Token resolution — env var → a0 secrets vault, never settings.json.

a0's MCP stdio spawn uses a safe-listed environment plus the static
``env`` dict in the ``mcp_servers`` entry — so a token can neither ride
``os.environ`` nor sit in settings.json. Instead the spawned server
resolves it *inside its own process*:

1. ``NOTION_TOKEN`` (or the configured ``secret_name``) in the process
   environment — covers standalone runs and any env the operator wires.
2. ``usr/secrets.env`` — a0's secrets vault is a plain dotenv file;
   ``§§secret(NAME)`` in tools resolves against the same store. The
   server self-locates the a0 root from ``__file__`` by walking ancestors
   for a ``usr/plugins`` dir and parses the file — no host imports
   needed inside the subprocess.
"""

from __future__ import annotations

import os
from pathlib import Path


def parse_env_file(text: str) -> dict[str, str]:
    """Minimal dotenv parse — KEY=VALUE, comments, single/double quotes,
    ``export`` prefix tolerated. Deliberately independent of a0 helpers so
    the MCP subprocess needs nothing but stdlib."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def a0_root_from(path: str | Path) -> Path | None:
    """Locate the a0 root from a file inside ``usr/plugins/<p>/…``.
    Returns None when the layout doesn't match (e.g. repo checkout in
    tests). Only ``usr/plugins`` counts — a bare ``usr/`` dir would match
    the filesystem root."""
    p = Path(path).resolve()
    for parent in p.parents:
        if (parent / "usr" / "plugins").is_dir():
            return parent
    return None


def read_vault(secret_name: str, *, a0_root: Path | None = None) -> str:
    """Read *secret_name* from ``usr/secrets.env`` under *a0_root* (or the
    self-located root). Empty string when absent — never raises."""
    root = a0_root or a0_root_from(__file__)
    if root is None:
        return ""
    try:
        text = (root / "usr" / "secrets.env").read_text(encoding="utf-8")
    except OSError:
        return ""
    return parse_env_file(text).get(secret_name, "")


def resolve_token(
    secret_name: str = "NOTION_TOKEN",
    *,
    a0_root: Path | None = None,
    environ: dict[str, str] | None = None,
) -> str:
    """First hit wins: process env → vault file → empty."""
    env = environ if environ is not None else os.environ
    token = str(env.get(secret_name) or "").strip()
    if token:
        return token
    return read_vault(secret_name, a0_root=a0_root).strip()
