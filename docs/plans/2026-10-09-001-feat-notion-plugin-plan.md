# a0-plugin-notion — implementation plan (Khan#196)

## Issue contract

- Agent can search/read Notion pages on stock upstream a0.
- Secrets via `§§secret()`/plugin config, never settings.json.
- README states MCP vs local-server tradeoff.
- Prefer MCP as agent-facing contract; local token-based server for ingestion jobs.

## Verified host facts (Khan fork == upstream a0 for these seams)

- `helpers/mcp_handler.py`: `mcp` SDK is an a0 dep (mcp==1.27.0, fastmcp==3.2.4);
  `MCPServerLocal` = `{name,type:stdio,command,args,env}` inside the
  `settings["mcp_servers"]` JSON (`{"mcpServers": {...}}`); a settings change
  fires `MCPConfig.update()` which spawns the server and registers its tools.
- MCP stdio spawn env = `get_default_environment()` SAFE-LIST (HOME/PATH/
  SHELL/TERM/USER) **+ explicit env dict** — process-env injection does NOT
  reach the server. `§§secret()` resolves only in tool args/prompts, NOT in
  mcp_servers JSON.
- `helpers/secrets.py`: vault is `usr/secrets.env`, a plain dotenv file —
  readable by any same-user process (the spawned server).
- Plugin routing: `/api/plugins/<name>/<handler>` → `usr/plugins/<name>/api/`.
- `startup_migration` extensions run synchronously (a0's extension sweep
  fails on awaitables); plugin name = import path, must be `notion`.
- Khan source: `connectors/notion.py` (246 LOC read-only: notion://database/<id>
  + .notion.json → Atoms), `connectors/base.py` (Atom dataclass).

## Design

**Local stdio MCP server** shipped inside the plugin — `mcp` SDK is already
installed by a0, so the plugin stays zero-new-dep. The plugin registers
itself in `settings["mcp_servers"]` at startup (idempotent, non-secret
config only: command=sys.executable, args=[server path]); `hooks.py
uninstall` removes the entry.

**Token path** (the crux): the server resolves the Notion token at startup
inside the spawned process — `NOTION_TOKEN` env var (covers the safe-list
when a0 passes env overrides, plus standalone/ingestion runs), else
`usr/secrets.env` parsed directly (self-locates a0 root via `__file__`
parents). The secret therefore lives only in the vault; `mcp_servers`
config never sees it.

**Tools (read-only, matching Khan's contract):**
- `notion_search(query, filter_object="page"|"database", page_size)`
- `notion_get_page(page_id)` — metadata/properties
- `notion_get_page_content(page_id)` — block children flattened to text
- `notion_query_database(database_id, filter_json=None, page_size)`

**Ingestion atoms** (`helpers/atoms.py`): port of `_extract_title` /
`_page_to_atom` + `.notion.json` file + `notion://database/<id>` — the
Atom shape Kurultai (#200) and the device-sync kurultai inbox already
speak. Bulk scheduling stays out (issue: jobs call dlt/readers later).

## Layout

```
plugin.yaml                       name: notion
default_config.yaml               enabled/secret_name/api caps
server/notion_server.py           FastMCP stdio server (~4 tools)
helpers/notion_client.py          stdlib REST client (search/page/blocks/db)
helpers/secrets_env.py            usr/secrets.env reader + token chain
helpers/mcp_register.py           merge/remove entry in mcp_servers JSON
helpers/config.py runtime.py      config dataclass + facade
helpers/atoms.py                  Khan atom-mapping port
api/notion_status.py              token configured? server registered?
extensions/python/startup_migration/_75_notion_init.py
hooks.py                          uninstall -> unregister
```

## Acceptance mapping

- search/read pages on stock a0 -> the 4 MCP tools, exercised against a
  fake urlopen in tests.
- secrets via §§secret()/plugin config -> `usr/secrets.env` chain +
  `secret_name` config; settings.json only ever carries the stdio entry.
- README tradeoff section -> remote mcp.notion.com (OAuth, hosted,
  interactive auth) vs local token server (headless, shipped).
