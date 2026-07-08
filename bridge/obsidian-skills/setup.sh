#!/usr/bin/env bash
# Teach obsidian-second-brain to use obsidian-skills format companions.
# Installed to obsidian-second-brain/integrations/obsidian-skills/ by AOA setup.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OSB_ROOT="$(cd "$HERE/../.." && pwd)"
ROOT="${AOA_ROOT:-$(cd "$OSB_ROOT/.." 2>/dev/null && pwd || echo "$OSB_ROOT/..")}"
SKILLS_DIR="${OBSIDIAN_SKILLS_DIR:-$ROOT/obsidian-skills}"
VAULT_DIR="${AOA_OBSIDIAN_VAULT_PATH:-${OBSIDIAN_VAULT_PATH:-$ROOT/AOA-Vault}}"
CURSOR_SKILLS="${CURSOR_SKILLS:-$ROOT/.cursor/skills}"
MARKER="Companion skills — obsidian-skills"

green() { printf '\033[0;32m%s\033[0m\n' "$1"; }
yellow() { printf '\033[0;33m%s\033[0m\n' "$1"; }

if [[ ! -d "$SKILLS_DIR/skills" ]]; then
  echo "obsidian-skills missing at $SKILLS_DIR — run ./scripts/obsidian-skills-setup.sh first." >&2
  exit 1
fi

if [[ ! -d "$VAULT_DIR" ]]; then
  echo "Vault missing at $VAULT_DIR — run obsidian-second-brain setup first." >&2
  exit 1
fi

mkdir -p "$CURSOR_SKILLS"
linked=0
for skill_dir in "$SKILLS_DIR"/skills/*/; do
  [[ -d "$skill_dir" ]] || continue
  name="$(basename "$skill_dir")"
  ln -snf "$skill_dir" "$CURSOR_SKILLS/$name"
  linked=$((linked + 1))
done
green "Linked $linked obsidian-skills into $CURSOR_SKILLS"

# Vault knowledge index (AI-first; obsidian-second-brain reads this)
mkdir -p "$VAULT_DIR/Knowledge"
KNOWLEDGE="$VAULT_DIR/Knowledge/Obsidian Skills Reference.md"
{
  echo "---"
  echo "type: reference"
  echo "tags:"
  echo "  - knowledge"
  echo "  - obsidian-skills"
  echo "  - integration"
  echo "ai-first: true"
  echo "date: $(date -u +%Y-%m-%d)"
  echo "---"
  echo
  echo "## For future Claude"
  echo
  echo "Index of obsidian-skills companion packages. obsidian-second-brain uses these"
  echo "for Obsidian-native syntax when creating or editing vault files. Skill sources"
  echo "live at \`obsidian-skills/skills/<name>/SKILL.md\` beside AOA Financial."
  echo
  echo "# Obsidian Skills Reference"
  echo
  for skill_dir in "$SKILLS_DIR"/skills/*/; do
    [[ -f "$skill_dir/SKILL.md" ]] || continue
    name="$(basename "$skill_dir")"
    desc="$(awk -F': ' '/^description:/{sub(/^description: /,""); print; exit}' "$skill_dir/SKILL.md")"
    echo "## $name"
    echo
    echo "$desc"
    echo
    echo "- Skill path: \`obsidian-skills/skills/$name/SKILL.md\`"
    echo "- Read before: editing \`.md\` (markdown), \`.base\` (bases), \`.canvas\` (canvas), CLI ops, web ingest"
    echo
  done
  echo "## Integration with obsidian-second-brain"
  echo
  echo "- \`/obsidian-init\` — use **obsidian-markdown** + **obsidian-bases** when generating _CLAUDE.md and Bases/"
  echo "- \`/obsidian-save\`, \`/obsidian-ingest\` — use **obsidian-markdown**; URLs via **defuddle** first"
  echo "- \`/obsidian-visualize\` — output **json-canvas** format"
  echo "- Live vault ops — **obsidian-cli** when Obsidian desktop is running"
} >"$KNOWLEDGE"
green "Wrote $KNOWLEDGE"

# Append companion section to _CLAUDE.md (idempotent)
CLAUDE_MD="$VAULT_DIR/_CLAUDE.md"
SNIPPET="$HERE/claude-md-snippet.md"
if [[ -f "$CLAUDE_MD" ]] && grep -qF "$MARKER" "$CLAUDE_MD"; then
  yellow "_CLAUDE.md already references obsidian-skills — skipping append"
elif [[ -f "$CLAUDE_MD" ]] && [[ -f "$SNIPPET" ]]; then
  {
    echo ""
    echo "---"
    cat "$SNIPPET"
  } >>"$CLAUDE_MD"
  green "Appended obsidian-skills section to $CLAUDE_MD"
elif [[ -f "$SNIPPET" ]]; then
  cp "$SNIPPET" "$CLAUDE_MD"
  green "Created $CLAUDE_MD from obsidian-skills snippet (run /obsidian-init for full manual)"
fi

# Pointer for obsidian-second-brain skill readers
COMPANION="$OSB_ROOT/references/obsidian-skills-companion.md"
if [[ -d "$OSB_ROOT/references" ]]; then
  cp "$HERE/claude-md-snippet.md" "$COMPANION"
  green "Wrote $COMPANION (obsidian-second-brain references/)"
fi

echo ""
green "obsidian-second-brain ↔ obsidian-skills bridge ready."
echo "  Vault index: $KNOWLEDGE"
echo "  Skills repo: $SKILLS_DIR"
