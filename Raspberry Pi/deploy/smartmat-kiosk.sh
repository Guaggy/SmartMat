#!/bin/sh
# Touchscreen kiosk: the SmartMat dashboard fullscreen in Chromium, started at login by smartmat-kiosk.desktop.
# Close it by tapping the logo 5 times within 3 s (or Alt+F4 with a keyboard, or `pkill -f smartmat-kiosk-profile` over ssh).
URL="http://localhost:8000/?kiosk"
until curl -sf http://localhost:8000/api/health >/dev/null; do sleep 2; done   # wait for the server service
BROWSER=$(command -v chromium-browser || command -v chromium)
exec "$BROWSER" --kiosk --noerrdialogs --disable-infobars --no-first-run --touch-events=enabled \
  --disable-session-crashed-bubble --overscroll-history-navigation=0 --check-for-update-interval=31536000 \
  --user-data-dir="$HOME/.config/smartmat-kiosk-profile" "$URL"
