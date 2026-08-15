# Workspace mesh — AOA + vault + companion skills

> Knowledge/vault/Cursor multi-root mesh (`knowledge-stack-setup`, Obsidian, Spine).
> For trading companion status (`aoa workspaces`), see [workspaces.md](workspaces.md).

AOA Financial is the primary trading runtime. Companion workspaces share one
vault and Cursor multi-root layout so agents can move between trading, notes,
and broker API skills without leaving the stack.

## One-command setup (local Mac)

```bash
./scripts/knowledge-stack-setup.sh
```

This clones and wires:

| Workspace | Role |
|-----------|------|
| `AOA-Financial` | Trading swarm, ATTL, Moomoo broker |
| `AOA-Vault` | Shared Obsidian vault |
| `obsidian-second-brain` | AI-first vault ops + MCP |
| `spine` | Commit-driven feature spines |
| `obsidian-skills` | Obsidian format skills |
| Moomoo OpenD skills | Vendored `moomooapi` + `install-moomoo-opend` |
| `AOA.code-workspace` | Multi-root Cursor/VS Code workspace |

Optional siblings: `qm` (`./scripts/qm-setup.sh`), `py-moomoo-api`,
SGX order-book notebooks (`./scripts/sgx-orderbook-setup.sh` — see
[hft-research-lane.md](hft-research-lane.md)).

## Open in Cursor

```bash
./scripts/write-aoa-workspace.sh
# File → Open Workspace from File… → AOA.code-workspace
```

Only folders that exist on disk are included. Add external repos as extra roots:

```bash
./scripts/write-aoa-workspace.sh AOA.code-workspace /path/to/other/repo
```

## Connect an external repo to the shared vault

The mesh above covers sibling clones beside AOA. To share the same second brain
with a project living **elsewhere** on disk:

```bash
./scripts/connect-workspace.sh /path/to/other/repo   # --list to preview
```

This, in the target repo:

| Step | Effect |
|------|--------|
| Cursor skills | Symlinks the shared `obsidian-second-brain` (+ spine, obsidian-skills) into `.cursor/skills/` |
| MCP | Writes `.cursor/mcp.json` pointing at the shared vault (backs up any existing file) |
| `.env` | Records `AOA_OBSIDIAN_VAULT_PATH` (+ `AOA_SPINE_ENABLED`) via the macOS-safe `env_upsert` |

Then, in that workspace: restart Cursor, run `/obsidian-architect` to document it
into the shared vault, and `/spine-capture` after commits. Because the vault,
`~/.spine/config.json`, and the obsidian-second-brain clone are shared, every
connected project reads and writes the **same** second brain.

## Cloud Agent environment

Repo-managed bootstrap: `.cursor/environment.json` runs `pip install -e ".[dev,web]"`,
`aoa attl init`, and `write-aoa-workspace.sh` after checkout. Knowledge-stack sibling
clones remain local (`./scripts/knowledge-stack-setup.sh`) and are gitignored.

VS Code / Cursor tasks include knowledge-stack setup, workspace writer, ATTL init,
and `aoa workloop upgrade --dry-run`.

## Agent skills (already in-repo)

| Skill | Path |
|-------|------|
| `moomooapi` | `.cursor/skills/moomooapi/` |
| `install-moomoo-opend` | `.cursor/skills/install-moomoo-opend/` |
| Loop / ATTL / ship | `.cursor/skills/loop-*`, `ship-loop`, … |

After knowledge-stack setup, Obsidian companion skills link under `.cursor/skills/` too.

## Mesh map

Machine-readable graph: `brain/mesh/repos.yaml` + `brain/mesh/index.yaml`.
Refresh: `aoa attl brain sync`.

## Related how-tos

- [workspaces.md](workspaces.md) — trading companions (`aoa workspaces`)
- [obsidian-second-brain-integration.md](obsidian-second-brain-integration.md)
- [spine-integration.md](spine-integration.md)
- [obsidian-skills-integration.md](obsidian-skills-integration.md)
- [moomoo-setup.md](moomoo-setup.md)
- [qm-integration.md](qm-integration.md)
- [hft-research-lane.md](hft-research-lane.md)
- [sgx-orderbook-reference.md](sgx-orderbook-reference.md)
