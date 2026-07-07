# Obsidian second brain integration

[obsidian-second-brain](https://github.com/afidurko/obsidian-second-brain) is a
cross-CLI skill that turns an Obsidian vault into a living AI-first second brain.
AOA Financial keeps it as a **sibling clone** so trading decisions, architecture
notes, and research can compound in one vault while the swarm runs separately.

## Architecture

```
┌─────────────────────┐     journal + team decisions
│  AOA Financial      │──────────────────────────────┐
│  aoa serve :8080    │                              │
│  (swarm + trading)  │                              ▼
└─────────────────────┘                    ┌─────────────────────┐
         │                                 │  AOA-Vault          │
         │  /obsidian-architect            │  (Obsidian)         │
         └────────────────────────────────▶│  AI-first notes     │
                                           └─────────────────────┘
         obsidian-second-brain skill ◀─────── Cursor / Claude Code
         (44 commands, MCP server)
```

- **AOA** — autonomous trading swarm, risk guardrails, team dashboard.
- **obsidian-second-brain** — vault skill repo (MIT); not vendored into AOA.
- **AOA-Vault** — your Obsidian vault beside the repo (seeded from the sample vault).
- **Link** — set `AOA_OBSIDIAN_VAULT_PATH` so the dashboard header opens the vault in Obsidian.

Trading execution stays in AOA only. The vault captures decisions, research, and
architecture — use `/obsidian-save`, `/obsidian-ingest`, and `/obsidian-architect`
from Cursor after setup.

## 1. Clone and wire

Idempotent setup (clone skill, seed vault, link Cursor skill, write MCP config):

```bash
./scripts/obsidian-second-brain-setup.sh
```

Add to `.env`:

```env
AOA_OBSIDIAN_VAULT_PATH=./AOA-Vault
```

Sync research API keys from AOA `.env` into `~/.config/obsidian-second-brain/.env`:

```bash
./scripts/sync-obsidian-second-brain-env.sh
```

The sync script bridges:

| AOA `.env` | obsidian-second-brain config |
|------------|------------------------------|
| `AOA_OBSIDIAN_VAULT_PATH` | `OBSIDIAN_VAULT_PATH` |
| `GEMINI_API_KEY` | `GEMINI_API_KEY` |
| `PERPLEXITY_API_KEY` | `PERPLEXITY_API_KEY` |
| `XAI_API_KEY` | `XAI_API_KEY` |
| `YOUTUBE_API_KEY` | `YOUTUBE_API_KEY` |

Research commands (`/research`, `/x-read`, `/youtube`, etc.) need the corresponding keys.
Vault read/write and `/obsidian-architect` work without them.

## 2. Open the vault

1. Install [Obsidian](https://obsidian.md/) if needed.
2. **Open folder as vault** → select `AOA-Vault` beside the repo.
3. In Cursor, run `/obsidian-init` inside the vault to generate `_CLAUDE.md`.
4. Run `/obsidian-architect` on this repo to document AOA architecture into the vault.
5. Restart Cursor so the MCP server picks up `.cursor/mcp.json`.

## 3. Run with AOA dashboard

```bash
pip install -e ".[dev,web]"
export AOA_OBSIDIAN_VAULT_PATH=./AOA-Vault
aoa serve
```

- AOA swarm: http://localhost:8080 (header shows **Second Brain ↗** when vault path is set)
- Obsidian: open the vault locally

Optional: add the vault to the work loop's extra sources:

```env
AOA_WORKLOOP_EXTRA_SOURCES=docs/,AOA-Vault/
```

## 4. MCP server

Setup writes `.cursor/mcp.json` pointing at the bundled MCP server in the sibling clone.
Tools include `obsidian_search`, `obsidian_read_note`, `obsidian_save_note`, and skill
playbooks for ingest/synthesize workflows.

Live test (after setup):

```bash
cd obsidian-second-brain
OBSIDIAN_VAULT_PATH=../AOA-Vault uv run --with mcp python integrations/obsidian-mcp-server/live_test.py "AOA trading"
```

## 5. Verify

```bash
python3 -m pytest tests/test_web.py -q
```

## Notes

- Default clone: `https://github.com/afidurko/obsidian-second-brain.git` (override with `OBSIDIAN_SECONDBRAIN_REPO`).
- The skill repo is MIT; your vault content is local and gitignored.
- Use `/obsidian-save` after team reviews to persist decisions from swarm cycles.
- See upstream [README](https://github.com/afidurko/obsidian-second-brain) for all 44 commands.
