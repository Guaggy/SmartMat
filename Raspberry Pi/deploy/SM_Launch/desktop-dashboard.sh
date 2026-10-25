#!/bin/sh
# The advanced desktop dashboard (Tk app: calibration, analysis, recordings). It needs the Pi's screen, so the fullscreen
# web kiosk is closed first (it would cover the window).
cd "$(dirname "$0")/../.." || exit 1
export DISPLAY="${DISPLAY:-:0}" WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
pgrep -f "[.]venv/bin/python main.py" >/dev/null && exit 0   # already running
pkill -f "[s]martmat-kiosk-profile"
sleep 1
exec .venv/bin/python main.py
