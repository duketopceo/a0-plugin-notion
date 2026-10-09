"""Plugin config — dataclass + env overrides (DEVICE_* pattern parity)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

_ENV_MAP = {
    "enabled": ("NOTION_ENABLED", "bool"),
    "secret_name": ("NOTION_SECRET_NAME", "str"),
    "api_version": ("NOTION_API_VERSION", "str"),
    "http_timeout_s": ("NOTION_HTTP_TIMEOUT_S", "float"),
    "max_search_results": ("NOTION_MAX_SEARCH_RESULTS", "int"),
    "max_page_blocks": ("NOTION_MAX_PAGE_BLOCKS", "int"),
    "auto_register_mcp": ("NOTION_AUTO_REGISTER_MCP", "bool"),
}


def _bool(v: Any) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


@dataclass
class NotionConfig:
    enabled: bool = False
    secret_name: str = "NOTION_TOKEN"
    api_version: str = "2022-06-28"
    http_timeout_s: float = 30.0
    max_search_results: int = 25
    max_page_blocks: int = 500
    auto_register_mcp: bool = True

    def __post_init__(self) -> None:
        # raw-dict callers can hand us truthy strings ("false") — coerce
        self.enabled = _bool(self.enabled)
        self.auto_register_mcp = _bool(self.auto_register_mcp)
        self.secret_name = str(self.secret_name or "NOTION_TOKEN").strip() or "NOTION_TOKEN"
        self.api_version = str(self.api_version or "2022-06-28").strip() or "2022-06-28"
        try:
            self.http_timeout_s = max(1.0, min(300.0, float(self.http_timeout_s)))
        except (TypeError, ValueError):
            self.http_timeout_s = 30.0
        for attr, lo, hi, default in (
            ("max_search_results", 1, 100, 25),
            ("max_page_blocks", 10, 5000, 500),
        ):
            try:
                setattr(self, attr, max(lo, min(hi, int(getattr(self, attr)))))
            except (TypeError, ValueError):
                setattr(self, attr, default)

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _merge_env(raw: dict[str, Any]) -> dict[str, Any]:
    out = dict(raw)
    for field, (var, kind) in _ENV_MAP.items():
        if var not in os.environ:
            continue
        val: Any = os.environ[var]
        try:
            if kind == "bool":
                val = _bool(val)
            elif kind == "int":
                val = int(val)
            elif kind == "float":
                val = float(val)
        except (TypeError, ValueError):
            continue
        out[field] = val
    return out


def get_config(config: dict[str, Any] | None = None) -> NotionConfig:
    """Build a validated config from a raw dict (plugin config) merged
    with env overrides. Unknown keys are ignored. ``None`` pulls the
    plugin's merged config from the host (get_plugin_config)."""
    if config is None:
        config = {}
        try:
            from helpers.plugins import get_plugin_config

            loaded = get_plugin_config("notion")
            if isinstance(loaded, dict):
                config = loaded
        except Exception:
            pass  # outside a0 / host helper missing — defaults+env apply
    raw = _merge_env(config)
    known = {k: v for k, v in raw.items() if k in NotionConfig.__dataclass_fields__}
    return NotionConfig(**known)
