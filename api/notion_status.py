"""Plugin status — token present? server registered? safe diagnostics.

POST /api/plugins/notion/notion_status

Session-auth'd like a normal a0 API (no PeerEndpoint-style token gate —
this is a user-facing diagnostic, not a machine peer). Emits no token
material and no filesystem paths.
"""

from __future__ import annotations

import asyncio

from helpers.api import ApiHandler

from usr.plugins.notion.helpers import runtime


class NotionStatus(ApiHandler):
    async def process(self, input, request):
        # status() touches the vault file + settings — off the a0 loop
        return {"ok": True, **(await asyncio.to_thread(runtime.status))}
