"""Philosophical Research Society (PRS), Los Feliz.

prs.org/events.html embeds a Tockify calendar (calname "eventbrite"). Tockify serves the same calendar
as public JSON at tockify.com/api/ngevent, which the embed widget uses (no key needed). Each event
carries a title, description, start in epoch millis plus the calendar's UTC offset, and a ticket link
(mostly Eventbrite).

PRS also hosts lectures, sound baths, reading groups, classes and concerts, so we keep only events whose
title marks them as film: a (YYYY) release year, "screening", "movie", "film", "premiere", "documentary",
"cinema". Of those, ones with a Q&A / lecture format are marked special_event.
"""

import re
from datetime import datetime, timedelta, timezone

from .common import blurb, clean, fetch_json, screening
from .la_offset import la_iso

API = "https://tockify.com/api/ngevent?calname=eventbrite&max=100&startms={ms}&offset={offset}"

THEATERS = [
    {
        "id": "prs",
        "name": "Philosophical Research Society",
        "neighborhood": "Los Feliz",
        "address": "3910 Los Feliz Blvd",
        "url": "https://www.prs.org/events.html",
    },
]

FILM = re.compile(r"\(\d{4}\)|\('\d\d\)|screening|movie|film|premiere|documentary|cinema|archival exploration", re.I)
LIVE_FORMAT = re.compile(r"q&a|panel|lecture|exploration|talk", re.I)
YEAR = re.compile(r"\((\d{4})\)|\('(\d\d)\)")


def events(since):
    ms = int(since.replace(tzinfo=timezone.utc).timestamp() * 1000)
    offset = 0
    while True:
        data = fetch_json(API.format(ms=ms, offset=offset))
        yield from data["events"]
        if not data["metaData"].get("hasNext") or not data["events"] or offset > 1000:
            return
        offset += len(data["events"])


def scrape(theater):
    now = datetime.now()
    out, seen = [], set()
    for ev in events(now - timedelta(hours=3)):
        content = ev["content"]
        title = clean(content["summary"]["text"])
        if not FILM.search(title):
            continue
        start = ev["when"]["start"]
        local = datetime.utcfromtimestamp((start["millis"] + start["offset"]) / 1000)
        if local < now:
            continue
        key = (ev["eid"]["uid"], ev["eid"]["tid"])
        if key in seen:
            continue
        seen.add(key)

        cancelled = title.upper().startswith("CANCELED") or title.upper().startswith("CANCELLED")
        title = re.sub(r"^CANCEL+ED:\s*", "", title, flags=re.I)
        link = (content.get("customButtonLink") or "").split("?")[0] or None
        event_page = f"https://tockify.com/eventbrite/detail/{key[0]}/{key[1]}"
        y = YEAR.search(title)
        year = None
        if y:
            year = y.group(1) or ("19" + y.group(2))
        out.append(screening(
            theater, title, la_iso(local), link or event_page,
            year=year, blurb=blurb(content.get("description", {}).get("text")),
            cancelled=cancelled, special_event=bool(LIVE_FORMAT.search(title))))
    return out
