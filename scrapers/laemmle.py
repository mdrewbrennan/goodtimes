"""Laemmle: the Royal (West LA), Monica Film Center, Glendale, NoHo 7, Town Center 5 (Encino) and Newhall.

laemmle.com is a Next.js site (since November 2026; it was Drupal with one page per day before). Each
theater page embeds a "films" list in its page data, with every upcoming showtime: local start time,
ticket link (tickets.laemmle.com), sold-out and Q&A flags, plus the poster and runtime. The page's
"Upcoming Q&As" box names the guests. Each film's own page gives the synopsis, year and director. If
the films list is missing (the layout changed again), the theater fails loudly instead of listing
nothing.

Six houses means a lot of pages from one small site, which starts resetting connections when hit hard.
So every request goes through _get: at most two at a time, spaced out, retried with a backoff. Film
pages are cached across houses (the same films play at several).
"""

import html
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from .common import blurb, clean, fetch, https_url, screening
from .la_offset import la_iso

BASE = "https://www.laemmle.com"
DAYS_AHEAD = 28
WORKERS = 2          # parallel requests to laemmle.com
SPACING = 0.25       # seconds between request starts
RETRIES = (2, 6)     # backoff before the second and third tries

_slots = threading.Semaphore(WORKERS)
_pace = threading.Lock()
_last = [0.0]
_film_cache = {}


def _get(url):
    """fetch(url), politely: limited concurrency, spaced starts, and retries on errors or timeouts."""
    for attempt in range(len(RETRIES) + 1):
        with _slots:
            with _pace:
                wait = _last[0] + SPACING - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                _last[0] = time.monotonic()
            try:
                return fetch(url)
            except Exception:
                if attempt == len(RETRIES):
                    raise
        time.sleep(RETRIES[attempt])

THEATERS = [
    {
        "id": "laemmle-royal",
        "name": "Laemmle Royal",
        "neighborhood": "West LA",
        "address": "11523 Santa Monica Blvd",
        "url": "https://www.laemmle.com/theater/royal",
        "page": "https://www.laemmle.com/theater/royal",
    },
]
# Laemmle's other houses use the same theater pages. Playhouse 7 (Pasadena) and Claremont 5 list no
# showtimes on laemmle.com, so they're left out.
for _slug, _name, _hood, _address in [
    ("monica-film-center", "Laemmle Monica Film Center", "Santa Monica", "1332 2nd St"),
    ("glendale", "Laemmle Glendale", "Glendale", "207 N Maryland Ave"),
    ("noho-7", "Laemmle NoHo 7", "North Hollywood", "5240 Lankershim Blvd"),
    ("town-center-5", "Laemmle Town Center 5", "Encino", "17200 Ventura Blvd"),
    ("newhall", "Laemmle Newhall", "Newhall", "22520 Lyons Ave"),
]:
    THEATERS.append({
        "id": "laemmle-" + _slug.split("-")[0], "name": _name, "neighborhood": _hood, "address": _address,
        "url": f"{BASE}/theater/{_slug}", "page": f"{BASE}/theater/{_slug}",
    })

NEXT_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
FILMS = '"films":['
# The "Upcoming Q&As" box: film link, then the guests.
QA = re.compile(r'"th-qa-film","href":"/films/([^"]+)".*?"th-qa-guest","children":"((?:[^"\\]|\\.)*)"', re.S)
EVENT_TITLE = re.compile(r'(National Theatre Live|Reel Talk|Met Opera|Metropolitan Opera|The Royal Ballet)', re.I)
META_DESC = re.compile(r'<meta name="description" content="([^"]*)"')


def _page_data(page):
    """The Next.js data embedded in a laemmle.com page, as one string."""
    return "".join(json.loads(chunk) for chunk in NEXT_CHUNK.findall(page))


def _films(data):
    """The theater page's films list: [{slug, title, poster, runtime, showtimes: [{startsAt, ticketUrl, ...}]}]."""
    i = data.find(FILMS)
    if i < 0:
        raise RuntimeError("laemmle.com page has no films list (layout changed?)")
    films, _ = json.JSONDecoder().raw_decode(data, i + len(FILMS) - 1)
    return films


def _film_details(slug):
    """Synopsis, year and director from the film's page, cached across houses."""
    if slug in _film_cache:
        return _film_cache[slug]
    try:
        page = _get(f"{BASE}/films/{slug}")
    except Exception:
        return {}  # not cached, so another house can try again
    text = clean(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>", "", page, flags=re.S))))
    text = re.sub(r"(?:\s*\|\s*)+", " | ", text)  # "Year | | 2026" -> "Year | 2026"
    synopsis = META_DESC.search(page)
    year = re.search(r"\bYear\s*\|\s*(\d{4})\b", text)
    director = re.search(r"\bDirectors?\s*\|\s*([^|]{2,120}?)\s*\|", text)
    _film_cache[slug] = {
        "blurb": blurb(html.unescape(synopsis.group(1))) if synopsis else None,
        "year": year.group(1) if year else None,
        "director": director.group(1).strip() if director else None,
    }
    return _film_cache[slug]


def scrape(theater):
    data = _page_data(_get(theater["page"]))  # if this fails after retries, scrape.py logs the theater
    films = _films(data)
    guests = {slug: json.loads(f'"{who}"') for slug, who in QA.findall(data)}
    today = date.today()
    horizon = today + timedelta(days=DAYS_AHEAD)

    upcoming = [f for f in films if any(today.isoformat() <= s.get("date", "") <= horizon.isoformat()
                                        for s in f.get("showtimes") or [])]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        details = dict(zip([f["slug"] for f in upcoming], pool.map(_film_details, [f["slug"] for f in upcoming])))

    out = []
    for f in upcoming:
        det = details.get(f["slug"], {})
        for s in f.get("showtimes") or []:
            if not (today.isoformat() <= s.get("date", "") <= horizon.isoformat()) or not s.get("startsAt"):
                continue
            text = det.get("blurb") or ""
            if s.get("hasQandA"):
                who = guests.get(f["slug"])
                text = (f"Q&A with {who}. " if who else "Followed by a Q&A. ") + text
            out.append(screening(
                theater, f["title"], la_iso(datetime.fromisoformat(s["startsAt"][:19])),
                s.get("ticketUrl") or f"{BASE}/films/{f['slug']}", film_url=f"{BASE}/films/{f['slug']}",
                year=det.get("year"), director=det.get("director"),
                runtime=f["runtime"] if isinstance(f.get("runtime"), int) else None,  # "$undefined" when unknown
                blurb=blurb(text), sold_out=bool(s.get("soldOut")), image=https_url(f.get("poster")),
                special_event=bool(EVENT_TITLE.match(f["title"])),
            ))
    return out
