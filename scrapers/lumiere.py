"""Lumiere Cinema at the Music Hall (Beverly Hills; formerly Laemmle Music Hall).

lumierecinemala.com is a WordPress site with a custom showtimes template. The "tickets-by-film"
page lists every upcoming showtime for every film on ONE page (each linking to lumieretickets.com),
so that is the source; each film page is then read once for year / director / genres / synopsis.
Dates on the listing have no year, so it is inferred (the nearest year within +/- 6 months of today).
"""

import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

from .common import blurb, clean, fetch, og_image, screening
from .la_offset import la_iso

LIST_URL = "https://lumierecinemala.com/tickets-by-film"

THEATERS = [
    {
        "id": "lumiere-music-hall",
        "name": "Lumiere Cinema at the Music Hall",
        "neighborhood": "Beverly Hills",
        "address": "9036 Wilshire Blvd",
        "url": "https://lumierecinemala.com/",
    },
]

FILM = re.compile(r'<div class="film">(.*?)(?=<div class="film">|<div class="footer|\Z)', re.S)
TITLE = re.compile(r'<h3 class="film-title"><a href="([^"]+)">(.*?)</a>', re.S)
RUNTIME = re.compile(r'Runtime:\s*(\d+)')
DATE_GROUP = re.compile(r'<h4 class="show-date">([^<]+)</h4>(.*?)(?=<h4 class="show-date">|\Z)', re.S)
SHOWTIME = re.compile(r'<a href="([^"]+)" class="showtime-button[^"]*">\s*(\d{1,2}:\d\d\s*[AP]M)\s*</a>', re.I)
RATING = re.compile(r'\s*\((?:G|PG|PG-13|R|NC-17|NR|TBD)\)\s*$')
SPECIAL = re.compile(r'double feature|film festival|\bLAIFF\b|open screen|live', re.I)
SMALL = {"a", "an", "the", "of", "and", "or", "in", "on", "at", "to", "for", "vs.", "vs", "but"}


def _nice_title(raw):
    t = RATING.sub("", clean(raw))
    if t != t.upper():
        return t
    words = t.lower().split(" ")
    t = " ".join(w if (i and w in SMALL) else w[:1].upper() + w[1:] for i, w in enumerate(words))
    t = re.sub(r"/([a-z])", lambda m: "/" + m.group(1).upper(), t)
    return re.sub(r"\bLaiff\b", "LAIFF", t)


def _infer_date(label, today):
    """'Monday, November 2' -> date, picking the year closest to today."""
    month_day = label.split(",", 1)[1].strip()
    best = None
    for year in (today.year - 1, today.year, today.year + 1):
        d = datetime.strptime(f"{month_day} {year}", "%B %d %Y").date()
        if best is None or abs((d - today).days) < abs((best - today).days):
            best = d
    return best


def _film_details(url):
    try:
        page = fetch(url)
    except Exception:
        return {}
    body = page[page.find("<body"):]
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", body, flags=re.S)
    segs = [clean(s) for s in re.split(r"<[^>]+>", body)]
    segs = [s for s in segs if s]
    out = {"image": og_image(page, "https://lumierecinemala.com")}
    for i, s in enumerate(segs):
        if re.fullmatch(r"\d+ min", s) and i + 1 < len(segs) and re.fullmatch(r"\d{4}", segs[i + 1]):
            out["year"] = segs[i + 1]
            if i + 4 < len(segs) and not segs[i + 4].endswith(":"):
                out["genres"] = [g.strip() for g in segs[i + 4].split(",") if g.strip()]
            break
    labels = [i for i, s in enumerate(segs) if s in ("Director:", "Written By:", "Starring:")]
    for i in labels:
        if segs[i] == "Director:" and i + 1 < len(segs):
            out["director"] = segs[i + 1]
    if labels:
        nxt = labels[-1] + 2
        if nxt < len(segs) and len(segs[nxt]) > 60:
            out["blurb"] = blurb(segs[nxt])
    return out


def scrape(theater):
    today = date.today()
    listing = fetch(LIST_URL)
    shows, films = [], {}
    for block in FILM.findall(listing):
        t = TITLE.search(block)
        if not t:
            continue
        url, title = t.group(1), _nice_title(re.sub(r"<[^>]+>", "", t.group(2)))
        rt = RUNTIME.search(block)
        films[url] = {"title": title, "runtime": int(rt.group(1)) if rt else None}
        for label, chunk in DATE_GROUP.findall(block):
            day = _infer_date(label, today)
            if day < today:
                continue
            for ticket, tm in SHOWTIME.findall(chunk):
                when = datetime.strptime(f"{day.isoformat()} {tm.replace(' ', '').upper()}", "%Y-%m-%d %I:%M%p")
                shows.append((url, when, html.unescape(ticket)))

    with ThreadPoolExecutor(max_workers=4) as pool:
        details = dict(zip(films, pool.map(_film_details, films)))

    out = []
    for url, when, ticket in shows:
        f, det = films[url], details.get(url, {})
        out.append(screening(
            theater, f["title"], la_iso(when), ticket,
            film_url=url, year=det.get("year"), director=det.get("director"),
            runtime=f["runtime"], genres=det.get("genres"), blurb=det.get("blurb"), image=det.get("image"),
            special_event=bool(SPECIAL.search(f["title"])),
        ))
    return out
