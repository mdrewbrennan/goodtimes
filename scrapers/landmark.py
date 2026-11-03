"""Landmark Theatres in Los Angeles: Nuart, Westwood, Sunset (West Hollywood), Pasadena.

landmarktheatres.com is a Gatsby app that loads showtimes client-side from its own JSON endpoints:
  /api/gatsby-source-boxofficeapi/schedule?from=..&to=..&theaters={"id":..,"timeZone":..}
  /api/gatsby-source-boxofficeapi/movies?basic=false&ids=..&ids=..   (title, directors, synopsis, release)
Schedule times are LA wall-clock times. Landmark lists these four as its "Los Angeles locations".
"""

import json
import re
import urllib.parse
from datetime import date, datetime, timedelta

from .common import blurb, fetch_json, screening
from .la_offset import la_iso

API = "https://www.landmarktheatres.com/api/gatsby-source-boxofficeapi/"
DAYS_AHEAD = 60

THEATERS = [
    {"id": "nuart", "name": "Nuart Theater", "operator": "Landmark", "neighborhood": "West LA",
     "address": "11272 Santa Monica Blvd",
     "url": "https://www.landmarktheatres.com/our-locations/x00cw-landmark-nuart-theatre-west-los-angeles/",
     "landmark_id": "X00CW"},
    {"id": "landmark-westwood", "name": "Landmark Westwood", "neighborhood": "Westwood",
     "address": "1045 Broxton Ave",
     "url": "https://www.landmarktheatres.com/our-locations/x00d9-landmark-westwood-los-angeles/",
     "landmark_id": "X00D9"},
    {"id": "landmark-sunset", "name": "Landmark Sunset", "neighborhood": "West Hollywood",
     "address": "8000 W Sunset Blvd",
     "url": "https://www.landmarktheatres.com/our-locations/g01si-landmark-theatres-sunset/",
     "landmark_id": "G01SI"},
    {"id": "landmark-pasadena", "name": "Landmark Pasadena", "neighborhood": "Pasadena",
     "address": "673 E Colorado Blvd",
     "url": "https://www.landmarktheatres.com/our-locations/g01ch-landmark-theatres-pasadena/",
     "landmark_id": "G01CH"},
]

_movie_cache = {}


def _slug(title):
    s = title.lower().replace("$", "dollar").replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _load_movies(ids):
    need = [i for i in ids if i not in _movie_cache]
    for k in range(0, len(need), 10):
        chunk = need[k:k + 10]
        query = "basic=false&castingLimit=1&" + "&".join(f"ids={urllib.parse.quote(i)}" for i in chunk)
        for m in fetch_json(API + "movies?" + query):
            _movie_cache[str(m["id"])] = m
    return {i: _movie_cache.get(i) for i in ids}


def _showtime_key(show):
    return show["startsAt"]


def _ticket_url(show, fallback):
    for t in (show.get("data") or {}).get("ticketing") or []:
        if t.get("provider") == "default" and t.get("urls"):
            return t["urls"][0]
    for t in (show.get("data") or {}).get("ticketing") or []:
        if t.get("urls"):
            return t["urls"][0]
    return fallback


def scrape(theater):
    tid = theater["landmark_id"]
    today = date.today()
    theaters = json.dumps({"id": tid, "timeZone": "America/Los_Angeles"}, separators=(",", ":"))
    url = (API + "schedule?from=" + today.isoformat() + "T00:00:00&theaters=" + urllib.parse.quote(theaters)
           + "&to=" + (today + timedelta(days=DAYS_AHEAD)).isoformat() + "T00:00:00")
    schedule = fetch_json(url)[tid]["schedule"]
    movies = _load_movies(list(schedule))

    out = []
    for movie_id, days in schedule.items():
        m = movies.get(movie_id) or {}
        title = m.get("title") or (m.get("locale") or {}).get("title")
        if not title:
            continue
        directors = [
            " ".join(filter(None, [(n.get("person") or {}).get("firstName"), (n.get("person") or {}).get("lastName")]))
            for n in ((m.get("directors") or {}).get("nodes") or [])
        ]
        runtime = m.get("runtime")  # seconds
        release = m.get("release") or ""
        film_url = f"https://www.landmarktheatres.com/movies/{movie_id}-{_slug(title)}/"
        by_start = {}
        for shows in days.values():
            for s in shows:
                prev = by_start.get(s["startsAt"])
                # Reserved/general-seating variants share a start time: keep one, sold out only if all are
                sold = "Internal.Data.SoldOut" in s["tags"] or (s.get("occupancy") or {}).get("rate", 0) >= 100
                if prev is None:
                    by_start[s["startsAt"]] = (s, sold)
                else:
                    by_start[s["startsAt"]] = (prev[0], prev[1] and sold)
        for starts_at, (s, sold) in sorted(by_start.items()):
            when = datetime.strptime(starts_at[:19], "%Y-%m-%dT%H:%M:%S")
            if s.get("isExpired"):
                continue
            out.append(screening(
                theater, title, la_iso(when), _ticket_url(s, film_url),
                film_url=film_url, year=release[:4] or None,
                director=", ".join(d for d in directors if d) or None,
                runtime=round(runtime / 60) if runtime else None,
                genres=[g.strip() for g in (m.get("genres") or "").split(",") if g.strip()],
                blurb=blurb(m.get("synopsis") or (m.get("locale") or {}).get("synopsis")),
                sold_out=sold,
            ))
    return out
