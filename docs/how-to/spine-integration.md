# Spine integration

[Spine](https://github.com/afidurko/spine) bridges AI memory to an Obsidian vault with
feature-organized spine notes, auto-capture from commits, and color-coded graph visualization.
In AOA Financial it shares **`AOA-Vault`** with
[obsidian-second-brain](obsidian-second-brain-integration.md) — Spine for commit-driven
engineering docs, obsidian-second-brain for AI-first capture and research.

## Three-repo stack

```
┌─────────────────────┐
│  AOA Financial      │  trading swarm, journal, dashboard
│  aoa serve :8080    │
└─────────┬───────────┘
          │ /spine-capture after commits
          │ /obsidian-save after team reviews
          ▼
┌─────────────────────┐     direct bridge (shared vault)
│  AOA-Vault          │◀─── integrations/spine/ in obsidian-second-brain
│  (Obsidian)         │
└─────────┬───────────┘
          │
    ┌─────┴─────┐
    ▼           ▼
  Spine     obsidian-second-brain
  feature   AI-first PARA + research
  docs      + MCP server
```

## 1. Full stack setup

One command installs obsidian-second-brain, Spine, and the direct bridge:

```bash
./scripts/knowledge-stack-setup.sh
```

Add to `.env`:

```env
AOA_OBSIDIAN_VAULT_PATH=./AOA-Vault
AOA_SPINE_ENABLED=true
```

## 2. Step-by-step

```bash
./scripts/obsidian-second-brain-setup.sh   # vault + OSB skill + MCP
./scripts/spine-setup.sh                     # Spine skills → .cursor/skills/
./scripts/integrate-spine-obsidian.sh        # direct OSB ↔ Spine bridge
./scripts/sync-spine-config.sh               # ~/.spine/config.json
```

The bridge installs `obsidian-second-brain/integrations/spine/` from AOA's
`bridge/spine-obsidian/` templates and configures:

| Config | Path | Purpose |
|--------|------|---------|
| `OBSIDIAN_VAULT_PATH` | `~/.config/obsidian-second-brain/.env` | obsidian-second-brain vault |
| `vaultPath` | `~/.spine/config.json` | Spine vault (same path) |
| `AOA_OBSIDIAN_VAULT_PATH` | AOA `.env` | Dashboard Second Brain link |

## 3. Vault layout

```
AOA-Vault/
  _CLAUDE.md                    ← obsidian-second-brain (run /obsidian-init)
  Daily/ Projects/ People/ …    ← obsidian-second-brain areas
  AOA-Financial/                ← Spine repo folder
    Swarm/Swarm.md
    Broker/Broker.md
    Work-loop/Work-loop.md
  Spine Architecture.md
  .spine/retrieval-policy.md
  .obsidian/graph.json          ← Spine color groups
```

## 4. Workflow with AOA

| When | Command | System |
|------|---------|--------|
| After a fix or feature commit | `/spine-capture` | Spine |
| After a team review cycle | `/obsidian-save` | obsidian-second-brain |
| Document codebase | `/obsidian-architect` | obsidian-second-brain |
| Deep feature context | `/spine-recall Swarm` | Spine |
| Vault health audit | `/spine-health` | Spine |
| Research a topic | `/research-deep "momentum"` | obsidian-second-brain |

Spine hooks track significant commits for batch capture when Tier 3 is enabled
(default in the bridge setup).

## 5. Run with dashboard

```bash
export AOA_OBSIDIAN_VAULT_PATH=./AOA-Vault
export AOA_SPINE_ENABLED=true
aoa serve
```

The dashboard header shows **Second Brain ↗** when the vault path is set.
`/api/config` returns `spine_enabled: true` when Spine is active.

## 6. Verify

```bash
python3 -m pytest tests/test_web.py -q
test -f ~/.spine/config.json && cat ~/.spine/config.json
test -d obsidian-second-brain/integrations/spine
test -f AOA-Vault/AOA-Financial/Swarm/Swarm.md
```

## Notes

- Default Spine clone: `https://github.com/afidurko/spine.git` (override with `SPINE_REPO`).
- Spine skills linked: `spine-init`, `spine-capture`, `spine-health`, `spine-scan`, `spine-update`, `spine-recall`.
- The direct bridge lives in obsidian-second-brain at `integrations/spine/` after setup.
- See [obsidian-second-brain-integration.md](obsidian-second-brain-integration.md) for MCP and research keys.
