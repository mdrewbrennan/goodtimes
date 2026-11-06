#!/bin/sh
# Redraw the PNG icons and the social card from the SVGs, using headless Chrome. Run it after changing
# the script logo, icon-g.html, goodtimes.svg or og-image.html, then commit the PNGs (the build only copies them).
set -e
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

shot() {  # shot <out.png> <width> <height> <file> [background]
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --default-background-color="${5:-00000000}" --window-size="$2,$3" --screenshot="$PWD/$1" "file://$PWD/$4" \
    2>/dev/null
}

# Headless Chrome won't open a window narrower than about 500px, so icons render at 512 and sips scales them down.
shot goodtimes-g.png 512 512 icon-g.html                       # the logo's G, transparent
sips -z 48 48 goodtimes-g.png --out favicon-48.png >/dev/null  # browser tabs and Google results
# The SVG tab icon wraps a 128px copy of the G, so it stays the original artwork rather than a redrawing.
sips -z 128 128 goodtimes-g.png --out /tmp/goodtimes-g-128.png >/dev/null
printf '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 128 128" role="img" aria-label="GOODTIMES"><image width="128" height="128" xlink:href="data:image/png;base64,%s"/></svg>\n' \
  "$(base64 < /tmp/goodtimes-g-128.png | tr -d '\n')" > goodtimes-icon.svg
shot icon-512.png 512 512 icon-tile.html FFF7EFFF              # the G on cream, for the web app manifest
sips -z 192 192 icon-512.png --out icon-192.png >/dev/null
sips -z 180 180 icon-512.png --out apple-touch-icon.png >/dev/null  # iOS home screen (no transparency)
shot og-image.png 1200 630 og-image.html FFFFFFFF              # link previews
echo "Wrote goodtimes-g.png, goodtimes-icon.svg, favicon-48.png, icon-192.png, icon-512.png, apple-touch-icon.png and og-image.png"
