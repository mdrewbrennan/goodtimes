"""Vista Theater (Los Feliz, Tarantino's).

vistatheater.com is a parked domain; the official site is vistatheaterhollywood.com. Its home page lists
the next ~2 weeks with full details (year, runtime, blurb, director, ticket link, sold-out flag). The
Veezi sessions page (the theater's ticketing vendor) lists further out, with titles only, so we use it
to fill in sessions beyond the home page.
"""

import re
from datetime import date

from . import veezi
from .common import blurb, clean, fetch, screening

SITE_TOKEN = "20xhpa3yt2hhkwt4zjvfcwsaww"
TICKETS = f"https://ticketing.uswest.veezi.com/sessions/?siteToken={SITE_TOKEN}"

THEATERS = [
    {
        "id": "vista",
        "name": "Vista Theater",
        "neighborhood": "Los Feliz",
        "address": "4473 Sunset Dr",
        "url": "https://www.vistatheaterhollywood.com/",
    },
]

ROW = re.compile(r'<div class="shows__grid--row">(.*?)(?=<div class="shows__grid--row">|</section>|\Z)', re.S)
TOKEN = re.compile(
    r"""class=['"]text__size-4 month['"]>(?P<month>[^<]*)<"""
    r"""|class="text__size-2">(?P<day>[^<]*)<"""
    r"""|<a href="(?P<url>[^"]*)"[^>]*class="(?P<cls>[^"]*)"[^>]*>\s*(?P<time>[^<]*?)\s*(?:<span>|</a>)""")
FORMAT_SUFFIX = re.compile(r"\s+(35mm|70mm|16mm|4K|DCP)(\s+\w+)?\s*$", re.I)


def _text(fragment):
    return clean(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def _norm(title):
    return re.sub(r"[^a-z0-9]", "", title.lower())


def _runtime(info):
    m = re.search(r"(?:(\d+)h)?\s*(?:(\d+)m)", info)
    return int(m.group(1) or 0) * 60 + int(m.group(2)) if m else None


def _home_rows(page, today):
    for row in ROW.findall(page):
        left, _, right = row.partition("shows__grid--poster")
        month, day, prev, slots = None, None, 0, []
        for m in TOKEN.finditer(left):
            if m.group("month"):
                month = veezi.MONTHS[m.group("month").strip()]
            elif m.group("day"):
                day = int(re.match(r"\d+", m.group("day")).group())
                if day < prev:  # row rolled into the next month without a new label
                    month = month % 12 + 1
                prev = day
            elif m.group("url") and day and month:
                hm = veezi.parse_time(m.group("time"))
                if hm:
                    slots.append((veezi.infer_date(month, day, today), hm, m.group("url"), "sold-out" in m.group("cls")))
        title = re.search(r'<h3 class="alt">(.*?)</h3>', right, re.S)
        if not title or not slots:
            continue
        info = re.search(r"<p>(\d{4}\s*\|[^<]*)</p>", right)
        summary = re.search(r"<div class='summary'>(.*?)</div>", right, re.S)
        director = re.search(r'text__size-4">Director</p>\s*<p>(.*?)</p>', right, re.S)
        yield {
            "title": _text(title.group(1)),
            "year": info.group(1)[:4] if info else None,
            "runtime": _runtime(info.group(1)) if info else None,
            "blurb": blurb(summary.group(1)) if summary else None,
            "director": _text(director.group(1)) if director else None,
            "slots": slots,
        }


def scrape(theater):
    today = date.today()
    seen, out, known = set(), [], {}
    for film in _home_rows(fetch(theater["url"]), today):
        known[_norm(film["title"])] = film
        for d, hm, url, sold_out in film["slots"]:
            seen.add((d, hm))
            out.append(screening(
                theater, film["title"], veezi.iso(d, hm), url,
                year=film["year"], director=film["director"], runtime=film["runtime"],
                blurb=film["blurb"], sold_out=sold_out,
            ))
    try:
        extra = veezi.sessions(SITE_TOKEN, today)
    except Exception:
        extra = []
    for s in extra:  # sessions further out than the home page shows (title only)
        if (s["date"], s["hm"]) in seen:
            continue
        seen.add((s["date"], s["hm"]))
        title = FORMAT_SUFFIX.sub("", s["title"])
        key = _norm(title)  # reuse home-page details/title when the same film appears there
        film = next((f for k, f in known.items() if k == key or k.startswith(key) or key.startswith(k)), None) or {}
        out.append(screening(
            theater, film.get("title") or title, veezi.iso(s["date"], s["hm"]), s["url"] or TICKETS,
            year=film.get("year"), director=film.get("director"), runtime=film.get("runtime"),
            blurb=film.get("blurb"), sold_out=s["sold_out"],
        ))
    return out
