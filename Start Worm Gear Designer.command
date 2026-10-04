#!/bin/sh
# Double-click (macOS Finder or Linux file manager) to open the dashboard. Needs Python 3.9+.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
    exec python3 app.py
fi
echo "Python 3 was not found. Install it from https://www.python.org/downloads/"
read -r _
