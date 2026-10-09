# a0-plugin-notion

Notion connector for [Agent Zero](https://github.com/agent0ai/agent-zero):
the agent gets `notion_search` / `notion_get_page` / `notion_get_page_content`
/ `notion_query_database` tools through a bundled **local stdio MCP server**,
plus a `notion://` / `.notion.json` ingestion path that emits atoms for
knowledge pipelines. Ported from the Khan fork's `connectors/notion.py` —
no upstream edits, read-only by design.

## Install

Drop the repo contents into `usr/plugins/notion/` (the directory name is the
plugin name — imports and `/api/plugins/notion/*` routes key on it; the repo
is `a0-plugin-notion` but the install path must be `notion`).

## Setup — two steps

1. Create a [Notion integration](https://www.notion.so/profile/integrations),
   copy the internal token (`ntn_…`), and share the pages/databases you want
   a0 to reach with that integration.
2. Add `NOTION_TOKEN=ntn_…` to the **a0 secrets vault** (Settings → Secrets —
   backed by `usr/secrets.env`), or export `NOTION_TOKEN` in a0's environment.

Set `enabled: true` in the plugin config and restart — the plugin registers
`a0_notion` in `settings["mcp_servers"]` (idempotent, preserves your other
servers) and a0 spawns `server/notion_server.py` with the same Python it
runs on. `hooks.py uninstall` removes the entry.

## Why a local MCP server (the tradeoff)

Notion runs an official remote MCP at `mcp.notion.com`. Choosing a bundled
local server was deliberate:

| | remote `mcp.notion.com` | local stdio (this plugin) |
|---|---|---|
| Auth | OAuth 2.0 flow — interactive browser consent per workspace | Integration token from the vault — headless, no OAuth dance |
| Runs on | Notion-hosted, always current | Your box — air-gapped tailnets work |
| Surface | Full read+write surface Notion ships | Read-only by design — fewer blast radius for a token-bearing agent |
| Latency | Remote round-trip per call | Local process; Notion API still remote but no OAuth/session overhead |
| Deps | Needs OAuth-capable MCP client | `mcp` SDK — already an a0 dependency |

If you prefer the remote server, add it under `mcp_servers` yourself and set
`auto_register_mcp: false` — this plugin's tools and theirs can coexist.

## How the token stays out of settings.json

a0's stdio spawn passes a **safe-listed environment** plus the static `env`
dict from the `mcp_servers` entry — so the token can neither ride the
process env nor sit in the entry (it would be plaintext in settings.json).
Instead the spawned server resolves it *inside its own process*:

1. `NOTION_TOKEN` (or `secret_name`) in the process env — covers manual
   runs and operators who inject secrets another way.
2. `usr/secrets.env` — the same vault `§§secret(NOTION_TOKEN)` resolves
   against; the server self-locates the a0 root from `__file__`.

So the vault stays the single source of truth and settings.json only ever
holds `{type: stdio, command, args}` — no secrets, no absolute user paths.

## Tools

| tool | what it does |
|---|---|
| `notion_search(query, filter_object?, page_size?)` | Workspace search; `filter_object` = `page`/`database` |
| `notion_get_page(page_id)` | Metadata + compacted property values |
| `notion_get_page_content(page_id, max_blocks?)` | Block tree flattened to readable text (headings, lists, code, tables, todos) |
| `notion_query_database(database_id, filter_json?, page_size?)` | Rows as page summaries; `filter_json` = raw Notion filter object |

Read-only — there is intentionally no create/update/delete tool.

## Ingestion atoms

`helpers/atoms.py` ports Khan's contract for pipelines (Kurultai #200,
device-sync's kurultai inbox):

- `notion://database/<id>` → live query → atoms
- `…/<name>.notion.json` → cached export → atoms
- `page_to_atom(page, source)` → the flat `{id,title,content,tags,source,extra}` shape

Bulk/scheduled sync is deliberately out of scope — schedule a job that calls
these helpers rather than hammering the API from agent tools.

## Config

`default_config.yaml` documents every key; env overrides use the
`NOTION_*` prefix (`NOTION_ENABLED`, `NOTION_SECRET_NAME`, `NOTION_API_VERSION`,
`NOTION_HTTP_TIMEOUT_S`, `NOTION_MAX_SEARCH_RESULTS`, `NOTION_MAX_PAGE_BLOCKS`,
`NOTION_AUTO_REGISTER_MCP`).

## Diagnostics

`POST /api/plugins/notion/notion_status` → `{enabled, secret_name,
token_present, mcp_registered, server_name}` — session-auth'd like a normal
a0 API; never echoes the token.

## Tests

```bash
python -m pytest tests/ -q
```

Standalone — the Notion API is faked at the `urlopen` seam, the MCP SDK is
stubbed where needed, no network, no token.

## Limits

- The integration only sees pages explicitly shared with it — that's
  Notion's model, not a plugin limit.
- `child_page`/`child_database` blocks appear as `[page]`/`[database]`
  stubs in `get_page_content` — open them with their own ids (one fetch
  level per call keeps responses bounded).
- API surface is pinned to `Notion-Version: 2022-06-28` (config-overridable
  when Notion's dated API moves).
