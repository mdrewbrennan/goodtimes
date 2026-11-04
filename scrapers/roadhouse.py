"""Permanent Records Roadhouse (Cypress Park): a record-store bar; we list its film nights only.

roadhouse.permanentrecordsla.com is a hand-made HTML page listing every upcoming night as a date line
("Thursday, November 5th - 9PM"), the lineup, a price and a ticket link (Opendate). It's almost all
bands, and band names are often film words ("Movie Club", "Social Cinema"), so the filter is strict:
a night counts only if its text says screening, film night, movie night, double feature or 16mm/35mm.
On the past-events pages for 2025-2026 nothing qualified, so zero screenings is the usual result.
"""

import re
from datetime import date, datetime

from . import veezi
from .common import blurb, clean, fetch, screening
from .la_offset import la_iso

URL = "http://roadhouse.permanentrecordsla.com/"

THEATERS = [
    {
        "id": "roadhouse",
        "name": "Permanent Records Roadhouse",
        "neighborhood": "Cypress Park",
        "address": "3216 N Figueroa St",
        "url": URL,
    },
]

DATE_LINE = re.compile(r"^\w+day,\s+([A-Z][a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s*-\s*(\d{1,2}(?::\d{2})?\s*[AP]M)", re.I)
FILM_NIGHT = re.compile(r"\bscreenings?\b|\bfilm night\b|\bmovie night\b|\bdouble feature\b|\b(?:16|35)\s?mm\b", re.I)
SKIP = re.compile(r"^(?:\$.*|buy tickets!?|rsvp here!?|details coming soon\.*|\d+\s*(?:advance|dos)|per|player)$", re.I)


def _hm(text):
    """'7pm', '7:30 pm', '9PM' -> (hour, minute), else None."""
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\b", text or "", re.I)
    if not m:
        return None
    return int(m.group(1)) % 12 + (12 if m.group(3).lower() == "p" else 0), int(m.group(2) or 0)


def _lines(page):
    page = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    out = []
    for chunk in re.split(r"<br\s*/?>|</p>|</div>|</td>|</tr>|</h\d>|</a>", page):
        text = clean(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", chunk)))
        link = re.search(r'href="(https?://[^"]+)"', chunk)
        if text or link:
            out.append((text, link.group(1) if link else None))
    return out


def scrape(theater):
    today = date.today()
    lines = _lines(fetch(URL))
    out = []
    for i, (text, _) in enumerate(lines):
        m = DATE_LINE.match(text)
        month = m and veezi.MONTHS.get(m.group(1).title())
        hm = m and _hm(m.group(3))
        if not month or not hm:
            continue
        rest = text[m.end():].strip()  # the lineup often shares the date's line
        body, ticket = ([rest] if rest and not SKIP.match(rest) else []), None
        for later, link in lines[i + 1:]:
            if DATE_LINE.match(later):
                break
            if link and "opendate" in link and not ticket:
                ticket = link
            if later and not SKIP.match(later):
                body.append(later)
        text_all = " ".join(body)
        if not body or not FILM_NIGHT.search(text_all):
            continue
        day = veezi.infer_date(month, int(m.group(2)), today)
        if day < today:
            continue
        out.append(screening(
            theater, body[0], la_iso(datetime(day.year, day.month, day.day, *hm)), ticket or URL,
            film_url=URL, blurb=blurb(text_all),
        ))
    return out
