# Multi-workspace integration

AOA Financial is the hub for a stack of sibling projects (obsidian-second-brain,
Spine, obsidian-skills, QM, OpenStock) that share **one Obsidian vault** as a
living second brain. These two scripts let that knowledge stack span *other*
repos and open everything together.

```
                     ┌───────────────── AOA-Vault (shared) ─────────────────┐
                     │  AI-first notes · architecture · research · decisions │
                     └───▲───────────────▲───────────────▲──────────────────┘
                         │               │               │
          /obsidian-architect     /obsidian-architect   /spine-capture
                         │               │               │
                ┌────────┴──────┐ ┌──────┴───────┐ ┌─────┴────────┐
                │ AOA-Financial │ │  your repo A │ │  your repo B │
                │ (hub + clones)│ │ (connected)  │ │ (connected)  │
                └───────────────┘ └──────────────┘ └──────────────┘
```

## 1. Connect another repo to the shared second brain

Run from the AOA repo, pointing at any other project:

```bash
./scripts/connect-workspace.sh /path/to/other/repo
```

This links the shared skills, points that repo's MCP server + `.env` at the
shared `AOA-Vault` (absolute paths), and prints next steps. It:

| Step | Effect in the target repo |
|------|---------------------------|
| Cursor skills | Symlinks `obsidian-second-brain` (+ spine, obsidian-skills) into `.cursor/skills/` |
| MCP | Writes `.cursor/mcp.json` pointing at the shared vault (backs up any existing file) |
| `.env` | Records `AOA_OBSIDIAN_VAULT_PATH` (+ `AOA_SPINE_ENABLED`) via the shared, macOS-safe `env_upsert` |

Preview what would be linked without touching anything:

```bash
./scripts/connect-workspace.sh --list
```

Then, **in the connected workspace**:

1. Restart Cursor so it loads `.cursor/mcp.json` + skills
2. Run `/obsidian-architect` to document that project into the shared vault
3. Run `/spine-capture` after commits to draft feature docs

Because the vault, `~/.spine/config.json`, and obsidian-second-brain clone are
shared, every connected project reads and writes the **same** second brain.

## 2. Open the whole stack in one window

Generate a multi-root Cursor/VS Code workspace bundling AOA + every sibling
clone that exists + the vault:

```bash
./scripts/generate-workspace.sh
```

This writes `aoa-stack.code-workspace` (gitignored — it contains absolute,
machine-local paths). Open it with **File → Open Workspace from File…**.

Add extra roots (e.g. connected repos) to the same window:

```bash
./scripts/generate-workspace.sh aoa-stack.code-workspace /path/to/other/repo
```

Only folders that exist are included, so it is safe to re-run after adding or
removing siblings.

## Prerequisites

Set up the knowledge stack in the AOA repo first:

```bash
./scripts/knowledge-stack-setup.sh
```

See [obsidian-second-brain-integration.md](obsidian-second-brain-integration.md),
[spine-integration.md](spine-integration.md), and
[obsidian-skills-integration.md](obsidian-skills-integration.md).

## Notes

- Skills are **symlinks** to the shared clones, so updating the clones updates
  every connected workspace at once.
- The connector never deletes a target's existing `.cursor/mcp.json` — it backs
  it up first. If the target already ran its own MCP servers, merge them by hand.
- `/research` and the MCP server still need `uv` and (for research) API keys —
  see [obsidian-second-brain-integration.md](obsidian-second-brain-integration.md).
