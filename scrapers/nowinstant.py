"""Now Instant Image Hall (Chinatown).

The site is server-rendered HTML (Kirby CMS). The homepage lists upcoming events with a date and
time; each event page carries the ticket link (tickets.now-instant.la), runtime and description.
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .common import blurb, clean, fetch, screening

THEATERS = [
    {
        "id": "now-instant",
        "name": "Now Instant Image Hall",
        "neighborhood": "Chinatown",
        "address": "939 Chung King Rd",
        "url": "https://now-instant.la/",
    },
]

LA = ZoneInfo("America/Los_Angeles")
CARD = re.compile(r'<a href="(https://now-instant\.la/events/[^"]+)".*?event-lockup--subtitle"><span>(.*?)</span>.*?'
                  r'event-lockup--title[^>]*><span[^>]*>(.*?)</span>.*?event-lockup--meta"><span>\s*(.*?)\s*</span>', re.S)
WHEN = re.compile(r"([A-Z][a-z]+ \d{1,2}, \d{4})\.?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.I)
RUNTIME = re.compile(r"\d{1,2}(?::\d{2})?\s*(?:am|pm),\s*(\d+)m", re.I)
TICKETS = re.compile(r'href="(https://tickets\.now-instant\.la/[^"]+)"')
FIRST_P = re.compile(r'block-type-text[^>]*>\s*<p>(.*?)</p>', re.S)


def _start(date_text, hour, minute, ampm):
    d = datetime.strptime(date_text, "%B %d, %Y")
    h = int(hour) % 12 + (12 if ampm.lower() == "pm" else 0)
    return d.replace(hour=h, minute=int(minute or 0), tzinfo=LA).isoformat()


def scrape(theater):
    home = fetch(theater["url"])
    out, seen = [], set()
    for url, people, title, meta in CARD.findall(home):
        when = WHEN.search(clean(meta).replace("\xa0", " "))
        if not when or url in seen:
            continue  # archive entries only show a short date, no time
        seen.add(url)
        page = fetch(url)
        tickets = TICKETS.search(page)
        runtime = RUNTIME.search(page)
        para = FIRST_P.search(page)
        out.append(screening_row(theater, url, people, title, when, tickets, runtime, para))
    out.sort(key=lambda r: r["start"])
    return out


def screening_row(theater, url, people, title, when, tickets, runtime, para):
    return screening(
        theater,
        re.sub(r"<[^>]+>", "", title).replace("\xa0", " "),
        _start(*when.groups()),
        tickets.group(1) if tickets else url,
        film_url=url,
        director=clean(people).replace("\xa0", " ") or None,
        runtime=int(runtime.group(1)) if runtime else None,
        blurb=blurb(para.group(1)) if para else None,
    )
