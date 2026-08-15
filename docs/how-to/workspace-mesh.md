# Workspace mesh — AOA + vault + companion skills

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

Optional siblings: `qm` (`./scripts/qm-setup.sh`), `py-moomoo-api`.

## Open in Cursor

```bash
./scripts/write-aoa-workspace.sh
# File → Open Workspace from File… → AOA.code-workspace
```

Only folders that exist on disk are included.

VS Code / Cursor tasks: **AOA: knowledge-stack setup**, **AOA: write multi-root workspace**,
**AOA: attl init (brain workspace)**.

## Cloud Agent environment

Repo-managed bootstrap: `.cursor/environment.json` runs `pip install -e ".[dev,web]"`,
`aoa attl init`, and `write-aoa-workspace.sh` after checkout. Knowledge-stack sibling
clones remain local (`./scripts/knowledge-stack-setup.sh`) and are gitignored.

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

- [obsidian-second-brain-integration.md](obsidian-second-brain-integration.md)
- [spine-integration.md](spine-integration.md)
- [obsidian-skills-integration.md](obsidian-skills-integration.md)
- [moomoo-setup.md](moomoo-setup.md)
- [qm-integration.md](qm-integration.md)
