"""Coaxial Arts (DTLA): a media-arts space; we list its film and video screenings only.

Coaxial sells through Pools (formerly Withfriends). Its Pools page (pools.events/o/coaxial_arts/upcoming/)
is server-rendered: one card per event with the title, event link and a local time like "Fri, Nov 6 at
7pm" (no year). Each event page's description (JSON-LD, else og:description) tells us what it is. Most
nights are noise, music or performance, so we keep an event only when its title or description says
film, screening, cinema, microcinema, 16mm/35mm, video program or moving image, or it's a Shadow Kitchen
night (Coaxial's own screening series).
"""

import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

from . import veezi
from .common import LD_JSON, blurb, clean, fetch, https_url, og_image, screening
from .la_offset import la_iso

BASE = "https://pools.events"
LISTING = BASE + "/o/coaxial_arts/upcoming/"

THEATERS = [
    {
        "id": "coaxial",
        "name": "Coaxial Arts",
        "neighborhood": "Downtown",
        "address": "1815 S Main St",
        "url": "https://coaxialarts.org/",
    },
]

CARD = re.compile(r'<div class="ticketCard[^"]*"(.*?)(?=<div class="ticketCard|\Z)', re.S)
LINK = re.compile(r'href="(/event/[A-Za-z0-9]+/[^"]*)"')
TITLE = re.compile(r'class="eventTitleMobile">([^<]+)<')
WHEN = re.compile(r'imageTextUpperLeft">.*?\w{3},\s+([A-Z][a-z]{2})\w*\s+(\d{1,2})\s+at\s+(\d{1,2}(?::\d{2})?\s*[ap]m)', re.S | re.I)
OG_DESC = re.compile(r'<meta[^>]+og:description"\s+content="([^"]*)"')
FILM = re.compile(r"\bfilms?\b|\bscreenings?\b|\bcinema\b|microcinema|shadow kitchen|\b(?:16|35|8)\s?mm\b|"
                  r"video (?:art )?program|moving[- ]image", re.I)
MONTHS = {name[:3]: number for name, number in veezi.MONTHS.items()}


def _hm(text):
    """'7pm', '7:30 pm', '9PM' -> (hour, minute), else None."""
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\b", text or "", re.I)
    if not m:
        return None
    return int(m.group(1)) % 12 + (12 if m.group(3).lower() == "p" else 0), int(m.group(2) or 0)


def _description(path):
    try:
        page = fetch(BASE + path)
    except Exception:
        return "", None
    text = ""
    for block in LD_JSON.findall(page):
        try:
            node = json.loads(block)
        except ValueError:
            continue
        if isinstance(node, dict) and node.get("@type") == "Event":
            text = node.get("description") or ""
    if not text:
        m = OG_DESC.search(page)
        text = html.unescape(m.group(1)) if m else ""
    # og:description starts with Pools' own "Fri, Nov 6 at 7pm at Coaxial Arts Foundation, Los Angeles, CA."
    text = re.sub(r"^\w{3}, \w{3} \d{1,2} at [^.]*?, CA\.\s*", "", blurb(text) or "")
    return text, og_image(page)


def scrape(theater):
    page = fetch(LISTING)
    today = date.today()
    cards = []
    for card in CARD.findall(page):
        link, title, when = LINK.search(card), TITLE.search(card), WHEN.search(card)
        month = when and MONTHS.get(when.group(1).title())
        hm = when and _hm(when.group(3))
        if not link or not title or not month or not hm:
            continue
        day = veezi.infer_date(month, int(when.group(2)), today)
        cards.append((link.group(1), clean(title.group(1)), datetime(day.year, day.month, day.day, *hm)))

    with ThreadPoolExecutor(max_workers=3) as pool:
        details = list(pool.map(_description, [c[0] for c in cards]))

    out = []
    for (path, title, start), (text, image) in zip(cards, details):
        if start.date() < today or not FILM.search(f"{title} {text}"):
            continue
        out.append(screening(
            theater, title, la_iso(start), BASE + path, film_url=BASE + path,
            blurb=text or None, image=https_url(image),
        ))
    return out
