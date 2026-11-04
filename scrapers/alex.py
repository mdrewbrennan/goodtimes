"""Alex Theatre (Glendale): Alex Film Society shows, 35mm/70mm runs and film events among its live shows.

thealex.com is a Squarespace site whose Shows page is an Elfsight event-calendar widget; the widget's
settings (every event, with date, time, description, tags, cover image and ticket link) come from
Elfsight's public boot endpoint as JSON. The venue is mostly concerts and dance, so we keep events that
link to the Alex's own cinema ticketing (cinema.thealex.com) or whose text says it's a screening or film.
Each event has one start time, so a multi-showtime run (a 70mm release) appears once. All-day entries
and pre-10am times are placeholders and are skipped. Times are Los Angeles local.
"""

import re
from datetime import date, datetime
from urllib.parse import quote

from .common import blurb, clean, fetch_json, https_url, screening
from .la_offset import la_iso
from .titlecase import smart_case

WIDGET = "b8b78dc4-f44a-4633-ab5e-9d1eade33f37"
PAGE = "https://www.thealex.com/shows"
BOOT = f"https://core.service.elfsight.com/p/boot/?page={quote(PAGE, safe='')}&w={WIDGET}"

THEATERS = [
    {
        "id": "alex",
        "name": "Alex Theatre",
        "neighborhood": "Glendale",
        "address": "216 N Brand Blvd",
        "url": PAGE,
    },
]

FILM = re.compile(r"\bscreenings?\b|\bfilms?\b|\b(16|35|70)\s?mm\b|\bin 4K\b|\bdocumentary\b|film society|premiere of", re.I)


def _link(event):
    for action in event.get("actions") or []:
        url = ((action.get("link") or {}).get("value") or "").strip()
        if url.startswith("http"):
            return url
    return None


def scrape(theater):
    data = fetch_json(BOOT)
    settings = data["data"]["widgets"][WIDGET]["data"]["settings"]
    today = date.today().isoformat()
    out = []
    for e in settings["events"]:
        start = e.get("start") or {}
        if e.get("isAllDay") or start.get("type") != "datetime" or start.get("date", "") < today:
            continue
        when = datetime.strptime(f"{start['date']} {start.get('time') or '00:00'}", "%Y-%m-%d %H:%M")
        if when.hour < 10:
            continue
        tags = [clean(t.get("tagName")) for t in e.get("tags") or [] if clean(t.get("tagName"))]
        description = blurb(e.get("description")) or ""
        link = _link(e)
        if not ("cinema.thealex.com" in (link or "") or FILM.search(" ".join([e.get("name", ""), *tags, description]))):
            continue
        text = " ".join(t if t.endswith((".", "!", "?")) else t + "." for t in tags) + " " + description
        out.append(screening(
            theater, smart_case(re.sub(r"\s+", " ", e["name"]).strip()), la_iso(when), link or PAGE,
            blurb=blurb(text), image=https_url((e.get("coverImage") or {}).get("url")),
        ))
    return out
