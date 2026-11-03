"""2220 Arts + Archives (Historic Filipinotown, 2220 Beverly Blvd).

2220arts.org is a Google Sites page whose event list is a DICE widget (it needs a partner API key that
sits in the page JS, which we don't use). Instead we read the public DICE venue page, which lists every
upcoming event as schema.org JSON-LD (name, startDate with offset, ticket/event URL). Event pages add a
description in their own JSON-LD, when the venue wrote one.

The venue is mostly a music space, so we keep only events that are film programs: titles naming a film
series/presenter (Lightstruck, LA Filmforum, Acropolis Cinema), "presents:" film nights, "Live Score"
films, or a possessive filmmaker + CAPS film title ("Fleischer's THE NARROW MARGIN"). Concerts, poetry
readings, performance lectures, fairs and benefits are dropped. Live-score shows are special_event.
"""

import json
import re
import urllib.error
import urllib.request
from datetime import datetime

from .common import LD_JSON, USER_AGENT, blurb, clean, screening

VENUE_URL = "https://dice.fm/venue/2220-arts--archives-bdyv"

THEATERS = [
    {
        "id": "arts2220",
        "name": "2220 Arts + Archives",
        "neighborhood": "Historic Filipinotown",
        "address": "2220 Beverly Blvd",
        "url": "https://www.2220arts.org/events",
    },
]

FILM_CASE = re.compile(r"lightstruck|filmforum|acropolis cinema|cinema:|\bfilms?\b|screening|live score|\bpresents:", re.I)
CAPS_TITLE = re.compile(r"[’']s [A-Z][A-Z ]{3,}")
LIVE_SCORE = re.compile(r"live score", re.I)


class _Redirect(urllib.request.HTTPRedirectHandler):
    http_error_308 = urllib.request.HTTPRedirectHandler.http_error_302  # DICE short links use 308


_opener = urllib.request.build_opener(_Redirect)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with _opener.open(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def ld_event(page):
    for block in LD_JSON.findall(page):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Event":
            return data
    return {}


def is_film(title):
    return bool(FILM_CASE.search(title) or CAPS_TITLE.search(title))


def scrape(theater):
    page = fetch(VENUE_URL)
    place = next((n for n in (json.loads(b) for b in LD_JSON.findall(page)) if n.get("@type") == "Place"), {})
    now = datetime.now()
    out = []
    for ev in place.get("event", []):
        title = clean(ev["name"])
        start = ev["startDate"]
        if not is_film(title) or datetime.strptime(start[:19], "%Y-%m-%dT%H:%M:%S") < now:
            continue
        if "Cancelled" in ev.get("eventStatus", ""):
            continue
        director = None
        m = re.match(r"(?:Acropolis Cinema):\s*(.+?)[’']s (.+)$", title)
        if m:
            director, title = m.group(1), m.group(2)
        try:
            detail = ld_event(fetch(ev["url"]))
        except urllib.error.URLError:
            detail = {}
        out.append(screening(
            theater, title, start, ev["url"],
            director=director, blurb=blurb(detail.get("description")),
            special_event=bool(LIVE_SCORE.search(title))))
    return out
