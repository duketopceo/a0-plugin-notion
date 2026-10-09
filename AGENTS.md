# a0-plugin-notion — Agent Contract

Notion connector for stock Agent Zero (Khan `connectors/notion.py` port).
Plugin surface only — **no upstream edits**.

## Layout

- `helpers/notion_client.py` — stdlib REST client (search, page, block
  children, db query); one `opener` seam for tests. Read-only.
- `helpers/notion_fmt.py` — pure dict→text formatting (title, rich_text,
  block→line, property compaction). **Zero imports** — the MCP subprocess
  and the host both load it in their own namespace; keep it dependency-free.
- `helpers/secrets_env.py` — token resolution: env → `usr/secrets.env`
  (a0 root self-located via `usr/plugins` ancestor). Never settings.json.
- `helpers/mcp_register.py` — merge/remove the `a0_notion` stdio entry in
  `settings["mcp_servers"]` (idempotent, preserves other servers).
- `helpers/atoms.py` — Khan Atom mapping + `notion://` / `.notion.json`
  ingestion (Kurultai/device-sync pipelines speak this shape).
- `helpers/config.py` `runtime.py` — NotionConfig + facade; `configure(None)`
  → host `get_plugin_config("notion")`.
- `server/notion_server.py` — FastMCP stdio server, 4 read-only tools.
  Runs in the a0 venv as a subprocess — **do not import `usr.plugins.*`
  here**; only `_PLUGIN_DIR` is on sys.path, so imports are `helpers.*`.
- `api/notion_status.py` — session-auth'd diagnostics.
- `extensions/python/startup_migration/_75_` — sync `execute`, lazy
  plugin import inside `execute()` (upstream sweep is unguarded).
- `hooks.py` — install/update log; uninstall unregisters the MCP entry.

## Conventions

- **Host seams lazy**: `helpers.settings`, `helpers.plugins`,
  `helpers.api`, `helpers.extension` import inside functions — a broken
  host import can never abort a0's sweep.
- **Plugin self-imports** fully qualified: `usr.plugins.notion.*` — except
  inside `server/`, which runs standalone and must use `helpers.*`.
- **Secrets**: token resolves inside the spawned server (env → vault
  file). `mcp_servers` entries must NEVER carry `env` with the token —
  a0's stdio env is static config, not a secret channel.
- **Read-only contract**: no write tools. A token-bearing agent can only
  read — do not add create/update/delete without an issue-level decision.
- **Never-raise**: extension/hooks catch broadly; tool errors return
  `error: …` strings, not exceptions (MCP surfaces them to the agent).
- **`mcp` is an a0 dep**: FastMCP import failure = wrong interpreter —
  the entry pins `sys.executable` at configure time for that reason.

## Tests

`python -m pytest tests/ -q` — standalone (conftest stubs host modules;
Notion API faked at `urlopen`; FastMCP stubbed for server tests).

## Provenance

Port of Khan `connectors/notion.py` + `connectors/base.py` (MIT, same
author). Atom shape stays wire-compatible with Kurultai/device-sync
pipelines — `id`, `title`, `content`, `tags`, `source`, `extra`.
