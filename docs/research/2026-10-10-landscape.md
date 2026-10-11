# Landscape: the Agent Zero plugin ecosystem and comparable agent-plugin systems

Date: 2026-10-10. Shared by `a0-plugin-durable`, `a0-plugin-glitchtip`, `a0-plugin-notion`, `a0-plugin-device-sync`, `a0-plugin-jev-compact`. Each repo's per-plugin section follows this shared text. Research used web search only; no paid model calls. Search results were mostly third-party mirrors, so every claim is tagged with how solid its source is. Where a source disagreed or was thin, that is said.

## 1. How Agent Zero plugins work (the host contract)

- Agent Zero looks for plugins in `usr/plugins/<name>/` (user) and `plugins/<name>/` (core). A folder is a plugin when it has a `plugin.yaml` at its root. Fields include `name`, `title`, `description`, `version`, `settings_sections` and per-project/per-agent flags. Valid `settings_sections` values reported: agent, external, mcp, developer, backup. Source: third-party mirrors of Agent Zero's own skill docs ([tessl a0-create-plugin](https://tessl.io/registry/skills/github/agent0ai/agent-zero/a0-create-plugin), [openskillindex a0-create-plugin](https://openskillindex.com/skills/agent0ai-agent-zero-a0-create-plugin)). Confidence: medium. The official repo was not read directly.
- Community plugins live in their own GitHub repo and are listed by a pull request to the `a0-plugins` index repo. The index is a generated `index.json` keyed by plugin name (title, description, github, tags, thumbnail). A `LICENSE` at the repo root is required, and CI requires `name` to match `^[a-z0-9_]+$`. Source: [openskillindex a0-contribute-plugin](https://openskillindex.com/skills/agent0ai-agent-zero-a0-contribute-plugin) and the mirrors above. Confidence: medium.
- Implication for this family: the `a0-plugins` index is the only discovery channel, and its card is a title, a description, tags and a thumbnail. A good thumbnail (our social card or mark) and a plain description do more for discovery than any feature. Our own plugins carry a `LICENSE` already; `a0-plugin-jev-compact` is the only one with `author`, `license`, `homepage` and `min_a0_version` in its manifest.

## 2. Comparable plugin systems

| System | Unit of extension | Distribution | What it does better than an a0 plugin | What it does worse |
|---|---|---|---|---|
| Claude Code plugins | Directory with `.claude-plugin/plugin.json`; bundles slash commands, subagents, hooks, skills, MCP servers ([guide](https://www.morphllm.com/claude-code-marketplace), third-party) | A git repo with `.claude-plugin/marketplace.json`; `/plugin marketplace add owner/repo`, `/plugin install` | Install is one command, from any git repo. Components are declarative (no Python to run). | Not a Python runtime: plugins cannot hold long-lived server code except via MCP. |
| Model Context Protocol (MCP) servers | A process speaking MCP over stdio or HTTP | Registries and per-client config | Client-neutral: one server works in many agents. Notion ships an official hosted one ([Notion docs](https://developers.notion.com/docs/hosting-open-source-mcp), [ToolHive guide](https://docs.stacklok.com/toolhive/guides-mcp/notion-remote)). | Every server is a separate process with its own auth and lifecycle. |
| Agent Zero plugins | Directory with `plugin.yaml`, `api/`, `extensions/`, `helpers/`, optional webui | One GitHub repo each + PR to `a0-plugins` index | Can hook the agent loop in-process (extensions), add API routes and settings panels, and ship an MCP server inside. | Discovery is one index; no versioned install command was found in the sources; hosts are Python-only. |

What users expect from a plugin in any of these systems: install in one step, a visible settings surface, a no-op default when disabled, a clear failure message instead of a crash at host startup, and a licence file.

## 3. Cross-cutting findings

1. **MCP is the neutral layer.** Where a capability already exists as an MCP server, a plugin that re-implements it competes with the vendor. A plugin earns its place by doing what MCP cannot: hooking the agent loop or host lifecycle in-process.
2. **Zero-dependency is a real differentiator in a host plugin.** All five plugins here are stdlib-only or lazy-import optional deps, so they cannot break a0 startup. That is a design choice worth keeping and stating in each README.
3. **Disabled-by-default and inert-when-off** is the convention that makes a plugin safe to install. Keep it.
4. **Discovery needs a card.** The `a0-plugins` index shows title, description, tags, thumbnail. Per-plugin tags and a thumbnail are cheap.

## 4. Adjacent domains (used by the per-plugin sections)

- **Durable execution** (for durable): Temporal records an event history and replays deterministic workflow code; Inngest checkpoints each `step.run()` and charges per run and per step, with a BSL self-host option; DBOS is MIT, database-native, TypeScript-centric; Restate is a single binary with sub-50ms latency claims from vendor pieces; Hatchet, Trigger.dev and LittleHorse also position as agent orchestrators. Sources are vendor-authored and flagged as directional by the search: [ZenML on Inngest alternatives](https://www.zenml.io/blog/inngest-alternatives), [Diagrid FAQ](https://www.diagrid.io/faq/alternatives-dbos-inngest/what-are-the-underappreciated-integration-costs-when-self-building-a-durable-execution-layer-on-temporal-c), [Spheron comparison](https://www.spheron.network/blog/ai-agent-workflow-orchestration-temporal-inngest-restate-gpu-cloud/), [noqta](https://www.noqta.tn/blog/durable-execution-ai-agents-inngest-trigger-temporal-2026).
- **Error tracking** (for glitchtip): GlitchTip accepts Sentry SDKs by changing one DSN string, self-hosts on roughly three services (app, Postgres, Valkey/Redis), and added incremental OpenTelemetry support and span views in 6.2, with an MCP server for AI-assisted debugging ([GlitchTip 6.2 release](https://glitchtip.com/blog/2026-06-22-glitchtip-6-2-released), [SDK docs](https://glitchtip.com/sdkdocs/all-sdks), [Sentry alternatives roundup](https://oneuptime.com/blog/post/2026-03-31-10-best-sentry-alternatives/markdown)). A competitor's roundup says it focuses on error and uptime, not full-stack observability. Langfuse trace-id correlation was not found in any source.
- **Notion access** (for notion): Notion runs an official hosted MCP server at `mcp.notion.com/mcp` (tools such as `notion-search`, `notion-fetch`, `notion-create-pages`); the open-source `makenotion/notion-mcp-server` is described as lower priority and possibly deprecated by two third-party sources. Sources disagree on whether the hosted server is OAuth-only. Verify on Notion's docs before acting: [StackOne deep dive](https://stackone.com/blog/notion-mcp-deep-dive), [ToolHive](https://docs.stacklok.com/toolhive/guides-mcp/notion-remote), [x-cmd](https://x-cmd.com/install/notion-mcp-server).
- **Device sync** (for device-sync): Syncthing is continuous two-way folder sync that needs both devices online and a daemon; Taildrop is ad hoc file transfer over a tailnet, not sync; rsync is one-way and has no memory between runs; Tailscale carries any of them. Sources are community posts and low quality: [Syncthing vs Tailscale thread](https://jisaku.com/glossary/network-nas-sync-tailscale-syncthing-remote), [rsync alternatives](https://alternativeto.net/software/rsync), [Taildrop forum](https://forum.tailscale.com/t/taildrop-alpha-futures-speculation/689).
- **Context compaction** (for jev-compact): Claude Code compacts manually with `/compact` and automatically near full context (reported near 95% of a 200K window); one critique says that timing degrades context first. A 2026 guide groups methods as LLM summarisation, opaque compression, and verbatim compaction (drop low-value lines, keep the rest word for word) and warns that 90%+ compression forces rewriting and hallucination risk. Mem0 markets a memory compression engine (vendor claim of up to 80% fewer prompt tokens, treat as marketing). Letta (MemGPT) pages data in and out like virtual memory. LLMLingua is token pruning. Sources: [morphllm guide](https://www.morphllm.com/context-compression), [Claude Code compaction explainer](https://techie007.substack.com/p/how-memory-compaction-works-in-agents), [Mem0 guide](https://guide.mem0.ai/faq/tools-reduce-context-llm-calls), [Self-Compacting Language Model Agents](https://arxiv.org/pdf/2606.23525).

## 5. What is unique about this family

- In-process agent-loop hooks with a stdlib-only footprint, which neither MCP servers nor marketplace plugins offer.
- A shared engineering standard across five repos: opt-in, inert when disabled, secrets never in config, `{ok, error}` API envelope, offline tests.
- Honest scale: these are single-host tools for one operator's Agent Zero boxes. None claims multi-tenant or multi-region.

## 6. Open risks to the whole family

- Host-contract drift: every claim in section 1 comes from third-party mirrors. Re-verify against the official `agent0ai/agent-zero` repo before the next release of any plugin.
- Five repos, five CI files and five near-identical `helpers/config.py`/`runtime.py` pairs. A shared helper package is the obvious simplification, but a0 plugins are standalone directories, so sharing means a vendored copy or a 6th plugin. See each ROADMAP.

## Plugin section: notion

Scope: what this plugin adds over Notion's own hosted MCP server and other ways to get Notion content into an agent. Read against the code: the plugin ships four read-only MCP tools (`server/notion_server.py`), a stdlib REST client (`helpers/notion_client.py`, 219 lines, one retry on HTTP 429, cursor pagination with a same-cursor guard), an auto-registration helper for `settings["mcp_servers"]` (`helpers/mcp_register.py`, 177 lines), and `helpers/atoms.py` (133 lines), which maps pages to the flat Atom shape used by the Kurultai and device-sync pipelines.

### Comparable options

| Option | What it is | Better than this plugin | Worse than this plugin |
|---|---|---|---|
| Notion hosted MCP, `mcp.notion.com` | Notion-run remote MCP with OAuth, about 36 tools across search, fetch, create, update, comments, views and agent sessions ([supported tools](https://developers.notion.com/guides/mcp/mcp-supported-tools)); Notion's overview says an OAuth-authorized client can read and update content the account can access ([overview](https://developers.notion.com/docs/mcp)). | Always current, write support, respects each user's own permissions, semantic search per Notion's own comparison table in the [makenotion README](https://github.com/makenotion/notion-mcp-server). | Auth is OAuth only and "not designed for headless agents" per one third-party vendor post ([Scalekit](https://scalekit.com/blog/notion-mcp-vs-api)); Notion's own pages describe only OAuth and do not mention tokens or headless use, so the headless claim has one source. Same post: no block-children retrieval, 180 requests per minute per user, tool schemas unversioned, and data-source querying needs Enterprise plus Notion AI. There is no read-only mode documented on either page. |
| `makenotion/notion-mcp-server` (self-hosted, MIT) | Official open-source server; stdio by default, optional Streamable HTTP with a bearer token; auth with an internal integration token via `NOTION_TOKEN`; 22 tools in v2.0.0 ([README](https://github.com/makenotion/notion-mcp-server)). | Broader API surface including data sources and Markdown page read/edit; transport options; token can be limited to read-only capabilities in Notion. | The README says it is "no longer actively maintained or supported" and may be sunset. It exposes write tools to the agent unless the integration is capability-limited, ships as a Node package (a second runtime beside a0's Python), and is not wired into a0's settings or vault. |
| Scalekit-style gateways and aggregators (for example [Cequence AI gateway](https://docs.aigateway.cequence.ai/docs/remote-mcp-servers/notion)) | Hosted proxies that front Notion's MCP with their own auth. | Solve OAuth for background jobs centrally. | Add a third party in the token path and a paid service; not evaluated further (sources thin). |
| LlamaIndex `NotionPageReader` ([PyPI](https://pypi.org/project/llama-index-readers-notion)) | Reader that loads pages or a database into LlamaIndex Documents. | Mature RAG ecosystem integration. | Ties ingestion to LlamaIndex; no agent tools. The PyPI page failed to load when fetched, so version and licence are unverified; a [search summary](https://pypi.org/project/llama-index-readers-notion/0.1.10) only confirms it reads by page id or database. |
| LangChain `NotionDBLoader` ([docs](https://python.langchain.com/docs/integrations/document_loaders/notion)) | Reads a database into Documents using an integration token; extra columns become metadata. | Familiar to LangChain users. | Database-level only; framework-bound; no agent tools. Thin source (search summary only). |
| Raw Notion REST API with an integration token | What `helpers/notion_client.py` wraps. The REST API accepts internal integration tokens, OAuth tokens and personal access tokens, and supports block-level reads and writes and webhooks per [Scalekit](https://scalekit.com/blog/notion-mcp-vs-api). | Full surface and explicit date versioning. | You write the glue, pagination and formatting yourself, which is what this plugin already does. |

### What users expect

- A working token path for unattended agents: the reason to pick a token over OAuth is that no browser consent is needed (Scalekit post above; single source).
- Predictable cost per call: capped results and blocks (`max_search_results`, `max_page_blocks`) rather than whole-workspace dumps.
- Clear error text when the integration has not been shared with a page. This is Notion's access model, not a plugin limit.
- Currency with the Notion API. Notion's self-hosted server targets API version 2025-09-03 and replaced database tools with data-source tools ([README](https://github.com/makenotion/notion-mcp-server)); this plugin pins `Notion-Version: 2022-06-28` (`default_config.yaml`). Whether database queries keep working on the old version indefinitely is not confirmed by any source read here.

### What is unique here

1. **Read-only by construction.** There is no write code at all, so a token-bearing agent cannot modify Notion. Neither Notion option offers this as a product guarantee.
2. **Headless token path inside a0's vault.** The token resolves inside the spawned server from `usr/secrets.env` and never reaches `settings.json`.
3. **`helpers/atoms.py`.** Mapping a database or a `.notion.json` export to flat Atoms for knowledge pipelines has no equivalent in either MCP server. It is the part that cannot be replaced by pointing a0 at a hosted server.

### Weak points (from reading the code)

- The atom `content` field is the JSON-dumped property map, not page body text, so ingested atoms carry metadata but not prose.
- Four tools against roughly 22 to 36 in the official servers: no comments, users or block-level reads.
- Auto-registration (`mcp_register.py`) is the largest piece of convenience code and exists only to save the operator one settings entry.
