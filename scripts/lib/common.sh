#!/usr/bin/env bash
# Shared shell helpers for AOA setup scripts. Source this file; do not execute it.

# git_clone_if_missing DIR REPO LABEL
#   Clone REPO into DIR unless DIR is already a git checkout.
git_clone_if_missing() {
  local dir="$1" repo="$2" label="$3"
  if [[ -d "$dir/.git" ]]; then
    echo "$label already present at $dir"
  else
    echo "Cloning $label into $dir"
    git clone "$repo" "$dir"
  fi
}

# link_cursor_skills REPO DEST_DIR
#   Symlink every skill under REPO/skills/*/ into DEST_DIR. Prints the count.
link_cursor_skills() {
  local repo="$1" dest="$2" linked=0 skill_dir name
  mkdir -p "$dest"
  for skill_dir in "$repo"/skills/*/; do
    [[ -d "$skill_dir" ]] || continue
    name="$(basename "$skill_dir")"
    ln -snf "$skill_dir" "$dest/$name"
    linked=$((linked + 1))
  done
  printf '%s' "$linked"
}
