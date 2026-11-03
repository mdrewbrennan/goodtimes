#!/bin/sh
# Refresh listings, rebuild the pages (site/ and the netlify/ folder to upload), and open the homepage.
# The pages use site-root links (/listings/, /fonts/...), so they're served locally rather than opened as files.
set -e
cd "$(dirname "$0")"
python3 scrape.py
python3 build.py
(sleep 1 && open http://localhost:8765/) &
python3 -m http.server 8765 -d site
