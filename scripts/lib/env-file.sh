#!/usr/bin/env bash
# Shared .env read/upsert helpers. Source this file; do not execute it.
# Portable across macOS (bash 3.2 / BSD tools) and Linux — uses awk, not sed -i.

# env_read KEY FILE
#   Print the value of KEY from FILE (first match), with surrounding quotes
#   stripped. Prints nothing if the file or key is absent.
env_read() {
  local key="$1" file="$2" val
  [[ -f "$file" ]] || return 0
  val="$(grep -E "^${key}=" "$file" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  val="${val%\"}"; val="${val#\"}"
  val="${val%\'}"; val="${val#\'}"
  printf '%s' "$val"
}

# env_upsert KEY VALUE FILE
#   Set KEY=VALUE in FILE, replacing an existing line or appending a new one.
#   Creates FILE (and parent dirs) if missing. Idempotent.
#   Rewrites in place (cat over the original) so file permissions — e.g. a
#   chmod 600 on a secrets file — are preserved.
env_upsert() {
  local key="$1" value="$2" file="$3"
  [[ -n "$file" ]] || return 1
  mkdir -p "$(dirname "$file")"
  [[ -f "$file" ]] || : >"$file"
  awk -v key="$key" -v val="$value" '
    $0 ~ "^" key "=" { print key "=" val; done = 1; next }
    { print }
    END { if (!done) print key "=" val }
  ' "$file" >"$file.tmp" && cat "$file.tmp" >"$file" && rm -f "$file.tmp"
}
