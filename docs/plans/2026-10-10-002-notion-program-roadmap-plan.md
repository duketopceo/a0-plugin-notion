---
title: "a0-plugin-notion program roadmap"
type: program-roadmap
date: 2026-10-10
status: proposed
origin: docs/research/2026-10-10-landscape.md
---

# a0-plugin-notion program roadmap

Note: written by hand in the shape of `2026-10-09-001-feat-notion-plugin-plan.md`; the `ce-plan` skill was invoked but the program-level, no-code scope was authored directly. Claims below were checked against the code on 2026-10-10.

## Summary

Keep the plugin standalone and keep it read-only. Its defensible niche is the headless token path plus `helpers/atoms.py`. The work ahead is mostly keeping pace with the Notion API, making atoms carry body text, and trimming convenience code.

## Now / Next / Later

| Now | Next | Later |
|---|---|---|
| U1 Notion API version check (easy) | U3 Atoms with page body text (medium) | U5 Optional extra read-only tools (medium) |
| U2 README and limits aligned with Notion's hosted MCP (easy, done in this PR) | U4 Discovery card and manifest fields (easy) | U6 Decide on dropping auto-registration (medium) |

## Units

### U1. Notion API version and data-source compatibility check

- Status: Now, not started. Evidence: `default_config.yaml` pins `api_version: "2022-06-28"`; Notion's self-hosted server README says v2.0.0 targets 2025-09-03 and replaced database tools with data-source tools.
- Dependencies: none. Verification: a live check with a throwaway integration against `POST /v1/databases/<id>/query` on the pinned version, recorded in docs; `tests/test_client.py` unchanged.
- **Difficulty**: easy. Needs a manual check plus a decision, no design.
- **Feasibility**: Notion could deprecate 2022-06-28 or change multi-source database behaviour; needs a real workspace token and no paid calls. No source read here states a sunset date.
- **Simpler alternative**: do nothing in code; document the pin and tell operators to set `api_version` (already config-overridable in `helpers/config.py`).

### U2. README and limits aligned with the hosted MCP

- Status: Now, done in this PR. Evidence: README comparison table now cites Notion's docs and records that the headless claim is single-sourced.
- Dependencies: none. Verification: every README claim traceable to code or a cited URL.
- **Difficulty**: easy. Docs only.
- **Feasibility**: Notion may add token auth to the hosted server, which would weaken the main differentiator; recheck quarterly.
- **Simpler alternative**: replace the whole comparison table with one paragraph and a link to `docs/research/2026-10-10-landscape.md`.

### U3. Atoms carry page body text

- Status: Next. Evidence: `page_to_atom` in `helpers/atoms.py` sets `content` to the JSON-dumped property map; body text is only reachable through `notion_get_page_content`.
- Dependencies: U1 (API shape); `helpers/notion_fmt.blocks_to_text` already exists. Verification: new tests in `tests/test_fmt_and_atoms.py` with a faked `urlopen`; an atom for a page with body text contains it; existing wire shape (`id,title,content,tags,source,extra`) unchanged.
- **Difficulty**: medium. One extra API call per page makes ingestion slower and rate-limit-bound.
- **Feasibility**: Notion rate limits (about 3 requests per second, handled by one retry in `helpers/notion_client.py`); changing `content` could break Kurultai or device-sync consumers, so it must be opt-in.
- **Simpler alternative**: keep atoms as metadata and let pipelines call `notion_get_page_content` for pages they care about; ship nothing.

### U4. Discovery card and manifest fields

- Status: Next. Evidence: `plugin.yaml` has no `author`, `license`, `homepage` or `min_a0_version`; the shared landscape says only jev-compact has them; the `a0-plugins` index shows title, description, tags and thumbnail.
- Dependencies: owner sign-off on the logo. Verification: `tests/test_consistency.py` still passes; the index PR validates.
- **Difficulty**: easy. Manifest edits plus an index pull request.
- **Feasibility**: the index's current CI rules are known only from third-party mirrors; re-verify against `agent0ai/agent-zero` first.
- **Simpler alternative**: skip the index listing and rely on the GitHub README.

### U5. Optional extra read-only tools

- Status: Later. Evidence: four tools here against about 36 in the hosted server; Scalekit notes the hosted MCP lacks block-children retrieval, which this plugin has.
- Dependencies: U1. Verification: each new tool has a faked-`urlopen` test and no write path.
- **Difficulty**: medium. Each tool is small, but the read-only contract in `AGENTS.md` needs an explicit issue decision for each.
- **Feasibility**: permission scopes on the integration; capability bloat against the plugin's small-surface selling point.
- **Simpler alternative**: do not add tools; point users who need comments or users to the hosted MCP, which can coexist (README already says so).

### U6. Decide whether to drop auto-registration

- Status: Later. Evidence: `helpers/mcp_register.py` (177 lines), `helpers/runtime.py` (109), `extensions/python/startup_migration/_75_notion_init.py` and the `hooks.py` uninstall path exist only to write one `mcp_servers` entry safely (including the `set_settings_delta` two-step and rollback).
- Dependencies: none, but removal is a breaking change for 0.1.x users. Verification: `tests/test_secrets_and_register.py` and `tests/test_consistency.py` updated; docs show the manual entry.
- **Difficulty**: medium. Deleting is easy; migration and doc work is the cost.
- **Feasibility**: a0's settings write API could change either way; manual entry puts a JSON edit on every operator and loses automatic repair after a venv rebuild.
- **Simpler alternative**: keep it but flip `auto_register_mcp` to default off and print the exact entry in `notion_status`; delete nothing.

## Merge / retire assessment

Verdict: no, keep standalone, slimmed over time.

- Retire: the hosted server is OAuth-only per Scalekit and Notion's own pages describe only OAuth (the "not for headless agents" quote is one third-party source). That leaves unattended a0 jobs without a Notion path, which is this plugin's job. Retiring is wrong while that holds. Recheck if Notion adds token auth to `mcp.notion.com`.
- Replace with `makenotion/notion-mcp-server`: its README says it is no longer actively maintained and may be sunset, it is a Node package, and it exposes write tools. Not a safe dependency for a read-only guarantee.
- Slim to atoms only: the four MCP tools are about 160 lines in `server/notion_server.py` plus the shared client. Dropping them would leave `helpers/atoms.py` (133 lines) needing `notion_client.py` and `notion_fmt.py` anyway, so the saving is small and the agent loses its only headless read tool. Not worth it.
- Merge into device-sync: device-sync's kurultai inbox consumes the Atom shape, but the two plugins share no code, config or lifecycle beyond that format. A merge would couple Notion API pinning to file sync. Not recommended.

Biggest simplification available: U6, the auto-registration code path, which is the only piece that exists purely for convenience.
