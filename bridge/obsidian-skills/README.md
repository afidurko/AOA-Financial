# obsidian-skills companion for obsidian-second-brain

[obsidian-skills](https://github.com/afidurko/obsidian-skills) teaches agents Obsidian-native
formats: Flavored Markdown, Bases, JSON Canvas, CLI, and Defuddle web extraction.

obsidian-second-brain **learns from** these skills when reading and writing vault files.
Apply them alongside the AI-first vault rule in `references/ai-first-rules.md`.

## When obsidian-second-brain should use each skill

| Skill | Use when |
|-------|----------|
| **obsidian-markdown** | Creating or editing `.md` notes — wikilinks, callouts, properties, embeds |
| **obsidian-bases** | Creating `.base` database views (Projects, People, Tasks boards) |
| **json-canvas** | Creating `.canvas` visual maps (`/obsidian-visualize` output) |
| **obsidian-cli** | Obsidian is running — search, create, reload plugins from CLI |
| **defuddle** | Ingesting web pages before `/obsidian-ingest` (cleaner than raw fetch) |

## Install (from AOA Financial)

```bash
./scripts/obsidian-skills-setup.sh
./scripts/integrate-obsidian-skills.sh
```

Or as part of the full stack:

```bash
./scripts/knowledge-stack-setup.sh
```

## What setup does

1. Clones `obsidian-skills` beside AOA Financial
2. Links all five skills into `.cursor/skills/`
3. Writes `Knowledge/Obsidian Skills Reference.md` in the shared vault
4. Appends a companion section to vault `_CLAUDE.md` so obsidian-second-brain loads format rules at session start
5. Installs this integration into `obsidian-second-brain/integrations/obsidian-skills/`

Skill source paths (after setup): `{AOA_ROOT}/obsidian-skills/skills/<name>/SKILL.md`

See [obsidian-skills-integration.md](../../../docs/how-to/obsidian-skills-integration.md) in AOA Financial.
