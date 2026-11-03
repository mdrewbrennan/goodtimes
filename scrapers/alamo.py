"""Alamo Drafthouse (Los Angeles market).

drafthouse.com's own front end reads one JSON document per market:
  /s/mother/v2/schedule/market/<market-slug>
It holds every presentation (show + optional event wrapper) and every session with local start time
and status. The LA market currently has a single cinema (DTLA).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from .common import blurb, clean, fetch_json, screening

NOT_EVENTS = {"unrated"}  # event-type labels that describe the print, not an event

THEATERS = [
    {
        "id": "alamo-dtla",
        "name": "Alamo Drafthouse DTLA",
        "neighborhood": "Downtown LA",
        "address": "700 W 7th St, Ste U240",
        "url": "https://drafthouse.com/los-angeles",
        "market": "los-angeles",
        "cinema_id": "1701",
        "specials_only": True,  # mostly first-run, so the site shows only its special screenings
    },
]

API = "https://drafthouse.com/s/mother/v2/schedule/market/"


def _iso(local, tz):
    return datetime.fromisoformat(local).replace(tzinfo=ZoneInfo(tz)).isoformat()


def scrape(theater):
    data = fetch_json(API + theater["market"])["data"]
    presentations = {p["slug"]: p for p in data["presentations"]}
    out = []
    for s in data["sessions"]:
        if s["cinemaId"] != theater["cinema_id"] or s.get("isHidden"):
            continue
        p = presentations.get(s["presentationSlug"])
        if not p or p.get("isHidden"):
            continue
        show = p["show"]
        event = p.get("event") or {}
        text = blurb(show.get("headline"))
        label = clean(event.get("eventTypeTitleOverride") or (p.get("eventType") or {}).get("title") or "")
        if label:
            text = f"{label}. {text}" if text else label
        if s.get("ticketingExperience") == "BABY_DAY":
            text = ("Baby Day show (lights up, sound down). " + (text or "")).strip()
        film_url = f"https://drafthouse.com/los-angeles/show/{show['slug']}"
        item = screening(
            theater,
            show["title"],
            _iso(s["showTimeClt"], s.get("cinemaTimeZoneName") or "America/Los_Angeles"),
            film_url,  # the site's showtime buttons have no deep link; the show page lists them
            film_url=film_url,
            blurb=text,
            # Alamo labels its events (Q&As, movie parties, sing-alongs, fan screenings); plain shows have none.
            special_event=bool(label) and label.lower() not in NOT_EVENTS,
            sold_out=s["status"] == "SOLDOUT",
            cancelled=s["status"] == "CANCELLED",
        )
        if item["special_event"]:
            item["event_label"] = label  # shown as the tag in place of a generic one
        out.append(item)
    out.sort(key=lambda r: r["start"])
    return out
