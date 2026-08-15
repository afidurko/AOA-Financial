#!/usr/bin/env bash
# Write AOA.code-workspace including sibling knowledge-stack folders that exist.
# Extra external workspace roots may be passed as additional arguments (e.g. a
# repo connected via scripts/connect-workspace.sh).
#
# Usage:
#   ./scripts/write-aoa-workspace.sh
#   ./scripts/write-aoa-workspace.sh AOA.code-workspace /path/to/other/repo ...
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/AOA.code-workspace}"
shift || true
EXTRA_ROOTS=("$@")

folders=()
# add_folder NAME JSON_PATH CHECK_PATH
#   Emit a folder entry (using JSON_PATH, kept relative for in-repo folders so
#   the committed workspace stays portable) when CHECK_PATH exists on disk.
add_folder() {
  local name="$1" json_path="$2" check_path="$3"
  if [[ -d "$check_path" ]]; then
    folders+=("$(python3 -c 'import json,sys; print(json.dumps({"name":sys.argv[1],"path":sys.argv[2]}))' "$name" "$json_path")")
  fi
}

add_folder "AOA-Financial" "." "$ROOT"
add_folder "AOA-Vault" "AOA-Vault" "$ROOT/AOA-Vault"
add_folder "obsidian-second-brain" "obsidian-second-brain" "$ROOT/obsidian-second-brain"
add_folder "spine" "spine" "$ROOT/spine"
add_folder "obsidian-skills" "obsidian-skills" "$ROOT/obsidian-skills"
add_folder "qm" "qm" "$ROOT/qm"
add_folder "py-moomoo-api" "py-moomoo-api" "$ROOT/py-moomoo-api"
add_folder "SGX-OrderBook" "SGX-Full-OrderBook-Tick-Data-Trading-Strategy" \
  "$ROOT/SGX-Full-OrderBook-Tick-Data-Trading-Strategy"
add_folder "example-hftish" "example-hftish" "$ROOT/example-hftish"
add_folder "VisualHFT" "VisualHFT" "$ROOT/VisualHFT"

# External roots (absolute paths) — e.g. repos connected via connect-workspace.sh.
for extra in "${EXTRA_ROOTS[@]}"; do
  [[ -n "$extra" ]] || continue
  abs="$(cd "$extra" 2>/dev/null && pwd)" || { echo "Skipping missing root: $extra" >&2; continue; }
  add_folder "$(basename "$abs")" "$abs" "$abs"
done

python3 - "$OUT" "${folders[@]}" <<'PY'
import json, sys
out = sys.argv[1]
folders = [json.loads(s) for s in sys.argv[2:]]
doc = {
    "folders": folders,
    "settings": {
        "files.exclude": {
            "**/.pytest_cache": True,
            "**/__pycache__": True,
        }
    },
    "extensions": {
        "recommendations": ["ms-python.python", "charliermarsh.ruff"]
    },
}
with open(out, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2)
    f.write("\n")
print(f"Wrote {out} ({len(folders)} folders)")
PY
