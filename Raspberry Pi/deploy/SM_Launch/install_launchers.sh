#!/bin/sh
# Creates ~/Desktop/SM_Launch with three icons and the README, and a `smartmat` command in ~/.local/bin.
# Safe to run again (smartmat_ctl.py update does). The icons point into this checkout, so a git pull updates them.
HERE=$(cd "$(dirname "$0")" && pwd)
APP=$(cd "$HERE/../.." && pwd)
DEST="${1:-$HOME/Desktop/SM_Launch}"
mkdir -p "$DEST" "$HOME/.local/bin"
chmod +x "$HERE"/*.sh "$HERE/smartmat_ctl.py" "$APP/deploy/smartmat-kiosk.sh"

icon() { # file, name, comment, command, icon, terminal
  cat > "$DEST/$1" <<DESK
[Desktop Entry]
Type=Application
Name=$2
Comment=$3
Exec=$4
Icon=$5
Terminal=$6
DESK
  chmod +x "$DEST/$1"
  gio set "$DEST/$1" metadata::trusted true 2>/dev/null
}
icon "1 Web dashboard (fullscreen).desktop" "1 Web dashboard (fullscreen)" "The touchscreen dashboard, as at boot" \
  "sh \"$APP/deploy/smartmat-kiosk.sh\"" web-browser false
icon "2 Desktop dashboard (advanced).desktop" "2 Desktop dashboard (advanced)" "Calibration, analysis, recordings" \
  "sh \"$HERE/desktop-dashboard.sh\"" utilities-system-monitor false
icon "3 SmartMat config (terminal).desktop" "3 SmartMat config (terminal)" "Status, boot options, simulations, restart, update" \
  "python3 \"$HERE/smartmat_ctl.py\"" utilities-terminal true
cp "$HERE/README.txt" "$DEST/README.txt"
ln -sf "$HERE/smartmat_ctl.py" "$HOME/.local/bin/smartmat"
echo "Launchers in $DEST ; terminal command: smartmat (or python3 $HERE/smartmat_ctl.py)"
