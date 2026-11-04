"""REDCAT (Downtown, Disney Concert Hall complex): CalArts' arts center; we list its film programs only.

redcat.org is Drupal with no JSON-LD. Its calendar can be filtered by "metier" (?type=4 is Film), but
that filter also returns mixed festival programs whose genres merely include film (NOW: "Theater,
Film, Dance, Music"), so we keep an event only when the calendar card's own metier label is "Film".
Each event page has a details list with DATE ("JUL 16", "NOV 19-21", "DEC 30 - JAN 2") and TIME
("7 PM", "WED, 8 PM"). When TIME names a single time it applies to every date in the range; an event
that lists several different times is skipped rather than guessed.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from . import veezi
from .common import blurb, clean, fetch, https_url, og_image, screening
from .la_offset import la_iso

BASE = "https://www.redcat.org"
LISTING = BASE + "/events?type=4"

THEATERS = [
    {
        "id": "redcat",
        "name": "REDCAT",
        "neighborhood": "Downtown",
        "address": "631 W 2nd St",
        "url": LISTING,
    },
]

CARD = re.compile(r'<a href="?(/events/[a-z0-9-]+)"?\s+class="event-card[^>]*>(.*?)</a>', re.S)
METIER = re.compile(r'<div class="metier">\s*([^<]+?)\s*</div>')
TITLE = re.compile(r'<div class="pl-6">\s*(.*?)\s*</div>', re.S)
FIELD = re.compile(r'<dt class="uppercase">([^<]+)</dt>\s*<dd>(.*?)</dd>', re.S)
DESCRIPTION = re.compile(r'<meta name="description" content="([^"]*)"')
MONTHS = {name[:3].upper(): number for name, number in veezi.MONTHS.items()}
TIMES = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([AP])\.?M\b", re.I)


def _text(fragment):
    return clean(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment or "")))


def _dates(text, today):
    """'JUL 16' / 'NOV 19-21' / 'DEC 30 - JAN 2' -> list of dates, else []."""
    m = re.fullmatch(r"([A-Z]{3})\s+(\d{1,2})(?:\s*[-–]\s*(?:([A-Z]{3})\s+)?(\d{1,2}))?", text.upper().strip())
    if not m or m.group(1) not in MONTHS:
        return []
    first = veezi.infer_date(MONTHS[m.group(1)], int(m.group(2)), today)
    if not m.group(4):
        return [first]
    end_month = MONTHS.get(m.group(3) or m.group(1))
    if not end_month:
        return []
    last = date(first.year + (end_month < first.month), end_month, int(m.group(4)))
    if not first <= last <= first + timedelta(days=31):
        return []
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def _event(path):
    page = fetch(BASE + path)
    fields = {k.strip().upper(): _text(v) for k, v in FIELD.findall(page)}
    about = DESCRIPTION.search(page)
    return fields, (blurb(about.group(1)) if about else None), og_image(page, BASE)


def scrape(theater):
    today = date.today()
    cards = []
    for path, body in CARD.findall(fetch(LISTING)):
        metier, title = METIER.search(body), TITLE.search(body)
        if metier and title and metier.group(1).strip().lower() == "film":
            cards.append((path, _text(title.group(1))))

    with ThreadPoolExecutor(max_workers=3) as pool:
        events = list(pool.map(lambda c: _event(c[0]), cards))

    out = []
    for (path, title), (fields, about, image) in zip(cards, events):
        times = {(int(h) % 12 + (12 if ap.upper() == "P" else 0), int(mi or 0))
                 for h, mi, ap in TIMES.findall(fields.get("TIME", ""))}
        if len(times) != 1:
            continue
        hm = times.pop()
        for day in _dates(fields.get("DATE", ""), today):
            if day < today:
                continue
            out.append(screening(
                theater, title, la_iso(datetime(day.year, day.month, day.day, *hm)), BASE + path,
                film_url=BASE + path, blurb=about, image=https_url(image),
            ))
    return out
