# Moomoo OpenD Skills (vendored)

Official Moomoo API agent skills from
https://openapi.moomoo.com/skills/opend-skills.zip
(docs: https://openapi.moomoo.com/moomoo-api-doc/en/intro/ai.html).

| Skill | Role |
|-------|------|
| `moomooapi` | Market data & trading via OpenD + `moomoo-api` |
| `install-moomoo-opend` | Download/install OpenD and upgrade the SDK |

Also mirrored to `.claude/skills/` for Claude Code. Cursor rules stubs:
`.cursor/rules/moomooapi.mdc`, `.cursor/rules/install-moomoo-opend.mdc`.

To refresh:

```bash
curl -fsSL -o /tmp/opend-skills.zip https://openapi.moomoo.com/skills/opend-skills.zip
unzip -o /tmp/opend-skills.zip -d /tmp/opend-skills
cp -a /tmp/opend-skills/skills/moomooapi .cursor/skills/
cp -a /tmp/opend-skills/skills/install-moomoo-opend .cursor/skills/
cp -a /tmp/opend-skills/skills/LEGAL*.md .cursor/skills/
cp -a /tmp/opend-skills/skills/moomooapi .claude/skills/
cp -a /tmp/opend-skills/skills/install-moomoo-opend .claude/skills/
```
