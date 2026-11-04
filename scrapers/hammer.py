"""Hammer Museum (Westwood): its own screenings and the UCLA Film & TV Archive's, in the Billy Wilder Theater.

hammer.ucla.edu is a Drupal site with no JSON or JSON-LD. Its programs page takes a start date and a
category filter, so we ask for "Screenings" (which includes the Archive's shows) from today and follow
the pager. Each listing row has the title, a short excerpt, a thumbnail and one date and time
("Thu Nov 5", "7:30 PM", no year). Screenings are free; the program page has the RSVP details.
"""

import re
from datetime import date, datetime

from . import veezi
from .common import blurb, clean, fetch, https_url, screening
from .la_offset import la_iso

BASE = "https://hammer.ucla.edu"
SCREENINGS = 5316  # the "Screenings" category id in the programs filter
MAX_PAGES = 8

THEATERS = [
    {
        "id": "hammer",
        "name": "Hammer Museum",
        "neighborhood": "Westwood",
        "address": "10899 Wilshire Blvd",
        "url": f"{BASE}/programs-events?category%5B{SCREENINGS}%5D={SCREENINGS}",
    },
]

ITEM = re.compile(r'<a class="result-item result-item--program" href="([^"]+)">(.*?)</a>', re.S)
TITLE = re.compile(r'<h3 class="result-item__title">(.*?)</h3>', re.S)
EXCERPT = re.compile(r'result-item__excerpt">(.*?)</div>', re.S)
IMAGE = re.compile(r'<img[^>]*?\ssrc="([^"]+)"')
WHEN = re.compile(r'result-item__occurrence">\s*\w+\s+(\w+)\s+(\d{1,2})\s*<span class="occurrence__time">\s*([^<]+?)\s*</span>', re.S)
MONTH_ABBR = {name[:3]: number for name, number in veezi.MONTHS.items()}


def _text(fragment):
    return clean(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment or "")))


def scrape(theater):
    today = date.today()
    out, seen = [], set()
    for page_no in range(MAX_PAGES):
        page = fetch(f"{theater['url']}&start_date={today:%m/%d/%Y}&page={page_no}")
        items = ITEM.findall(page)
        if not items:
            break
        for path, body in items:
            title, when = TITLE.search(body), WHEN.search(body)
            month = when and MONTH_ABBR.get(when.group(1)[:3].title())
            hm = when and veezi.parse_time(when.group(3))
            if not title or not month or not hm:
                continue
            day = veezi.infer_date(month, int(when.group(2)), today)
            start = la_iso(datetime(day.year, day.month, day.day, *hm))
            url = BASE + path
            if (url, start) in seen:
                continue
            seen.add((url, start))
            excerpt, image = EXCERPT.search(body), IMAGE.search(body)
            out.append(screening(
                theater, _text(title.group(1)), start, url, film_url=url,
                blurb=blurb(excerpt.group(1)) if excerpt else None,
                image=https_url(clean(image.group(1)), BASE) if image else None,
            ))
        if f"page={page_no + 1}" not in page:
            break
    return out
