"""Hand-entered screenings, for venues whose schedules can't be scraped (scrapers/manual.json).

Some venues only sell through ticketing sites that block scrapers (the Palace Theatre's AXS listings)
or announce one-off film nights nowhere machine-readable. manual.json lists those venues and their
screenings by hand; this module turns them into ordinary listings, so they get the same dedupe, TMDB
posters, tags and calendar files as everything else. Instructions are in the file's "_how" key.

Screenings that have already started are dropped. An entry missing a field or with a bad date is
skipped and printed, so one typo doesn't hide the rest; if the file itself won't parse, every manual
venue fails together and scrape.py reports it.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .common import https_url, screening
from .la_offset import la_iso

DATA = Path(__file__).with_name("manual.json")
REQUIRED_THEATER = ("id", "name", "neighborhood", "address", "url")
REQUIRED_SCREENING = ("theater", "title", "start", "url")


def _load():
    return json.loads(DATA.read_text(encoding="utf-8"))


def _theaters():
    try:
        data = _load()
    except (OSError, ValueError) as e:
        print(f"manual.json: can't read ({e})", file=sys.stderr)
        return []
    out = []
    for t in data.get("theaters") or []:
        if all(t.get(k) for k in REQUIRED_THEATER):
            out.append({k: t[k] for k in REQUIRED_THEATER})
        else:
            print(f"manual.json: skipping theater missing {REQUIRED_THEATER}: {t}", file=sys.stderr)
    return out


THEATERS = _theaters()


def _la_now():
    """Current Los Angeles wall-clock time, whatever the build machine's time zone (Netlify runs in UTC)."""
    utc = datetime.now(timezone.utc).replace(tzinfo=None)
    local = utc - timedelta(hours=7)
    return local if la_iso(local).endswith("-07:00") else utc - timedelta(hours=8)


def scrape(theater):
    data = _load()
    now = _la_now()
    out = []
    for s in data.get("screenings") or []:
        if s.get("theater") != theater["id"]:
            continue
        try:
            missing = [k for k in REQUIRED_SCREENING if not s.get(k)]
            if missing:
                raise ValueError(f"missing {', '.join(missing)}")
            start = datetime.strptime(s["start"].strip(), "%Y-%m-%d %H:%M")
            runtime = int(s["runtime"]) if s.get("runtime") else None
        except (ValueError, TypeError, AttributeError) as e:
            print(f"manual.json: skipping {s.get('title')!r} ({e})", file=sys.stderr)
            continue
        if start < now:
            continue
        out.append(screening(
            theater, s["title"], la_iso(start), s["url"], film_url=s.get("film_url") or s["url"],
            year=s.get("year"), director=s.get("director"), runtime=runtime, blurb=s.get("blurb"),
            image=https_url(s.get("image")), special_event=bool(s.get("special_event")),
        ))
    return out
