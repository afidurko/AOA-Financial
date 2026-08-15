#!/usr/bin/env bash
# Write AOA.code-workspace including sibling knowledge-stack folders that exist.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/AOA.code-workspace}"

folders=()
add_folder() {
  local name="$1"
  local rel="$2"
  if [[ -d "$ROOT/$rel" ]]; then
    folders+=("$(python3 -c 'import json,sys; print(json.dumps({"name":sys.argv[1],"path":sys.argv[2]}))' "$name" "$rel")")
  fi
}

add_folder "AOA-Financial" "."
add_folder "AOA-Vault" "AOA-Vault"
add_folder "obsidian-second-brain" "obsidian-second-brain"
add_folder "spine" "spine"
add_folder "obsidian-skills" "obsidian-skills"
add_folder "qm" "qm"
add_folder "py-moomoo-api" "py-moomoo-api"
add_folder "SGX-OrderBook" "SGX-Full-OrderBook-Tick-Data-Trading-Strategy"

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
