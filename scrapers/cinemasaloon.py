"""Cinema Saloon (West Adams): a free movie society at Fais Do-Do, run by young South LA filmmakers.

cinemasaloon.la is a hand-built one-page site for the next night only: the film's title (as the alt
text of a title image and in og:title, "Title · Sat Nov 14"), a "DIRECTED BY ..." line, a logline and
full description, and a screen-reader line with the date and times ("Saturday, November 14. Doors
6:30 pm. Movie 7:30 pm."). No structured data and no year, so we infer the year from the date. If the
page's wording changes we find nothing rather than guess. RSVP is free at /rsvp.
"""

import re
from datetime import date, datetime

from . import veezi
from .common import blurb, clean, fetch, og_image, screening
from .la_offset import la_iso
from .titlecase import smart_case

URL = "https://cinemasaloon.la/"

THEATERS = [
    {
        "id": "cinemasaloon",
        "name": "Cinema Saloon",
        "neighborhood": "West Adams",
        "address": "5253 W Adams Blvd (Fais Do-Do)",
        "url": URL,
    },
]

WHEN = re.compile(r'class="sr">\s*\w+day,\s+([A-Z][a-z]+)\s+(\d{1,2})\b[^<]*?Movie\s+(\d{1,2}(?::\d{2})?\s*[ap]m)', re.I)
TITLE_IMG = re.compile(r'<section class="info[^"]*">\s*<h2>\s*<img[^>]*\salt="([^"]+)"', re.S)
OG_TITLE = re.compile(r'<meta property="og:title" content="([^"]+)"')
DIRECTOR = re.compile(r'<div class="dir">\s*DIRECTED BY\s+([^<]+)</div>', re.I)
LOGLINE = re.compile(r'<p class="logline">(.*?)</p>', re.S)
FULL = re.compile(r'<div class="full">(.*?)</details>', re.S)


def scrape(theater):
    page = fetch(URL)
    when = WHEN.search(page)
    title = TITLE_IMG.search(page) or OG_TITLE.search(page)
    if not when or not title:
        return []
    month = veezi.MONTHS.get(when.group(1).title())
    hm = veezi.parse_time(when.group(3))
    if not month or not hm:
        return []
    day = veezi.infer_date(month, int(when.group(2)), date.today())
    if day < date.today():
        return []
    name = re.split(r"\s+(?:·|&middot;)\s+", clean(title.group(1)))[0]
    director = DIRECTOR.search(page)
    logline, full = LOGLINE.search(page), FULL.search(page)
    # The full description ends with the house blurb ("Howdy, welcome to Cinema Saloon..."); keep the film part.
    film_text = re.split(r"This is what Cinema Saloon|Howdy, welcome", full.group(1))[0] if full else ""
    return [screening(
        theater, name, la_iso(datetime(day.year, day.month, day.day, *hm)), URL + "rsvp", film_url=URL,
        director=smart_case(clean(director.group(1))) if director else None,
        blurb=blurb(" ".join(x for x in [logline and logline.group(1), film_text] if x)),
        image=og_image(page, URL.rstrip("/")),
    )]
