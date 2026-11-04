"""Human Resources (Chinatown): an artist-run space; we list its film screenings only.

h-r.la is WordPress with The Events Calendar, whose REST API (/wp-json/tribe/events/v1/events) returns
upcoming events as JSON with local start times, categories, description and image. Most events are
music, performance, talks or exhibitions, so we keep only films:
  - events in the "screening" category, or
  - events with no category at all whose title or description says film, screening, cinema, 16mm or 35mm
    ("Film and performance by ..." counts).
An event filed only under other categories (music/sound, performance, reading, ...) is dropped, and so
are all-day events, which are exhibition runs rather than showtimes.
"""

import re
from datetime import date, datetime

from .common import blurb, clean, fetch_json, https_url, screening
from .la_offset import la_iso

API = "https://www.h-r.la/wp-json/tribe/events/v1/events"
MAX_PAGES = 5

THEATERS = [
    {
        "id": "humanresources",
        "name": "Human Resources",
        "neighborhood": "Chinatown",
        "address": "410 Cottage Home St",
        "url": "https://www.h-r.la/",
    },
]

FILM_TEXT = re.compile(r"\bfilms?\b|\bscreenings?\b|\bcinema\b|\bmicrocinema\b|\b(?:16|35|8)\s?mm\b", re.I)


def _is_film(event):
    categories = {c.get("slug") or c.get("name", "").lower() for c in event.get("categories") or []}
    if "screening" in categories:
        return True
    if categories:
        return False
    return bool(FILM_TEXT.search(f'{event.get("title", "")} {blurb(event.get("description")) or ""}'))


def scrape(theater):
    url = f"{API}?per_page=50&start_date={date.today().isoformat()}"
    out = []
    for _ in range(MAX_PAGES):
        data = fetch_json(url)
        for e in data.get("events") or []:
            if e.get("all_day") or e.get("status") not in (None, "publish") or not _is_film(e):
                continue
            start = datetime.strptime(e["start_date"], "%Y-%m-%d %H:%M:%S")  # the site's own (LA) time
            image = e.get("image") or {}
            out.append(screening(
                theater, clean(e["title"]), la_iso(start), e.get("website") or e["url"], film_url=e["url"],
                blurb=blurb(e.get("description")),
                image=https_url(image.get("url")) if isinstance(image, dict) else None,
            ))
        url = data.get("next_rest_url")
        if not url:
            break
    return out
