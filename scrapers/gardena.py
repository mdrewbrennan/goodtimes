"""Gardena Cinema.

The site is a client-rendered Next.js app (Veezi-backed ticketing). It loads showtimes from
  /api/movie/playing-now
which returns every movie with dated sessionTimes, Veezi booking links and sold-out flags.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from .common import blurb, fetch_json, https_url, screening

THEATERS = [
    {
        "id": "gardena",
        "name": "Gardena Cinema",
        "neighborhood": "Gardena",
        "address": "14948 Crenshaw Blvd",
        "url": "https://www.gardenacinema.com/",
        "api": "https://www.gardenacinema.com/api/movie/playing-now",
    },
]

LA = ZoneInfo("America/Los_Angeles")


def _start(date, time):
    t = datetime.strptime(time.strip().upper(), "%I:%M%p")
    return datetime.strptime(date, "%Y-%m-%d").replace(hour=t.hour, minute=t.minute, tzinfo=LA).isoformat()


def scrape(theater):
    out = []
    for m in fetch_json(theater["api"]):
        inner = m.get("director") if isinstance(m.get("director"), dict) else {}
        directors = inner.get("director") or []
        film_url = f"https://www.gardenacinema.com/movie/{m['url']}"
        try:
            runtime = int(m.get("duration")) or None
        except (TypeError, ValueError):
            runtime = None
        text = blurb(m.get("synopsisShort"))
        image = https_url(m.get("imageVerticalUrl"))
        is_event = not directors  # no director credited: live/community events (e.g. short-film club)
        for s in m.get("sessionTimes") or []:
            out.append(screening(
                theater,
                m["title"],
                _start(s["date"], s["time"]),
                s.get("bookingLink") or film_url,
                film_url=film_url,
                director=", ".join(directors),
                runtime=runtime,
                blurb=text,
                image=image,
                sold_out=bool(s.get("isSoldOut")),
                special_event=is_event and "club" in m["title"].lower(),
            ))
    out.sort(key=lambda r: r["start"])
    return out
