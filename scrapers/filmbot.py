"""Vidiots and Brain Dead Studios.

Both run on the same theater-website platform, which usually embeds every screening as schema.org
JSON-LD (ScreeningEvent + Movie). The JSON-LD is sometimes trimmed to a single featured show, so we
also read the showtime buttons in the page HTML and merge the two, keyed by ticket URL.
"""

import re
from datetime import datetime, timedelta

from .common import blurb, clean, fetch, https_url, json_ld_nodes, runtime_minutes, screening
from .la_offset import la_iso

THEATERS = [
    {
        "id": "vidiots",
        "name": "Vidiots",
        "neighborhood": "Eagle Rock",
        "address": "4884 Eagle Rock Blvd",
        "url": "https://vidiotsfoundation.org/",
        "pages": ["https://vidiotsfoundation.org/", "https://vidiotsfoundation.org/coming-soon/"],
    },
    {
        "id": "braindead",
        "name": "Brain Dead Studios",
        "neighborhood": "Fairfax",
        "address": "611 N Fairfax Ave",
        "url": "https://studios.wearebraindead.com/",
        "pages": ["https://studios.wearebraindead.com/", "https://studios.wearebraindead.com/coming-soon/"],
    },
]


SHOW = re.compile(r'<div class="show-details">(.*?)(?=<div class="show-details">|\Z)', re.S)
# Bookable times are <a href=...>; sold-out ones are <span href=...> with an extra label inside.
SHOWTIME = re.compile(r'<li data-date="(\d+)"\s*>\s*<(?:a|span) href="([^"]+/purchase/\d+/)"[^>]*class="([^"]*)"[^>]*>\s*([^<]+?)\s*<', re.S)


def spec(block, label):
    m = re.search(rf'show-spec-label">{label}:</span>\s*([^<]+)', block)
    return clean(m.group(1)) if m else None


def ld_image(node):
    """The 'image' of a JSON-LD node (a string, a list, or an ImageObject) as an https URL, or None."""
    img = (node or {}).get("image")
    if isinstance(img, list):
        img = img[0] if img else None
    if isinstance(img, dict):
        img = img.get("url")
    return https_url(img) if isinstance(img, str) else None


def block_image(block):
    """The poster <img> of a show block (the one inside .show-poster, else the first <img>)."""
    poster = re.search(r'class="show-poster.*?<img[^>]*?\ssrc="([^"]+)"', block, re.S) or \
        re.search(r'<img[^>]*?\ssrc="([^"]+)"', block)
    return https_url(clean(poster.group(1))) if poster else None


def from_html(theater, page):
    """Screenings from the showtime buttons, for when the JSON-LD leaves some out."""
    out = []
    for block in SHOW.findall(page):
        title = re.search(r'<h2 class="show-title"><a class="title" href="([^"]+)">(.*?)</a>', block, re.S)
        if not title:
            continue
        runtime = re.search(r"(\d+)", spec(block, "Run Time") or "")
        fmt = spec(block, "Format")
        image = block_image(block)
        about = re.search(r'<div class="show-content">(.*?)</div>', block, re.S)
        text = blurb(about.group(1)) if about else None
        if fmt and fmt.lower() != "digital":
            text = f"On {fmt}. {text or ''}".strip()
        for ts, url, cls, time in SHOWTIME.findall(block):
            # data-date is local midnight as a unix timestamp; PST is the safe base for the date itself.
            day = (datetime.utcfromtimestamp(int(ts)) - timedelta(hours=8)).date()
            clock = datetime.strptime(time.strip().upper().replace(" ", ""), "%I:%M%p").time()
            out.append(screening(
                theater, title.group(2), la_iso(datetime.combine(day, clock)), url,
                film_url=title.group(1), year=spec(block, "Release Year"), director=spec(block, "Director"),
                runtime=int(runtime.group(1)) if runtime else None, blurb=text, sold_out="sold-out" in cls,
                image=image))
    return out


def scrape(theater):
    movies, events, pages = {}, {}, []
    for url in theater["pages"]:
        page = fetch(url)
        pages.append(page)
        for node in json_ld_nodes(page):
            if node.get("@type") == "Movie":
                movies[node["@id"]] = node
            elif node.get("@type") in ("ScreeningEvent", "Event") and node.get("startDate"):
                events[node["url"]] = node  # dedupe across pages by ticket URL

    out = []
    for ev in events.values():
        movie = movies.get((ev.get("workPresented") or {}).get("@id"), {})
        offers = ev.get("offers") or []
        is_event = ev["@type"] == "Event"
        out.append(screening(
            theater,
            movie.get("name") or ev["name"].split(" - ")[0],
            ev["startDate"],
            ev["url"],
            film_url=movie.get("url") or (ev["url"] if is_event else None),
            year=movie.get("dateCreated"),
            director=", ".join(clean(d["name"]) for d in movie.get("director", [])),
            runtime=runtime_minutes(movie.get("duration")),
            genres=movie.get("genre"),
            blurb=blurb(movie.get("description") or (ev.get("description") if is_event else "")),
            sold_out=bool(offers) and all(o.get("availability", "").endswith("SoldOut") for o in offers),
            cancelled=ev.get("eventStatus", "").endswith("EventCancelled"),
            special_event=is_event,
            image=ld_image(movie) or ld_image(ev),
        ))

    have = {s["ticket_url"] for s in out}
    html_posters = {}
    for page in pages:
        for s in from_html(theater, page):
            if s["image"] and s["film_url"]:
                html_posters.setdefault(s["film_url"], s["image"])
            if s["ticket_url"] not in have:
                have.add(s["ticket_url"])
                out.append(s)
    for s in out:  # a film whose JSON-LD had no image can still have a poster in the page HTML
        s["image"] = s["image"] or html_posters.get(s["film_url"])
    return out
