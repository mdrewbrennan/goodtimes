"""USC School of Cinematic Arts (University Park): free public screenings in the Norris, Ray Stark and IMAX theaters.

cinema.usc.edu is a ColdFusion site with no JSON or JSON-LD. Its events page lists every upcoming event
(title, date and time, location, short description, image); each event page adds the RSVP link and
the full write-up, where the director, runtime and "Q&A with ..." lines are. Only events with a single
date and time in one of the school's theaters are kept, so classes, meetings and multi-day workshops
drop out.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from .common import blurb, clean, fetch, https_url, screening
from .la_offset import la_iso
from .titlecase import smart_case

BASE = "https://cinema.usc.edu"

THEATERS = [
    {
        "id": "usc",
        "name": "USC Cinematic Arts",
        "neighborhood": "University Park",
        "address": "900 W 34th St",
        "url": BASE + "/events/index.cfm",
    },
]

ARTICLE = re.compile(r'<article class="event-list__item">(.*?)</article>', re.S)
TITLE = re.compile(r'event-list__title">\s*<a href="(/events/event\.cfm\?id=(\d+))"[^>]*>(.*?)</a>', re.S)
META = re.compile(r'<p[^>]*class="event-list__meta">.*?<span>(.*?)</span>', re.S)
DESC = re.compile(r'event-list__description">(.*?)</p>', re.S)
IMAGE = re.compile(r'class="event-list__image"[^>]*?\ssrc="([^"]+)"', re.S)
# "November 3, 2026, 7:00 P.M." (a range like "3:00-4:00 PM" or "6-10 PM" isn't a screening)
WHEN = re.compile(r"(\w+ \d{1,2}, \d{4}),\s*(\d{1,2})(?::(\d{2}))?\s*([AP])\.?M\.?", re.I)
SERIES = re.compile(r"^(.*\bScreening):\s*(.+)$", re.I)  # "AGFA Movie Hooky Club IMAX Matinee Screening: X"
YEAR = re.compile(r"\s*\((\d{4})\)\s*$")
CUES = re.compile(r"q&a|in person|conversation|discussion|introduc|moderated|\b(16|35|70)mm\b", re.I)


def _text(fragment):
    return clean(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment or "")))


def _event_page(path):
    """Director, runtime, RSVP link and guest/format lines from an event's own page."""
    try:
        page = fetch(BASE + path)
    except Exception:
        return {}
    body = page.split('class="event-detail__body"', 1)[-1].split("</article>", 1)[0]
    lines = [_text(x) for x in re.split(r"<br\s*/?>|</p>|</h\d>|</li>", body)]
    director = re.search(r"Directed by\s*(?:&nbsp;)?\s*([^<\n]+)", body)
    if director:  # "Directed by the mighty Penelope Spheeris (WAYNE'S WORLD) and written by ..."
        director = re.split(r"\.\s|\.$|\s\(|,? and written|,? written by|\s+Running time", _text(director.group(1)))[0]
        director = re.sub(r"^(?:[a-z]+\s+)+", "", director).strip(" ,")
    runtime = re.search(r"Running time:\s*(\d+)", body, re.I)
    rsvp = re.search(r'href="([^"]*reservation\.cfm\?id=\d+)"', page)
    return {
        "director": director if director and len(director) < 80 else None,
        "runtime": int(runtime.group(1)) if runtime else None,
        "rsvp": https_url(rsvp.group(1), BASE) if rsvp else None,
        "cues": [line for line in lines if line and len(line) < 300 and CUES.search(line)],
    }


def scrape(theater):
    page = fetch(theater["url"])
    events = []
    for article in ARTICLE.findall(page):
        title = TITLE.search(article)
        metas = [_text(m) for m in META.findall(article)]
        if not title or len(metas) < 2:
            continue
        when = WHEN.fullmatch(metas[0].strip())
        if not when or "theat" not in metas[1].lower():
            continue
        day, hour, minute, ampm = when.groups()
        start = datetime.strptime(f"{day} {hour}:{minute or '00'} {ampm.upper()}M", "%B %d, %Y %I:%M %p")
        name, series = _text(title.group(3)), None
        m = SERIES.match(name)
        if m:
            series, name = m.group(1), m.group(2)
        year = YEAR.search(name)
        name = YEAR.sub("", name)
        desc = DESC.search(article)
        image = IMAGE.search(article)
        events.append({
            "path": title.group(1), "title": smart_case(name), "start": start, "series": series,
            "year": year.group(1) if year else None, "desc": _text(desc.group(1)) if desc else "",
            "image": https_url(clean(image.group(1)), BASE) if image else None,
        })

    with ThreadPoolExecutor(max_workers=4) as pool:
        details = list(pool.map(_event_page, [e["path"] for e in events]))

    out = []
    for e, det in zip(events, details):
        parts = [e["series"], *det.get("cues", []), e["desc"]]
        text = " ".join(x if x.endswith((".", "!", "?", ",")) else x + "." for x in parts if x)
        out.append(screening(
            theater, e["title"], la_iso(e["start"]), det.get("rsvp") or BASE + e["path"],
            film_url=BASE + e["path"], year=e["year"], director=det.get("director"),
            runtime=det.get("runtime"), blurb=blurb(text), image=e["image"],
        ))
    return out
