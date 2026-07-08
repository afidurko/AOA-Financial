#!/usr/bin/env bash
# Clone obsidian-skills beside the repo and link Cursor skills.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_REPO_DIR="${OBSIDIAN_SKILLS_DIR:-$ROOT/obsidian-skills}"
SKILLS_REPO="${OBSIDIAN_SKILLS_REPO:-https://github.com/afidurko/obsidian-skills.git}"
CURSOR_SKILLS="$ROOT/.cursor/skills"

if [[ ! -d "$SKILLS_REPO_DIR/.git" ]]; then
  echo "Cloning obsidian-skills into $SKILLS_REPO_DIR"
  git clone "$SKILLS_REPO" "$SKILLS_REPO_DIR"
else
  echo "obsidian-skills already present at $SKILLS_REPO_DIR"
fi

mkdir -p "$CURSOR_SKILLS"
linked=0
for skill_dir in "$SKILLS_REPO_DIR"/skills/*/; do
  [[ -d "$skill_dir" ]] || continue
  name="$(basename "$skill_dir")"
  ln -snf "$skill_dir" "$CURSOR_SKILLS/$name"
  linked=$((linked + 1))
done

echo ""
echo "obsidian-skills ready."
echo "  Repo:   $SKILLS_REPO_DIR"
echo "  Linked: $linked skills (obsidian-markdown, obsidian-bases, json-canvas, obsidian-cli, defuddle)"
echo ""
echo "Next: ./scripts/integrate-obsidian-skills.sh  — teach obsidian-second-brain"
