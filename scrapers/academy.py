"""Academy Museum of Motion Pictures (Miracle Mile): the David Geffen and Ted Mann theaters.

Sessions come from the museum's Ticketure ticketing API (tickets.academymuseum.org/cached_api), the same
public JSON its calendar page reads: one event template per program, with its sessions in UTC. Film
details (year, runtime, director, format, guests, synopsis, image) and the program page link come from
the calendar page itself, a Next.js page whose embedded data holds a Contentful "ProgramEvent" per
program, keyed by the same Ticketure id. Talks, tours and workshops are left out.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from .common import blurb, clean, fetch, fetch_json, https_url, screening
from .la_offset import la_iso

SITE = "https://www.academymuseum.org"
API = "https://tickets.academymuseum.org/cached_api/events/available"
FILM_CATEGORIES = ("Film Screening", "Film Screening: Matinee", "Film Screening: Double Feature")
OTHER_CATEGORIES = ("Program", "Special Event")  # kept only when the museum's own data calls it a film

THEATERS = [
    {
        "id": "academy-museum",
        "name": "Academy Museum",
        "neighborhood": "Miracle Mile",
        "address": "6067 Wilshire Blvd",
        "url": SITE + "/calendar?programTypes=Screenings",
    },
]

NEXT_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
PROGRAM = re.compile(r'\{"sys":\{"id":"[^"]+"\},"__typename":"ProgramEvent"')
FORMATS = re.compile(r"\b(16mm|35mm|70mm)\b", re.I)


def _rich_text(node):
    """Plain text of a Contentful rich-text field ({"json": {...}}), one line per paragraph."""
    if isinstance(node, str):
        return node.strip()
    out = []

    def walk(n):
        if n.get("nodeType") == "text":
            out.append(n.get("value", ""))
        for child in n.get("content", []):
            walk(child)
        if n.get("nodeType", "").startswith(("paragraph", "heading")):
            out.append("\n")

    if isinstance(node, dict):
        walk(node.get("json") or {})
    return re.sub(r"[ \t\xa0]+", " ", "".join(out)).strip()


def _programs():
    """Calendar-page program details, keyed by Ticketure event id."""
    page = fetch(SITE + "/calendar")
    data = "".join(json.loads(chunk) for chunk in NEXT_CHUNK.findall(page))
    decoder, out = json.JSONDecoder(), {}
    for m in PROGRAM.finditer(data):
        try:
            obj, _ = decoder.raw_decode(data, m.start())
        except ValueError:
            continue
        if obj.get("ticketureIdProduction"):
            out[obj["ticketureIdProduction"]] = obj
    return out


def _details(program):
    if not program:
        return {}
    meta = _rich_text(program.get("filmMetadata1"))
    first = meta.split("\n")[0]
    year = re.match(r"\s*(\d{4})\b", first)
    runtime = re.search(r"(\d+)\s*min", first)
    director = re.search(r"DIRECTED BY:\s*(.+)", meta, re.I)
    guest = program.get("specialGuest")
    guest = _rich_text(guest) if guest else ""
    fmt = FORMATS.search(program.get("filmFormat1") or "")
    parts = [guest, f"Presented in {fmt.group(1)}." if fmt else "", _rich_text(program.get("filmDescription1"))]
    image = (program.get("image") or {}).get("url")
    return {
        "year": year.group(1) if year else None,
        "runtime": int(runtime.group(1)) if runtime else None,
        "director": clean(director.group(1)).rstrip(" .") if director else None,
        "blurb": blurb(" ".join(p if p.endswith((".", "!", "?")) else p + "." for p in parts if p)),
        "image": https_url(image),
        "url": f"{SITE}/programs/detail/{program['slug']}" if program.get("slug") else None,
        "is_film": program.get("type") == "Film",
    }


def _la_time(utc_text):
    """'2026-11-04T03:30:00Z' -> LA wall-clock ISO string with its offset."""
    utc = datetime.fromisoformat(utc_text.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    local = utc - timedelta(hours=7)
    if not la_iso(local).endswith("-07:00"):  # standard time
        local = utc - timedelta(hours=8)
    return la_iso(local)


def scrape(theater):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    query = urlencode({
        "event_session.start_datetime._gte": now,
        "category._in": ",".join(FILM_CATEGORIES + OTHER_CATEGORIES),
        "_embed": "event_session",
        "_sort": "event_session.start_datetime",
    }, safe=",:")
    data = fetch_json(f"{API}?{query}")
    templates = {t["id"]: t for t in data["event_template"]["_data"]}
    try:
        programs = _programs()
    except Exception:  # details are a bonus; the sessions alone still make a listing
        programs = {}

    out = []
    for session in data["event_session"]["_data"]:
        template = templates.get(session["event_template_id"])
        if not template:
            continue
        info = _details(programs.get(template["id"]))
        if template["category"] not in FILM_CATEGORIES and not info.get("is_film"):
            continue
        out.append(screening(
            theater, template["name"], _la_time(session["start_datetime"]), info.get("url") or theater["url"],
            film_url=info.get("url"), year=info.get("year"), director=info.get("director"),
            runtime=info.get("runtime"), blurb=info.get("blurb"), image=info.get("image"),
            sold_out=bool(session.get("sold_out")),
        ))
    return out
