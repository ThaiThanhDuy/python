#!/bin/bash
# One-time setup: registers "Mouse Corner Macro" in your desktop's application
# menu so you can just click its icon to run it (no terminal needed).
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"

DESKTOP_FILE="$APPS_DIR/mouse-corner-macro.desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Mouse Corner Macro
Comment=Detect screen size and move the mouse to its 4 corners
Exec=$DIR/run_gui.sh
Icon=input-mouse
Terminal=false
Categories=Utility;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE" "$DIR/run_gui.sh"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi

echo "Installed. Search for 'Mouse Corner Macro' in your application menu / Activities."
