#!/usr/bin/env bash
# Clone obsidian-second-brain beside the repo, seed a vault, wire Cursor skill + MCP.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OSB_DIR="${OBSIDIAN_SECONDBRAIN_DIR:-$ROOT/obsidian-second-brain}"
OSB_REPO="${OBSIDIAN_SECONDBRAIN_REPO:-https://github.com/afidurko/obsidian-second-brain.git}"
VAULT_DIR="${AOA_OBSIDIAN_VAULT_PATH:-$ROOT/AOA-Vault}"
CURSOR_SKILLS="$ROOT/.cursor/skills"
CURSOR_MCP="$ROOT/.cursor/mcp.json"

if [[ ! -d "$OSB_DIR/.git" ]]; then
  echo "Cloning obsidian-second-brain into $OSB_DIR"
  git clone "$OSB_REPO" "$OSB_DIR"
else
  echo "obsidian-second-brain already present at $OSB_DIR"
fi

if [[ ! -d "$VAULT_DIR" ]]; then
  echo "Creating AOA vault at $VAULT_DIR"
  mkdir -p "$VAULT_DIR"
  if [[ -d "$OSB_DIR/examples/sample-vault" ]]; then
    cp -R "$OSB_DIR/examples/sample-vault/." "$VAULT_DIR/"
    echo "  Seeded from obsidian-second-brain sample vault"
  fi
else
  echo "Vault already present at $VAULT_DIR"
fi

if [[ -x "$ROOT/scripts/sync-obsidian-second-brain-env.sh" ]]; then
  AOA_OBSIDIAN_VAULT_PATH="$VAULT_DIR" "$ROOT/scripts/sync-obsidian-second-brain-env.sh"
fi

mkdir -p "$CURSOR_SKILLS"
SKILL_LINK="$CURSOR_SKILLS/obsidian-second-brain"
if [[ -L "$SKILL_LINK" || -d "$SKILL_LINK" ]]; then
  ln -snf "$OSB_DIR" "$SKILL_LINK"
  echo "Refreshed Cursor skill link: $SKILL_LINK -> $OSB_DIR"
else
  ln -s "$OSB_DIR" "$SKILL_LINK"
  echo "Linked Cursor skill: $SKILL_LINK -> $OSB_DIR"
fi

mkdir -p "$ROOT/.cursor"
cat >"$CURSOR_MCP" <<EOF
{
  "mcpServers": {
    "obsidian-second-brain": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "mcp",
        "python",
        "obsidian-second-brain/integrations/obsidian-mcp-server/server.py"
      ],
      "env": {
        "OBSIDIAN_VAULT_PATH": "${VAULT_DIR}"
      }
    }
  }
}
EOF
echo "Wrote $CURSOR_MCP"

if command -v uv >/dev/null 2>&1; then
  echo "Installing obsidian-second-brain Python deps (uv sync)…"
  (cd "$OSB_DIR" && uv sync --quiet)
else
  echo "uv not found — skip Python deps (install uv for /research and MCP server)"
fi

echo ""
echo "obsidian-second-brain ready."
echo "  Vault:  $VAULT_DIR"
echo "  Skill:  $OSB_DIR (linked into .cursor/skills/)"
echo ""
echo "Add to .env (if not already set):"
echo "  AOA_OBSIDIAN_VAULT_PATH=$VAULT_DIR"
echo ""
echo "Next steps in Cursor:"
echo "  1. Open the vault in Obsidian (Open folder as vault → $VAULT_DIR)"
echo "  2. Run /obsidian-init in the vault to generate _CLAUDE.md"
echo "  3. Run /obsidian-architect on this repo to document AOA in the vault"
echo "  4. Restart Cursor so the MCP server picks up the vault path"
