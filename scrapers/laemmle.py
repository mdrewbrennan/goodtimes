"""Laemmle Royal (West LA).

laemmle.com is a server-rendered Drupal site with no JSON/JSON-LD for showtimes. The theater page
lists one day at a time (?date=YYYY-MM-DD, with the available dates in a <select>), so we read the
next few weeks of those day pages, then each film's page once for director / synopsis.
Ticketing is tickets.laemmle.com (linked directly from each showtime).
"""

import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from .common import blurb, clean, fetch, https_url, screening
from .la_offset import la_iso

BASE = "https://www.laemmle.com"
DAYS_AHEAD = 28

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
    try:
        page = fetch(BASE + path)
    except Exception:
        return {}
    director = re.search(r'field--name-field-director.*?<div class="field__items">(.*?)</div>\s*</div>', page, re.S)
    synopsis = re.search(r'field--name-field-synopsis[^>]*>(.*?)</div>', page, re.S)
    dur = re.search(r'field--name-field-duration.*?field--item">\s*(\d+)\s*<', page, re.S)
    names = re.findall(r'<span class="field--item">([^<]+)</span>', director.group(1)) if director else []
    # the full-size poster upload; the only styled rendition on the page is a 150px thumbnail
    poster = re.search(r'field--name-field-poster\b.*?<img[^>]*?\ssrc="([^"]+)"', page, re.S)
    image = https_url(html.unescape(poster.group(1)), BASE) if poster else None
    return {
        "image": image,
        "director": ", ".join(clean(n).rstrip(",") for n in names) or None,
        "blurb": blurb(synopsis.group(1)) if synopsis else None,
        "runtime": int(dur.group(1)) if dur else None,
    }


def scrape(theater):
    first = fetch(theater["page"])
    days = _dates(first)

    def day_page(d):
        return d, (first if d == date.today().isoformat() else fetch(f"{theater['page']}?date={d}"))

    with ThreadPoolExecutor(max_workers=4) as pool:
        pages = list(pool.map(day_page, days))

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

    with ThreadPoolExecutor(max_workers=4) as pool:
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
