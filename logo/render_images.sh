#!/bin/sh
# Redraw the PNG icons and the social card from the SVGs, using headless Chrome. Run it after changing
# goodtimes-icon.svg, goodtimes.svg or og-image.html, then commit the PNGs (the build only copies them).
set -e
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

shot() {  # shot <out.png> <width> <height> <file> [background]
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --default-background-color="${5:-00000000}" --window-size="$2,$3" --screenshot="$PWD/$1" "file://$PWD/$4" \
    2>/dev/null
}

# Headless Chrome won't open a window narrower than about 500px, so icons render at 512 and sips scales them down.
shot icon-512.png 512 512 goodtimes-icon.svg                   # transparent, edge to edge
sips -z 48 48 icon-512.png --out favicon-48.png >/dev/null     # browser tabs and Google results
shot icon-512.png 512 512 icon-tile.html FFFFFFFF              # the G on white, for the web app manifest
sips -z 192 192 icon-512.png --out icon-192.png >/dev/null
sips -z 180 180 icon-512.png --out apple-touch-icon.png >/dev/null  # iOS home screen (no transparency)
shot og-image.png 1200 630 og-image.html FFFFFFFF              # link previews
echo "Wrote favicon-48.png, icon-192.png, icon-512.png, apple-touch-icon.png and og-image.png"
