"""The Eastwood Performing Arts Center (East Hollywood): its Cinema programs only, not its theatre.

The Eastwood sells through Stagey (eastwoodpac.stagey.net). The "Now Playing" page loads its show cards
from a form POST to /dashboard/search_projects, which answers with a jQuery snippet holding the cards'
HTML: one card per project with its title, a category ("Cinema", "Theatre", ...) and a one-line
description. We keep the Cinema cards; each project's tickets tab lists every showing with a full date
and time ("Saturday November 21 2026, 4:00 PM") and its own Buy Tickets link. Film titles come as
"Rear Window (Alfred Hitchcock, 1954) Presented by See It On 16mm"; we split out the title, director
and year and move the "Presented by" part into the blurb, where the site picks up 16mm and the like.
"""

import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlencode
import urllib.request

from .common import USER_AGENT, blurb, clean, fetch, https_url, screening
from .la_offset import la_iso

BASE = "https://eastwoodpac.stagey.net"
SEARCH = BASE + "/dashboard/search_projects"
FORM = {"utf8": "✓", "event_id": "198", "sort_order": "OPENING", "project_format": "Vertical",
        "shows_per_page": "60", "now_playing_only": "true"}

THEATERS = [
    {
        "id": "eastwood",
        "name": "The Eastwood",
        "neighborhood": "East Hollywood",
        "address": "1089 N Oxford Ave",
        "url": BASE + "/shows",
    },
]

CARD = re.compile(r'class="card px-0(.*?)(?=class="card px-0|\Z)', re.S)
PROJECT = re.compile(r'href="(https://[^"]+/projects/(\d+))"')
CARD_TITLE = re.compile(r'card-title[^>]*>(.*?)</', re.S)
SHOWING = re.compile(r'<h4 class="my-0">\s*\w+day\s+([A-Z][a-z]+)\s+(\d{1,2})\s+(\d{4}),\s*(\d{1,2}:\d{2}\s*[AP]M)'
                     r'(?:\s*\|\s*(\d+)\s*mins?)?\s*</h4>(.*?)(?=<h4 class="my-0">|id="perf_paginator"|\Z)', re.S)
BUY = re.compile(r'href="([^"]*performance_id=\d+[^"]*)"[^>]*>\s*Buy Tickets', re.S)
OG = re.compile(r'<meta[^>]+property="og:(description|image)"[^>]+content="([^"]*)"')
FILM_TITLE = re.compile(r"^(.*?)\s*\(([^()]*?),\s*(\d{4})\)\s*(.*)$")


def _text(fragment):
    return clean(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment or "")))


def _cards():
    """The Now Playing cards' HTML, out of Stagey's jQuery response."""
    req = urllib.request.Request(SEARCH, data=urlencode(FORM).encode(), headers={
        "User-Agent": USER_AGENT, "X-Requested-With": "XMLHttpRequest",
        "Accept": "text/javascript, application/javascript, */*"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        js = resp.read().decode("utf-8", errors="replace")
    # undo the JavaScript string escaping: \" \' \/ \n
    return re.sub(r"\\(.)", lambda m: "\n" if m.group(1) == "n" else m.group(1), js)


def _project(url):
    page = fetch(url + "?tab=tickets")
    og = dict(OG.findall(page))
    rows = []
    for month, day, year, time, mins, rest in SHOWING.findall(page):  # days are space-padded: "November  7"
        buy = BUY.search(rest)
        rows.append((datetime.strptime(f"{month} {day} {year} {time.replace(' ', '')}", "%B %d %Y %I:%M%p"),
                     int(mins) if mins else None, html.unescape(buy.group(1)) if buy else url + "?tab=tickets"))
    return rows, html.unescape(og.get("description", "")).strip(), og.get("image")


def scrape(theater):
    films = []
    for card in CARD.findall(_cards()):
        project, title = PROJECT.search(card), CARD_TITLE.search(card)
        if project and title and re.search(r">\s*Cinema\s*<|\bCinema\s*·", card):
            films.append((project.group(1), _text(title.group(1))))
    if not films and "projects/" not in _cards():
        raise RuntimeError("Stagey returned no show cards")

    with ThreadPoolExecutor(max_workers=3) as pool:
        details = list(pool.map(lambda f: _project(f[0]), films))

    now = datetime.now()
    out = []
    for (url, raw_title), (rows, tagline, image) in zip(films, details):
        m = FILM_TITLE.match(raw_title)
        title, director, year, extra = (m.groups() if m else (raw_title, None, None, ""))
        text = " ".join(x if x.endswith((".", "!", "?")) else x + "." for x in (extra.strip(), tagline) if x)
        for start, mins, buy in rows:
            if start < now.replace(hour=0, minute=0):
                continue
            out.append(screening(
                theater, title, la_iso(start), buy, film_url=url, year=year, director=director,
                runtime=mins, blurb=blurb(text), image=https_url(image),
            ))
    return out
