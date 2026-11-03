"""Muscle Distribution (Los Angeles screenings only).

Muscle books films at various venues, so it is modelled as one "theater"; the actual venue goes in the blurb.
The site (Next.js) publishes its schedule as an iCalendar feed (/screenings.ics), which carries date, venue,
city, ticket URL and film-page URL. The ICS has dates only (all-day events, no showtimes), so every
screening is given a 19:30 local start. Year/director/runtime/description come from each film page's
schema.org Movie JSON-LD.
"""

import re
from datetime import date

from .common import blurb, fetch, json_ld_nodes, runtime_minutes, screening

THEATERS = [
    {
        "id": "muscle",
        "name": "Muscle Distribution",
        "neighborhood": "Various",
        "address": "Various Los Angeles venues",
        "url": "https://www.muscle-distribution.com/screenings",
        "ics": "https://www.muscle-distribution.com/screenings.ics",
    },
]

DEFAULT_TIME = "19:30:00"  # the feed has no showtimes


def _unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text)


def _unescape(v):
    return v.replace("\\n", "\n").replace("\\,", ",").replace("\;", ";").replace("\\\\", "\\")


def _events(ics):
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", _unfold(ics), re.S):
        props = {}
        for line in block.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                props[k.split(";")[0]] = _unescape(v)
        yield props


def _offset(d):
    """US Pacific offset for a date (DST: second Sunday of March to first Sunday of November)."""
    def nth_sunday(year, month, n):
        first = date(year, month, 1)
        return date(year, month, 1 + (6 - first.weekday()) % 7 + 7 * (n - 1))
    return "-07:00" if nth_sunday(d.year, 3, 2) <= d < nth_sunday(d.year, 11, 1) else "-08:00"


def _film(url, cache):
    if url not in cache:
        try:
            cache[url] = next((n for n in json_ld_nodes(fetch(url)) if n.get("@type") == "Movie"), {})
        except Exception:
            cache[url] = {}
    return cache[url]


def scrape(theater):
    today = date.today()
    films, seen, out = {}, set(), []
    for ev in _events(fetch(theater["ics"])):
        loc = ev.get("LOCATION", "")
        if not loc.endswith(", Los Angeles, CA"):
            continue
        m = re.match(r"(\d{4})(\d{2})(\d{2})", ev.get("DTSTART", ""))
        if not m:
            continue
        d = date(*map(int, m.groups()))
        if d < today:
            continue
        desc = ev.get("DESCRIPTION", "")
        info = re.search(r"More info: (\S+)", desc)
        film_url = info.group(1) if info else None
        ticket_url = ev.get("URL") or theater["url"]
        key = (ev.get("SUMMARY"), d, loc)
        if key in seen:
            continue
        seen.add(key)

        movie = _film(film_url, films) if film_url else {}
        director = movie.get("director") or []
        if isinstance(director, dict):
            director = [director]
        venue = loc[: -len(", Los Angeles, CA")]
        text = blurb(movie.get("description"))
        out.append(screening(
            theater,
            ev["SUMMARY"],
            "%sT%s%s" % (d.isoformat(), DEFAULT_TIME, _offset(d)),
            ticket_url,
            film_url=film_url,
            year=movie.get("dateCreated"),
            director=", ".join(p["name"] for p in director if p.get("name")),
            runtime=runtime_minutes(movie.get("duration")),
            genres=[g for g in movie.get("genre", []) if g != "New Release"],
            blurb=("At %s. Showtime not listed by Muscle (check tickets link). %s" % (venue, text or "")).strip(),
        ))
    return out
