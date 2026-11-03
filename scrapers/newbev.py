"""New Beverly Cinema.

The WordPress theme exposes no REST data for programs, so we read the monthly schedule page
(thenewbev.com/schedule/) for dates, times, titles and program pages; each program page for director,
year, runtime and blurb; and the Veezi sessions page for ticket links and sold-out status.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from . import veezi
from .common import blurb, clean, fetch, https_url, og_image, screening

SITE_TOKEN = "fmtswb0qqbym3de6c4bbsqj89m"
TICKETS = f"https://ticketing.uswest.veezi.com/sessions/?siteToken={SITE_TOKEN}"

THEATERS = [
    {
        "id": "newbev",
        "name": "New Beverly Cinema",
        "neighborhood": "Fairfax",
        "address": "7165 Beverly Blvd",
        "url": "https://thenewbev.com/",
        "schedule": "https://thenewbev.com/schedule/",
    },
]

MONTH_HEAD = re.compile(r"<h2>\s*([A-Za-z]+)\s+(\d{4})\s*</h2>")
CARD = re.compile(r'<article class="event-card">(.*?)</article>', re.S)
MOVIE = re.compile(r'<div class="movie row-xl">(.*?)(?=<div class="movie row-xl">|<!-- Upcoming|\Z)', re.S)
DL = re.compile(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", re.S)


def _text(fragment):
    return clean(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def _cards(page):
    heads = [(m.start(), MONTH_HEAD.match(m.group(0)).groups()) for m in MONTH_HEAD.finditer(page)]
    for m in CARD.finditer(page):
        year = None
        for pos, (_, y) in heads:
            if pos < m.start():
                year = int(y)
        body = m.group(1)
        link = re.search(r'<a href="([^"]+)"', body).group(1)
        month = re.search(r'event-card__month">\s*(\w+)', body).group(1)
        day = int(re.search(r'event-card__numb">\s*(\d+)', body).group(1))
        times = [veezi.parse_time(t) for t in re.findall(r'<time class="event-card__time">(.*?)</time>', body, re.S)]
        title_html = re.search(r'<h4 class="event-card__title">(.*?)</h4>', body, re.S).group(1)
        titles = [_text(t) for t in re.split(r"/\s*<br\s*/?>", title_html)]
        titles = [re.sub(r"\s*\(Schedule Change\)\s*$", "", t, flags=re.I) for t in titles if t]
        yield date(year, veezi.MONTHS[month], day), [t for t in times if t], titles, link


def _program(url):
    """Per-film details from a program page: list of dicts in page order."""
    try:
        page = fetch(url)
    except Exception:
        return []
    films = []
    fallback = og_image(page)
    for block in MOVIE.findall(page):
        title = re.search(r'<h2 class="movie__title">(.*?)</h2>', block, re.S)
        paras = re.findall(r"<p>(.*?)</p>", block.split('class="movie__details"')[0], re.S)
        details = {_text(k): _text(v) for k, v in DL.findall(block)}
        runtime = re.match(r"(\d+)", details.get("Running Time", ""))
        text = blurb(paras[0]) if paras else None
        if text and len(text) > 500:
            text = text[:497].rsplit(" ", 1)[0] + "..."
        poster = re.search(r'<img[^>]*?\ssrc="([^"]+)"', block.split('class="movie__details"')[0])
        films.append({
            "image": https_url(clean(poster.group(1))) if poster else fallback,
            "title": _text(title.group(1)) if title else None,
            "year": (re.match(r"\d{4}", details.get("Year", "")) or [None])[0],
            "director": details.get("Director") or None,
            "runtime": int(runtime.group(1)) if runtime else None,
            "blurb": text,
        })
    return films


def scrape(theater):
    cards = list(_cards(fetch(theater["schedule"])))
    try:
        sess = veezi.sessions(SITE_TOKEN)
    except Exception:
        sess = []
    by_day = {}
    for s in sess:
        by_day.setdefault(s["date"], []).append(s)

    links = sorted({c[3] for c in cards})
    with ThreadPoolExecutor(max_workers=4) as pool:
        programs = dict(zip(links, pool.map(_program, links)))

    out = []
    for d, times, titles, link in cards:
        if not times:
            continue
        details = programs.get(link) or []
        day_sessions = by_day.get(d, [])
        first = next((s for s in day_sessions if s["hm"] == times[0]), None)
        for i, title in enumerate(titles):
            hm = times[i] if i < len(times) else times[-1]
            # a double feature is one Veezi session (at the first showtime) covering both titles
            sess_ = next((s for s in day_sessions if s["hm"] == hm), first)
            info = details[i] if len(details) == len(titles) else next(
                (x for x in details if x["title"] and x["title"].lower() == title.lower()), {})
            out.append(screening(
                theater, title, veezi.iso(d, hm),
                (sess_ or {}).get("url") or (TICKETS if (sess_ or {}).get("sold_out") else link),
                film_url=link,
                year=info.get("year"),
                director=info.get("director"),
                runtime=info.get("runtime"),
                blurb=info.get("blurb"),
                image=info.get("image"),
                sold_out=bool(sess_ and sess_["sold_out"]),
            ))
    return out
