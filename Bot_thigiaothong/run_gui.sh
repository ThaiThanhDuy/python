#!/bin/bash
# Launches the Mouse Corner Macro GUI app.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
xhost +si:localuser:"$(whoami)" >/dev/null 2>&1
exec "$DIR/venv/bin/python" "$DIR/gui.py"
