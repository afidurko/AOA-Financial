#!/usr/bin/env bash
# Open .env in TextEdit to edit API keys. Double-click in Finder.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
if [[ ! -f .env ]]; then
  cp .env.example .env
fi
open -e .env
echo "Edit ANTHROPIC_API_KEY in TextEdit, then Save (Cmd+S)."
read -r -p "Press Enter to close..."
