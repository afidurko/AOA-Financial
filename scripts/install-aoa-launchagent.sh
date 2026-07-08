#!/usr/bin/env bash
# Install macOS LaunchAgent so `aoa serve` starts at login and stays running.
# Run on your Mac from the repo root:
#   ./scripts/install-aoa-launchagent.sh
#   ./scripts/install-aoa-launchagent.sh --status
#   ./scripts/install-aoa-launchagent.sh --uninstall
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.aoa.serve"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
DAEMON="$ROOT/scripts/aoa-serve-daemon.sh"
LOG_DIR="$HOME/Library/Logs"
OUT_LOG="$LOG_DIR/aoa-serve.log"
ERR_LOG="$LOG_DIR/aoa-serve.err.log"

# shellcheck source=scripts/lib/env-file.sh
source "$ROOT/scripts/lib/env-file.sh"

usage() {
  cat <<EOF
Usage: ./scripts/install-aoa-launchagent.sh [--status|--uninstall|--reload]

Installs a user LaunchAgent that runs \`aoa serve\` at login (KeepAlive).
Requires a working install: .venv + pip install -e ".[dev,web]".

Logs:
  $OUT_LOG
  $ERR_LOG
EOF
}

read_web_port() {
  local port
  port="$(env_read AOA_WEB_PORT "$ROOT/.env")"
  echo "${port:-8080}"
}

xml_escape() {
  local s="$1"
  s="${s//&/&amp;}"
  s="${s//</&lt;}"
  s="${s//>/&gt;}"
  printf '%s' "$s"
}

write_plist() {
  mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
  chmod +x "$DAEMON"
  cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>$(xml_escape "$DAEMON")</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$(xml_escape "$ROOT")</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$(xml_escape "$OUT_LOG")</string>
  <key>StandardErrorPath</key>
  <string>$(xml_escape "$ERR_LOG")</string>
</dict>
</plist>
EOF
}

load_agent() {
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  launchctl enable "gui/$(id -u)/${LABEL}" 2>/dev/null || true
  launchctl kickstart -k "gui/$(id -u)/${LABEL}" 2>/dev/null || true
}

ensure_macos() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This script is for macOS LaunchAgents only." >&2
    echo "On Linux use deploy/aoa-web.service or docker compose up -d web." >&2
    exit 1
  fi
}

ensure_prereqs() {
  if [[ ! -x "$DAEMON" ]]; then
    echo "Missing daemon wrapper: $DAEMON" >&2
    exit 1
  fi
  if [[ ! -x "$ROOT/.venv/bin/python3" ]]; then
    cat >&2 <<EOF
.venv not found. Create it first, then re-run:

  cd $ROOT
  python3.12 -m venv .venv
  source .venv/bin/activate
  pip install -e ".[dev,web]"
  ./scripts/install-aoa-launchagent.sh
EOF
    exit 1
  fi
  if ! "$ROOT/.venv/bin/python3" -m aoa.cli --help >/dev/null 2>&1; then
    echo "aoa CLI not installed in .venv — run: pip install -e \".[dev,web]\"" >&2
    exit 1
  fi
}

unload_agent() {
  if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
  fi
}

install_agent() {
  ensure_macos
  ensure_prereqs
  write_plist
  unload_agent
  load_agent

  local port
  port="$(read_web_port)"
  echo "Installed LaunchAgent: $PLIST"
  echo "Dashboard (local): http://127.0.0.1:${port}/"
  echo "Logs: $OUT_LOG"
  echo ""
  echo "Remote access: ./scripts/setup-tailscale-access.sh"
  echo "Or full stack: ./scripts/setup-always-on.sh"
}

status_agent() {
  ensure_macos
  if [[ ! -f "$PLIST" ]]; then
    echo "Not installed ($PLIST missing)."
    exit 1
  fi
  echo "Plist: $PLIST"
  if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    launchctl print "gui/$(id -u)/${LABEL}" | head -20
  else
    launchctl list | grep -F "$LABEL" || echo "Agent not loaded."
  fi
  local port
  port="$(read_web_port)"
  echo ""
  echo "Health check: curl -sf http://127.0.0.1:${port}/health && echo OK"
}

uninstall_agent() {
  ensure_macos
  unload_agent
  rm -f "$PLIST"
  echo "Removed $PLIST"
}

case "${1:-}" in
  --status)
    status_agent
    ;;
  --uninstall)
    uninstall_agent
    ;;
  --reload)
    ensure_macos
    ensure_prereqs
    write_plist
    unload_agent
    load_agent
    echo "Reloaded ${LABEL}"
    ;;
  -h|--help)
    usage
    ;;
  "")
    install_agent
    ;;
  *)
    echo "Unknown option: $1" >&2
    usage >&2
    exit 1
    ;;
esac
