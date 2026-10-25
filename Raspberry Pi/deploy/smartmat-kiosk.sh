#!/bin/sh
# Touchscreen kiosk: the SmartMat dashboard fullscreen in Chromium. Started at login by smartmat-kiosk.desktop, or by hand
# (SM_Launch icon, `smartmat_ctl.py web start`). Close it by holding the logo 3 s, or tapping it 5 times within 4 s
# (or Alt+F4 with a keyboard, or `smartmat_ctl.py web stop`).
URL="http://localhost:8000/?kiosk"
# a launch from ssh or a terminal without a desktop environment still has to reach the Pi's screen
export DISPLAY="${DISPLAY:-:0}" WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
pgrep -f "[s]martmat-kiosk-profile" >/dev/null && exit 0     # already running
until curl -sf http://localhost:8000/api/health >/dev/null; do sleep 2; done   # wait for the server service
BROWSER=$(command -v chromium-browser || command -v chromium)
exec "$BROWSER" --kiosk --noerrdialogs --disable-infobars --no-first-run --touch-events=enabled --disable-pinch \
  --disable-session-crashed-bubble --overscroll-history-navigation=0 --check-for-update-interval=31536000 \
  --disable-features=Translate --password-store=basic \
  --user-data-dir="$HOME/.config/smartmat-kiosk-profile" "$URL"
