#!/usr/bin/env bash
# Clone the ant-design-mobile sibling beside the repo (UI kit reference — not vendored).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANTD_MOBILE_DIR="${ANTD_MOBILE_DIR:-$ROOT/ant-design-mobile}"
ANTD_MOBILE_REPO="${ANTD_MOBILE_REPO:-https://github.com/afidurko/ant-design-mobile.git}"

# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

if [[ -e "$ANTD_MOBILE_DIR" && ! -d "$ANTD_MOBILE_DIR/.git" ]]; then
  echo "error: $ANTD_MOBILE_DIR exists but is not a git clone; remove or set ANTD_MOBILE_DIR elsewhere" >&2
  exit 1
fi

git_clone_if_missing "$ANTD_MOBILE_DIR" "$ANTD_MOBILE_REPO" "ant-design-mobile"

echo ""
echo "ant-design-mobile sibling ready (UI kit — not started by AOA, never places orders)."
echo "  Docs: docs/how-to/antd-mobile-integration.md"
echo "  Built-in mobile shell: aoa serve → http://localhost:8080/m"
echo "  Optional header link: export AOA_ANTD_MOBILE_URL=https://github.com/afidurko/ant-design-mobile"
echo "  Upstream: https://github.com/ant-design/ant-design-mobile · https://mobile.ant.design"
echo "  Safety: paper/dashboard only; never wire UI gestures into live order submission."
