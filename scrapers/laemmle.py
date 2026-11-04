"""Laemmle: the Royal (West LA), Monica Film Center, Glendale, NoHo 7, Town Center 5 (Encino) and Newhall.

laemmle.com is a server-rendered Drupal site with no JSON/JSON-LD for showtimes. The theater page
lists one day at a time (?date=YYYY-MM-DD, with the available dates in a <select>), so we read the
next few weeks of those day pages, then each film's page once for director / synopsis.
Ticketing is tickets.laemmle.com (linked directly from each showtime).

Six houses means a lot of pages from one small site, which starts resetting connections when hit hard.
So every request goes through _get: at most two at a time, spaced out, retried with a backoff. Film
pages are cached across houses (the same films play at several), and a day page that still fails is
skipped rather than failing the whole theater.
"""

import html
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

OPTION = re.compile(r'<option value="(\d{4}-\d{2}-\d{2})"')
MOVIE = re.compile(r'<div class="movie">(.*?)(?=<div class="movie">|<div class="theater-get-tickets-footer|\Z)', re.S)
TITLE = re.compile(r'<div class="title">\s*<a href="([^"]+)">\s*(.*?)\s*</a>', re.S)
TIME_LINK = re.compile(r'<div class="showtime([^"]*)">\s*<a href="([^"]+)">\s*(\d{1,2}:\d\d\s*[ap]m)\s*</a>', re.S | re.I)
EVENT_TITLE = re.compile(r'(National Theatre Live|Reel Talk|Met Opera|Metropolitan Opera)', re.I)
DETAIL_RUNTIME = re.compile(r'(\d+)\s*min', re.I)


def _dates(page):
    today = date.today()
    out = []
    for d in OPTION.findall(page):
        day = date.fromisoformat(d)
        if today <= day <= today + timedelta(days=DAYS_AHEAD):
            out.append(d)
    return out


def _film_details(path):
    if path in _film_cache:
        return _film_cache[path]
    try:
        page = _get(BASE + path)
    except Exception:
        return {}  # not cached, so another house can try again
    director = re.search(r'field--name-field-director.*?<div class="field__items">(.*?)</div>\s*</div>', page, re.S)
    synopsis = re.search(r'field--name-field-synopsis[^>]*>(.*?)</div>', page, re.S)
    dur = re.search(r'field--name-field-duration.*?field--item">\s*(\d+)\s*<', page, re.S)
    names = re.findall(r'<span class="field--item">([^<]+)</span>', director.group(1)) if director else []
    # the full-size poster upload; the only styled rendition on the page is a 150px thumbnail
    poster = re.search(r'field--name-field-poster\b.*?<img[^>]*?\ssrc="([^"]+)"', page, re.S)
    image = https_url(html.unescape(poster.group(1)), BASE) if poster else None
    _film_cache[path] = {
        "image": image,
        "director": ", ".join(clean(n).rstrip(",") for n in names) or None,
        "blurb": blurb(synopsis.group(1)) if synopsis else None,
        "runtime": int(dur.group(1)) if dur else None,
    }
    return _film_cache[path]


def scrape(theater):
    first = _get(theater["page"])  # if even this fails after retries, the theater fails (scrape.py logs it)
    days = _dates(first)

    def day_page(d):
        if d == date.today().isoformat():
            return d, first
        try:
            return d, _get(f"{theater['page']}?date={d}")
        except Exception:
            return d, ""  # one missing day shouldn't drop the other four weeks

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        pages = list(pool.map(day_page, days))
    if days and not any(page for _, page in pages):
        raise RuntimeError("laemmle.com returned no day pages")

    shows, films = [], {}
    for d, page in pages:
        for block in MOVIE.findall(page):
            t = TITLE.search(block)
            if not t:
                continue
            path, title = t.group(1), clean(re.sub(r"<[^>]+>", "", t.group(2)))
            rt = DETAIL_RUNTIME.search(block.split('class="showtimes')[0])
            films[path] = {"title": title, "runtime": int(rt.group(1)) if rt else None}
            for cls, url, tm in TIME_LINK.findall(block):  # past showtimes have no link, so are skipped
                when = datetime.strptime(f"{d} {tm.replace(' ', '').upper()}", "%Y-%m-%d %I:%M%p")
                shows.append((path, when, html.unescape(url), "sold" in cls.lower()))

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        details = dict(zip(films, pool.map(_film_details, films)))

    out = []
    for path, when, url, sold in shows:
        f, det = films[path], details.get(path, {})
        out.append(screening(
            theater, f["title"], la_iso(when), url,
            film_url=BASE + path, runtime=f["runtime"] or det.get("runtime"),
            director=det.get("director"), blurb=det.get("blurb"), sold_out=sold, image=det.get("image"),
            special_event=bool(EVENT_TITLE.match(f["title"])),
        ))
    return out
