"""Veggie Cloud (Highland Park): a DIY backyard/living-room screening series. Free, digital projection.

The schedule is one hand-written Cargo Collective page: an UPCOMING list, then PAST, each entry a bold
"Sunday, October 4, 2026" line, a title line, optional "(2025, dir. Name, 101min)" credits, then a
paragraph and a flyer image. There is no structured data, so we read every dated entry on the page and
keep the ones from today on, skipping entries that plug an event at another venue. The header says
"Screenings at 8pm"; an entry that ties its own time to the show ("7:30 pm film") wins. If the page's wording changes, this finds nothing rather than guessing, and between
seasons the UPCOMING list is often empty ("Let's see!"), so zero screenings is normal.
"""

import html
import re
from datetime import date, datetime

from .common import blurb, clean, fetch, https_url, screening
from .la_offset import la_iso

URL = "https://cargocollective.com/veggiecloud"

THEATERS = [
    {
        "id": "veggiecloud",
        "name": "Veggie Cloud",
        "neighborhood": "Highland Park",
        "address": "5210 Monte Vista St",
        "url": URL,
    },
]

DATE_LINE = re.compile(r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,\s+([A-Z][a-z]+ \d{1,2},? \d{4})$")
CREDITS = re.compile(r"\((\d{4}),\s*dir\.\s*([^,]+?),\s*(\d+)\s*(min|hr)\)")
TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\b", re.I)
_T = r"\d{1,2}(?::\d{2})?\s*[ap]\.?m\b"
# Only a time tied to the show counts ("7:30 pm film", "screening at 8pm"); blurbs often give times of
# events elsewhere.
SHOW_TIME = re.compile(rf"({_T})\s*(?:film|screening|show)|(?:film|screening|show)s?\s*(?:at|@|:)\s*({_T})", re.I)
# Some entries are the curators' events at other venues, flagged by a note just before them.
ELSEWHERE = re.compile(r"\b(?:will take place|takes place|event is|program is|is happening) at\b", re.I)
DEFAULT_TIME = re.compile(r"Screenings at\s+(\d{1,2}(?::\d{2})?\s*[ap]m)", re.I)
IMG = re.compile(r'<img[^>]*?\ssrc="([^"]+)"')


def _lines(page):
    """The page body as (text, image_url) lines, split on <br>; image_url is set on lines that hold a flyer."""
    start = page.find("V E G G I E")
    body = page[start:] if start >= 0 else page
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", body, flags=re.S)
    out = []
    for chunk in re.split(r"<br\s*/?>|</p>|</div>", body):
        img = IMG.search(chunk)
        text = clean(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", chunk)))
        out.append((text, https_url(html.unescape(img.group(1))) if img else None))
    return out


def _hm(text):
    m = TIME.search(text or "")
    if not m:
        return None
    return int(m.group(1)) % 12 + (12 if m.group(3).lower() == "p" else 0), int(m.group(2) or 0)


def _date(text):
    """'October 4, 2026' or 'Oct 4, 2026' (older entries abbreviate), else None."""
    text = text.replace(",", "")
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def entries(page):
    """Every dated entry on the page, past and upcoming."""
    default = DEFAULT_TIME.search(re.sub(r"<[^>]+>", " ", page))
    default_hm = _hm(default.group(1)) if default else (20, 0)
    lines = _lines(page)
    found, offsite_next = [], False
    for i, (text, _) in enumerate(lines):
        m = DATE_LINE.match(text)
        if not m:
            continue
        # "The following event is at Cinefamily!" ends one entry but describes the next one.
        offsite, offsite_next = offsite_next, False
        day = _date(m.group(1))
        rest, image = [], None
        for later, img in lines[i + 1:]:
            if DATE_LINE.match(later) or later in ("PAST", "UPCOMING"):
                break
            if ELSEWHERE.search(later):
                if "following" in later.lower():
                    offsite_next = True
                    break
                offsite = True  # "this screening will take place AT CINEFAMILY"
            if img and not image:
                image = img
            if later:
                rest.append(later)
        if not day or not rest or offsite:
            continue
        title, details = rest[0], rest[1:]
        credits = CREDITS.search(details[0]) if details and details[0].startswith("(") else None
        text_all = " ".join(details)
        show = SHOW_TIME.search(text_all)
        found.append({
            "date": day, "hm": _hm(show.group(1) or show.group(2)) if show else default_hm, "title": title, "image": image,
            "year": credits.group(1) if credits else None,
            "director": credits.group(2).strip() if credits else None,
            "runtime": int(credits.group(3)) * (60 if credits.group(4) == "hr" else 1) if credits else None,
            "blurb": blurb(text_all),
        })
    return found


def scrape(theater):
    today = date.today()
    out = []
    for e in entries(fetch(URL)):
        if e["date"] < today:
            continue
        start = la_iso(datetime(e["date"].year, e["date"].month, e["date"].day, *e["hm"]))
        out.append(screening(
            theater, e["title"], start, URL, film_url=URL, year=e["year"], director=e["director"],
            runtime=e["runtime"], blurb=e["blurb"], image=e["image"],
        ))
    return out
