#!/usr/bin/env bash
# Clone obsidian-skills beside the repo and link Cursor skills.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_REPO_DIR="${OBSIDIAN_SKILLS_DIR:-$ROOT/obsidian-skills}"
SKILLS_REPO="${OBSIDIAN_SKILLS_REPO:-https://github.com/afidurko/obsidian-skills.git}"
CURSOR_SKILLS="$ROOT/.cursor/skills"

# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

git_clone_if_missing "$SKILLS_REPO_DIR" "$SKILLS_REPO" "obsidian-skills"

linked="$(link_cursor_skills "$SKILLS_REPO_DIR" "$CURSOR_SKILLS")"

echo ""
echo "obsidian-skills ready."
echo "  Repo:   $SKILLS_REPO_DIR"
echo "  Linked: $linked skills (obsidian-markdown, obsidian-bases, json-canvas, obsidian-cli, defuddle)"
echo ""
echo "Next: ./scripts/integrate-obsidian-skills.sh  — teach obsidian-second-brain"
