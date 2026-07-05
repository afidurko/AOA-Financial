#!/usr/bin/env bash
# Install Moomoo OpenD GUI on macOS (from official tar.gz).
# Run on your Mac: bash scripts/install_moomoo_opend_macos.sh
# Optional: bash scripts/install_moomoo_opend_macos.sh /path/to/install/dir
set -euo pipefail

INSTALL_DIR="${1:-$HOME/Desktop}"
ARCHIVE="$INSTALL_DIR/MoomooOpenD.tar.gz"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script must run on macOS (OpenD GUI + hdiutil)." >&2
  exit 1
fi

echo "=== Step 1: latest OpenD filename ==="
LOCATION=$(
  curl -sI -A "$UA" "https://www.moomoo.com/download/fetch-lasted-link?name=opend-macos" \
    | grep -i "^location:" | awk '{print $2}' | tr -d '\r'
)
if [[ -z "$LOCATION" || "$LOCATION" == *"/403"* ]]; then
  echo "fetch-lasted-link failed; using fallback 10.8.6808" >&2
  LOCATION="https://softwaredownload.futustatic.com/moomoo_OpenD_10.8.6808_Mac.tar.gz"
fi
FILENAME=$(basename "$LOCATION")
echo "Download URL: $LOCATION"
echo "Filename: $FILENAME"

echo ""
echo "=== Step 2: download (~374MB) ==="
mkdir -p "$INSTALL_DIR"
rm -f "$ARCHIVE"
rm -rf "$INSTALL_DIR"/moomoo_OpenD_*_Mac
curl -L -A "$UA" -o "$ARCHIVE" "$LOCATION"
du -h "$ARCHIVE"

echo ""
echo "=== Step 3: extract ==="
tar -xzf "$ARCHIVE" -C "$INSTALL_DIR/" && rm -f "$ARCHIVE"

echo ""
echo "=== Step 4: mount .dmg and install GUI to /Applications ==="
DMG_PATH=$(find "$INSTALL_DIR" -maxdepth 3 -name "*OpenD-GUI*.dmg" -type f | head -1)
if [[ -z "$DMG_PATH" ]]; then
  echo "No *OpenD-GUI*.dmg found under $INSTALL_DIR" >&2
  exit 1
fi
echo "Found DMG: $DMG_PATH"
VOLUME_PATH=$(hdiutil attach "$DMG_PATH" -nobrowse | grep "/Volumes" | awk -F'\t' '{print $NF}')
echo "Mounted: $VOLUME_PATH"
APP_IN_DMG=$(find "$VOLUME_PATH" -maxdepth 1 -name "*.app" -type d | head -1)
echo "Found app: $APP_IN_DMG"
cp -R "$APP_IN_DMG" /Applications/
APP_NAME=$(basename "$APP_IN_DMG")
xattr -rd com.apple.quarantine "/Applications/$APP_NAME" 2>/dev/null || true
hdiutil detach "$VOLUME_PATH"
echo "Installed: /Applications/$APP_NAME"

echo ""
echo "=== Step 5: launch GUI ==="
open "/Applications/$APP_NAME"

FIXRUN=$(find "$INSTALL_DIR" -maxdepth 3 -name "fixrun.sh" | head -1)
if [[ -n "$FIXRUN" ]]; then
  echo "If OpenD shows path errors, run: bash $FIXRUN"
fi

echo ""
echo "=== Step 6: cleanup extracted dir ==="
EXTRACT_DIR=$(find "$INSTALL_DIR" -maxdepth 1 -type d -name "*OpenD*" | head -1)
if [[ -n "$EXTRACT_DIR" ]]; then
  rm -rf "$EXTRACT_DIR"
  echo "Cleaned up: $EXTRACT_DIR"
fi

echo ""
echo "Done. Log in to OpenD, then from AOA repo:"
echo "  python3 -m aoa.cli doctor"
echo "  python3 -m aoa.cli run"
