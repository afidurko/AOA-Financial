#!/usr/bin/env bash
# Moomoo setup — delegates to one-step activation.
set -euo pipefail
exec "$(dirname "${BASH_SOURCE[0]}")/activate.sh" "$@"
