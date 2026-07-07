# Spine + obsidian-second-brain bridge

[Spine](https://github.com/afidurko/spine) and
[obsidian-second-brain](https://github.com/afidurko/obsidian-second-brain) share one
Obsidian vault. They solve different problems and use different folder conventions inside
that vault.

| System | Role | Vault layout |
|--------|------|--------------|
| **obsidian-second-brain** | AI-first capture, research, synthesis, nightly agents | `Daily/`, `Projects/`, `People/`, `Research/`, `_CLAUDE.md` |
| **Spine** | Commit-driven feature docs, spine notes, graph colors | `{repo}/{feature}/` with `type/*` tags |

## Shared vault path

Both systems read the same absolute path:

- obsidian-second-brain: `OBSIDIAN_VAULT_PATH` (in `~/.config/obsidian-second-brain/.env`)
- Spine: `SPINE_VAULT_PATH` or `~/.spine/config.json` → `vaultPath`

AOA Financial setup sets all three to `./AOA-Vault`.

## How they work together

```
Session start
  ├─ Spine auto-loads feature index (repo-first spine notes)
  └─ obsidian-second-brain SessionStart injects _CLAUDE.md context

After a trading cycle or fix
  ├─ /spine-capture — commit-driven feature doc under AOA-Financial/{feature}/
  └─ /obsidian-save — AI-first decision note in Projects/ or Daily/

Architecture overview
  ├─ /obsidian-architect — codebase scan into vault (OSB format)
  └─ /spine-recall Swarm — deep pull of Spine feature docs
```

Spine owns **durable engineering knowledge tied to git commits**. obsidian-second-brain
owns **living AI-first notes that rewrite themselves**. Wikilinks connect them when useful.

## Install (from AOA Financial)

```bash
./scripts/knowledge-stack-setup.sh
```

Or only the bridge (after both sibling clones exist):

```bash
./scripts/integrate-spine-obsidian.sh
```

Manual install inside this repo:

```bash
cd integrations/spine && ./setup.sh
```

## AOA Financial layout

After setup, the shared vault contains:

```
AOA-Vault/
  _CLAUDE.md                 ← obsidian-second-brain operating manual
  Spine Architecture.md      ← Spine meta doc
  Daily/ Projects/ …         ← obsidian-second-brain sample areas
  AOA-Financial/             ← Spine repo folder
    Swarm/Swarm.md
    Broker/Broker.md
    Work-loop/Work-loop.md
  .spine/retrieval-policy.md ← Spine session-start policy
  .obsidian/graph.json       ← Spine color groups
```

See [spine-integration.md](../../../docs/how-to/spine-integration.md) in AOA Financial for
the full three-repo stack.
