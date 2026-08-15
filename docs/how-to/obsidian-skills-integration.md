# obsidian-skills integration

[obsidian-skills](https://github.com/afidurko/obsidian-skills) teaches agents
Obsidian-native formats: Flavored Markdown, Bases, JSON Canvas, CLI, and Defuddle.
obsidian-second-brain **learns from** these skills when reading and writing vault files.

## Role in the stack

```
obsidian-skills          ← format syntax (wikilinks, .base, .canvas, CLI)
        ↓ learned by
obsidian-second-brain    ← AI-first vault operations (save, ingest, research)
        ↓ shared vault
AOA-Vault/Knowledge/Obsidian Skills Reference.md
```

Spine and obsidian-skills are complementary: Spine tracks commit-driven feature docs;
obsidian-skills teaches obsidian-second-brain how to write valid Obsidian files.

## Setup

Full stack (includes obsidian-skills):

```bash
./scripts/knowledge-stack-setup.sh
```

Or obsidian-skills only (after obsidian-second-brain is installed):

```bash
./scripts/obsidian-skills-setup.sh
./scripts/integrate-obsidian-skills.sh
```

## Skills linked

| Skill | Purpose |
|-------|---------|
| obsidian-markdown | Wikilinks, callouts, properties, embeds in `.md` |
| obsidian-bases | Database views in `.base` files |
| json-canvas | Visual canvases in `.canvas` files |
| obsidian-cli | Vault CLI when Obsidian desktop is running |
| defuddle | Clean web page extraction before ingest |

All five link into `.cursor/skills/` and are indexed in the vault at
`Knowledge/Obsidian Skills Reference.md`.

## What obsidian-second-brain learns

The bridge (`obsidian-second-brain/integrations/obsidian-skills/`):

1. Writes the vault knowledge index with skill descriptions and usage cues
2. Appends a **Companion skills — obsidian-skills** section to `_CLAUDE.md`
3. Copies `references/obsidian-skills-companion.md` into the obsidian-second-brain clone

When you run `/obsidian-init`, `/obsidian-save`, or `/obsidian-ingest`, the agent should
read the companion skills for correct Obsidian syntax.

## Verify

```bash
test -d obsidian-skills/skills/obsidian-markdown
test -f obsidian-second-brain/integrations/obsidian-skills/setup.sh
test -f AOA-Vault/Knowledge/Obsidian\ Skills\ Reference.md
ls -la .cursor/skills/obsidian-markdown
```

## Notes

- Default clone: `https://github.com/afidurko/obsidian-skills.git` (fork of kepano/obsidian-skills)
- Override with `OBSIDIAN_SKILLS_REPO` or `OBSIDIAN_SKILLS_DIR`
- See [obsidian-second-brain-integration.md](obsidian-second-brain-integration.md) for vault + MCP setup
