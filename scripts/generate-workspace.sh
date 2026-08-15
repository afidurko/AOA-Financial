#!/usr/bin/env bash
# Generate a multi-root Cursor/VS Code workspace that bundles AOA Financial with
# its sibling integrations and the shared vault. Only folders that exist are
# included. Extra workspace roots may be passed as additional arguments.
#
# Usage:
#   ./scripts/generate-workspace.sh                       # -> aoa-stack.code-workspace
#   ./scripts/generate-workspace.sh out.code-workspace    # custom output path
#   ./scripts/generate-workspace.sh out.code-workspace /path/to/other/repo ...
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=scripts/lib/env-file.sh
source "$ROOT/scripts/lib/env-file.sh"

OUT="${1:-$ROOT/aoa-stack.code-workspace}"
shift || true
EXTRA_ROOTS=("$@")

VAULT_DIR="$(resolve_vault_dir "$ROOT")"

# name|path candidates, in display order.
candidates=(
  "AOA-Financial|$ROOT"
  "obsidian-second-brain|${OBSIDIAN_SECONDBRAIN_DIR:-$ROOT/obsidian-second-brain}"
  "spine|${SPINE_DIR:-$ROOT/spine}"
  "obsidian-skills|${OBSIDIAN_SKILLS_DIR:-$ROOT/obsidian-skills}"
  "qm|${QM_DIR:-$ROOT/qm}"
  "OpenStock|$ROOT/OpenStock"
  "AOA-Vault|$VAULT_DIR"
)
for extra in "${EXTRA_ROOTS[@]}"; do
  [[ -n "$extra" ]] || continue
  abs="$(cd "$extra" 2>/dev/null && pwd)" || { echo "Skipping missing root: $extra" >&2; continue; }
  candidates+=("$(basename "$abs")|$abs")
done

# json_escape STRING -> escape backslashes and double quotes for JSON.
json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  printf '%s' "$s"
}

folders=""
count=0
for entry in "${candidates[@]}"; do
  name="${entry%%|*}"
  path="${entry#*|}"
  [[ -d "$path" ]] || continue
  [[ -n "$folders" ]] && folders="$folders,"
  folders="$folders
    { \"name\": \"$(json_escape "$name")\", \"path\": \"$(json_escape "$path")\" }"
  count=$((count + 1))
done

cat >"$OUT" <<EOF
{
  "folders": [$folders
  ],
  "settings": {
    "files.exclude": {
      "**/.git": true,
      "**/__pycache__": true
    }
  }
}
EOF

echo "Wrote $OUT ($count folders)"
echo "Open in Cursor: File → Open Workspace from File… → $OUT"
