#!/usr/bin/env bash
# Connect another repo/workspace to AOA's shared second brain.
# Links the shared obsidian-second-brain + spine + obsidian-skills Cursor skills,
# points that workspace's MCP + .env at the shared AOA-Vault, so knowledge
# compounds across all your projects.
#
# Usage:
#   ./scripts/connect-workspace.sh /path/to/other/repo
#   ./scripts/connect-workspace.sh --list          # show what would be linked
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=scripts/lib/env-file.sh
source "$ROOT/scripts/lib/env-file.sh"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

OSB_DIR="${OBSIDIAN_SECONDBRAIN_DIR:-$ROOT/obsidian-second-brain}"
SPINE_DIR="${SPINE_DIR:-$ROOT/spine}"
SKILLS_DIR="${OBSIDIAN_SKILLS_DIR:-$ROOT/obsidian-skills}"
VAULT_DIR="$(resolve_vault_dir "$ROOT")"

print_shared() {
  echo "Shared knowledge stack (from $ROOT):"
  echo "  Vault:                 $VAULT_DIR"
  echo "  obsidian-second-brain: $OSB_DIR"
  echo "  spine:                 $SPINE_DIR $([[ -d $SPINE_DIR ]] || echo '(absent)')"
  echo "  obsidian-skills:       $SKILLS_DIR $([[ -d $SKILLS_DIR ]] || echo '(absent)')"
}

if [[ "${1:-}" == "--list" ]]; then
  print_shared
  exit 0
fi

TARGET_ARG="${1:-}"
if [[ -z "$TARGET_ARG" ]]; then
  echo "Usage: ./scripts/connect-workspace.sh /path/to/other/repo" >&2
  echo "       ./scripts/connect-workspace.sh --list" >&2
  exit 1
fi

TARGET="$(cd "$TARGET_ARG" 2>/dev/null && pwd)" || {
  echo "Target workspace not found: $TARGET_ARG" >&2
  exit 1
}
if [[ "$TARGET" == "$ROOT" ]]; then
  echo "Target is the AOA repo itself — nothing to connect." >&2
  exit 1
fi

if [[ ! -d "$OSB_DIR" || ! -d "$VAULT_DIR" ]]; then
  echo "Shared second brain not set up yet." >&2
  echo "Run ./scripts/knowledge-stack-setup.sh in $ROOT first." >&2
  exit 1
fi

echo "Connecting workspace: $TARGET"
print_shared
echo ""

# 1. Link Cursor skills (shared clones) into the target workspace.
SKILLS_DST="$TARGET/.cursor/skills"
mkdir -p "$SKILLS_DST"
ln -snf "$OSB_DIR" "$SKILLS_DST/obsidian-second-brain"
echo "Linked obsidian-second-brain skill → $SKILLS_DST/obsidian-second-brain"

if [[ -d "$SPINE_DIR" ]]; then
  n="$(link_cursor_skills "$SPINE_DIR" "$SKILLS_DST")"
  echo "Linked $n spine skills → $SKILLS_DST"
fi
if [[ -d "$SKILLS_DIR" ]]; then
  n="$(link_cursor_skills "$SKILLS_DIR" "$SKILLS_DST")"
  echo "Linked $n obsidian-skills → $SKILLS_DST"
fi

# 2. Point the target's MCP server at the shared vault (absolute paths so it
#    resolves regardless of the workspace's own working directory).
TARGET_MCP="$TARGET/.cursor/mcp.json"
if [[ -f "$TARGET_MCP" ]]; then
  cp "$TARGET_MCP" "$TARGET_MCP.bak.$(date +%s)"
  echo "Backed up existing $TARGET_MCP"
fi
cat >"$TARGET_MCP" <<EOF
{
  "mcpServers": {
    "obsidian-second-brain": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "$OSB_DIR",
        "--with",
        "mcp",
        "python",
        "integrations/obsidian-mcp-server/server.py"
      ],
      "env": {
        "OBSIDIAN_VAULT_PATH": "$VAULT_DIR"
      }
    }
  }
}
EOF
echo "Wrote $TARGET_MCP (shared vault)"

# 3. Record the shared vault in the target's .env (absolute path).
TARGET_ENV="$TARGET/.env"
env_upsert AOA_OBSIDIAN_VAULT_PATH "$VAULT_DIR" "$TARGET_ENV"
[[ -d "$SPINE_DIR" ]] && env_upsert AOA_SPINE_ENABLED "true" "$TARGET_ENV"
echo "Recorded vault path in $TARGET_ENV"

echo ""
echo "Workspace connected."
echo "Next in that workspace:"
echo "  1. Restart Cursor so it loads .cursor/mcp.json + skills"
echo "  2. Run /obsidian-architect to document this project into the shared vault"
echo "  3. Run /spine-capture after commits to draft feature docs"
echo ""
echo "Tip: open everything together with ./scripts/generate-workspace.sh"
