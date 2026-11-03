"""American Cinematheque: Aero Theatre, Egyptian Theatre and Los Feliz 3.

The Now Showing calendar is a Vue app fed by a public WordPress endpoint that returns the Algolia event
records as JSON (/wp-json/wp/v2/algolia_get_events). Each record is one showing, with event_location
taxonomy ids (54 Aero, 55 Egyptian, 102 Los Feliz 3; other ids are festival pop-up venues, skipped).
The record has no year/director/runtime/blurb or sold-out flag, so we read those from the event page
(the ticket cart itself is JS-only, so the event page is the ticket URL).
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from .common import blurb, clean, fetch, fetch_json, og_image, screening
from .veezi import la_offset

API = "https://www.americancinematheque.com/wp-json/wp/v2/algolia_get_events"
ENV = "production_2026"  # index name the site's own JS uses; read from window.algolia_env on the page
DAYS_AHEAD = 60

THEATERS = [
    {"id": "aero", "name": "Aero Theatre", "operator": "American Cinematheque", "neighborhood": "Santa Monica", "address": "1328 Montana Ave",
     "url": "https://www.americancinematheque.com/about/theatres/aero-theatre/", "location": 54},
    {"id": "egyptian", "name": "Egyptian Theatre", "operator": "American Cinematheque", "neighborhood": "Hollywood", "address": "6712 Hollywood Blvd",
     "url": "https://www.americancinematheque.com/about/theatres/egyptian-theatre", "location": 55},
    {"id": "losfeliz", "name": "Los Feliz 3", "operator": "American Cinematheque", "neighborhood": "Los Feliz", "address": "1822 N Vermont Ave",
     "url": "https://www.americancinematheque.com/about/theatres/los-feliz-theatre/", "location": 102},
]

FILM_TYPES = {60, 72, 77, 78, 99, 118, 120, 133, 191, 314}

_cache = {}  # one API call and one fetch per event page, shared across the three theaters


def _hits():
    if "hits" not in _cache:
        start = datetime.combine(date.today(), datetime.min.time())
        end = start + timedelta(days=DAYS_AHEAD)
        try:
            env = re.search(r'algolia_env = "([^"]+)"', fetch("https://www.americancinematheque.com/now-showing/")).group(1)
        except Exception:
            env = ENV
        # the site sends local-midnight epoch seconds; any consistent window works
        url = f"{API}?environment={env}&startDate={int(time.mktime(start.timetuple()))}&endDate={int(time.mktime(end.timetuple()))}"
        _cache["hits"] = fetch_json(url)["hits"]
    return _cache["hits"]


def _details(url):
    if url in _cache:
        return _cache[url]
    info = {}
    try:
        page = fetch(url)
        info["image"] = og_image(page)  # a landscape hero still; the site has no portrait poster
        bar = re.findall(r'eventDetailBar__item">(.*?)</li>', page, re.S)
        for item in bar:
            item = clean(re.sub(r"<[^>]+>", "", item))
            if m := re.match(r"RELEASED IN:\s*(\d{4})", item):
                info["year"] = m.group(1)
            elif m := re.match(r"(\d+)\s*MINUTES", item):
                info["runtime"] = int(m.group(1))
            elif m := re.match(r"DIRECTED BY:\s*(.+)", item):
                info["director"] = m.group(1)
        body = re.search(r'<div class="eventMain__body">(.*?)</div>\s*</article>', page, re.S)
        if body:
            paras = [p for p in re.findall(r"<p>(.*?)</p>", body.group(1), re.S)
                     if not re.match(r"\s*(FORMAT|DISTRIBUTOR|COUNTRY|PRINT SOURCE)\b", re.sub(r"<[^>]+>", "", p))]
            text = blurb(paras[0]) if paras else None
            if text and len(text) > 500:
                text = text[:497].rsplit(" ", 1)[0] + "..."
            info["blurb"] = text
        hero = re.search(r'class="eventHero__text">(.*?)</article>', page, re.S)
        info["sold_out"] = bool(hero and re.search(r"sold[\s-]*out", hero.group(1), re.I))
    except Exception:
        pass
    _cache[url] = info
    return info


def scrape(theater):
    today = date.today().strftime("%Y%m%d")
    hits = [h for h in _hits() if theater["location"] in h.get("event_location", [])
            and h.get("event_start_date", "") >= today and h.get("event_start_time")]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_details, sorted({h["url"] for h in hits if h["url"] not in _cache})))

    out = []
    for h in hits:
        d = datetime.strptime(h["event_start_date"], "%Y%m%d").date()
        t = datetime.strptime(h["event_start_time"].strip().upper(), "%I:%M %p")
        info = _details(h["url"])
        # event_type taxonomy: 60 Film, 72 Double Feature, 120 Shorts Program; anything else (panels, mixers,
        # book signings, ticket bundles) is a non-film event
        types = set(h.get("event_type") or [])
        film = bool(types & FILM_TYPES) and "bundle" not in h["title"].lower()
        out.append(screening(
            theater, h["title"], f"{d.isoformat()}T{t:%H:%M}:00{la_offset(d, t.hour)}", h["url"],
            film_url=h["url"],
            year=info.get("year"), director=info.get("director"), runtime=info.get("runtime"),
            blurb=info.get("blurb"), sold_out=info.get("sold_out", False), image=info.get("image"),
            special_event=not film,
        ))
    return out
