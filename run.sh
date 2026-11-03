#!/bin/sh
# Refresh listings, rebuild the pages (site/ and the netlify/ folder to upload), and open the homepage.
set -e
cd "$(dirname "$0")"
python3 scrape.py
python3 build.py
open site/index.html
