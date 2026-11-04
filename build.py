"""Render data/listings.json into the GOODTIMES site.

  index.html           homepage: what's showing today, upcoming special events
  listings/index.html  every upcoming screening, by day
  404.html             the not-found page
  plus robots.txt, sitemap.xml, the icons, fonts and web app manifest, and Netlify's _redirects and _headers

Both site/ (local preview: python3 -m http.server 8765 -d site) and netlify/ (the folder to deploy) get
the same files. site/share.html is the homepage without its document wrapper, for the claude.ai share link.

To use a real logo, drop logo.svg or logo.png into site/ and rebuild.

Standard library only: python3 build.py
"""

import hashlib
import json
import os
import re
import shutil
import struct
import sys
import urllib.parse
from collections import OrderedDict
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import archive
import tmdb

ROOT = Path(__file__).parent
SITE = ROOT / "site"
LA = ZoneInfo("America/Los_Angeles")  # handles daylight saving; used for "today" and the Updated time
NAME = "GOODTIMES"        # the wordmark
SITE_NAME = "GOODTIMES LA"  # the name search engines, link previews and titles use
TAGLINE = "To Live and Watch Movies in LA"
# While friends test the site, ask search engines not to list it. Set to False at launch.
PREVIEW = False
# The public address, for canonical links, the sitemap and link previews. Netlify sets URL to the site's
# primary domain during its builds; set SITE_URL to override it.
SITE_URL = (os.environ.get("SITE_URL") or os.environ.get("URL") or "http://localhost:8765").rstrip("/")
# IndexNow tells Bing (and the search engines that share its index) which pages changed. The key isn't
# secret: it's published at /<key>.txt so they can check the ping came from this site.
INDEXNOW_KEY = "fa258ddfd891832721dcea6fbfa30ebb"
NETLIFY = ROOT / "netlify"  # drag this folder onto app.netlify.com/drop

# Tags read from each screening's title and blurb. EVENT tags make a screening a special event.
EVENT_TAGS = [
    ("Live score", r"live score"),
    ("Recorded Q&A", r"(pre-recorded|livestream) q&a"),
    ("Guests in person", r"in person|in attendance|followed by a (conversation|q&a)|\bq&a\b|special guests|"
                         r"(thrilled|electrified|excited) to welcome"),
    ("Premiere", r"\bpremiere\b"),
    ("Special screening", r"special (free )?(advance )?screening|presented by|\bpresents\b|birthday"),
    ("Advance screening", r"advance screening"),
    ("Sing-along", r"sing[ -]?along"),
    ("Workshop", r"workshop"),
    ("Book launch", r"book launch"),
    ("Mystery screening", r"surprise screening|mystery screening"),
]
FORMAT_TAGS = [("35mm", r"\b35mm\b"), ("16mm", r"\b16mm\b"), ("70mm", r"\b70mm\b")]

# A festival by name: "GuadaLAjara Film Festival", "2026 PROOF Film Festival". In a title that's enough; in a
# blurb only when the festival is the one presenting ("The PROOF Film Festival is thrilled..."), so a film
# that merely "premiered at the Venice Film Festival" isn't tagged.
FEST_NAME = r"((?:[A-Z0-9][\w'&.!]*[ -]){1,5}(?:Film |Movie )?Festival)\b"
FEST_IN_BLURB = re.compile(FEST_NAME + r"(?: is| presents| returns| brings| will| celebrates|'s)|part of (?:the )?" + FEST_NAME)

# Where a blurb says who's coming: the sentence that mentions a Q&A, an intro or a guest by name.
GUEST_CUE = re.compile(r"q&a|in person|in attendance|conversation (with|moderated)|special guests?|"
                       r"(thrilled|electrified|excited|honored|delighted) to welcome|introduc(ed|tion) (by|from)|"
                       r"\bintro (by|from|with)|panel|appearance by|discussion with|moderated by", re.I)
PERSON_NAME = re.compile(r"\b[A-Z][a-z]+(?:[- ][A-Z][a-z'’]+)+\b")

# Genre names differ by theater; these collapse them onto TMDB's.
GENRE_NAMES = {"science fiction": "Sci-Fi", "sci-fi": "Sci-Fi", "biopic": "Biography", "biography": "Biography",
               "detective": "Crime", "historical": "History", "war movie": "War", "psychological thriller": "Thriller",
               "comedy drama": "Comedy", "musical": "Music", "opera": "Music", "ballet": "Music", "tv movie": None}

# Each theater's area (for the theater menu and the order venues appear in) and rough coordinates (for
# "Near me"). Areas run west to east, then the outliers.
AREAS = ["Westside", "Hollywood & Mid-City", "Eastside", "Downtown", "Pasadena", "South Bay"]
GEO = {
    "aero": ("Westside", 34.0406, -118.4960), "laemmle-royal": ("Westside", 34.0453, -118.4485),
    "nuart": ("Westside", 34.0436, -118.4440), "landmark-westwood": ("Westside", 34.0627, -118.4475),
    "lumiere-music-hall": ("Westside", 34.0667, -118.3920),
    "newbev": ("Hollywood & Mid-City", 34.0763, -118.3446), "braindead": ("Hollywood & Mid-City", 34.0821, -118.3614),
    "landmark-sunset": ("Hollywood & Mid-City", 34.0981, -118.3647), "egyptian": ("Hollywood & Mid-City", 34.1016, -118.3368),
    "losfeliz": ("Eastside", 34.1028, -118.2917), "vista": ("Eastside", 34.0977, -118.2873),
    "prs": ("Eastside", 34.1102, -118.2774), "whammy": ("Eastside", 34.0796, -118.2604),
    "arts2220": ("Eastside", 34.0688, -118.2700), "vidiots": ("Eastside", 34.1330, -118.2108),
    "alamo-dtla": ("Downtown", 34.0480, -118.2590), "now-instant": ("Downtown", 34.0661, -118.2387),
    "landmark-pasadena": ("Pasadena", 34.1458, -118.1366), "gardena": ("South Bay", 33.8960, -118.3266),
    "academy-museum": ("Hollywood & Mid-City", 34.0637, -118.3609), "usc": ("Downtown", 34.0219, -118.2856),
    "hammer": ("Westside", 34.0597, -118.4434), "finearts": ("Westside", 34.0664, -118.3787),
    "alex": ("Eastside", 34.1488, -118.2551), "laemmle-glendale": ("Eastside", 34.1478, -118.2563),
    "laemmle-monica": ("Westside", 34.0167, -118.4960), "laemmle-noho": ("Valley", 34.1673, -118.3762),
    "laemmle-town": ("Valley", 34.1597, -118.5048), "laemmle-newhall": ("Valley", 34.3796, -118.5318),
    "veggiecloud": ("Eastside", 34.1077, -118.2009), "cinemasaloon": ("Hollywood & Mid-City", 34.0331, -118.3602),
}
CITIES = {"Santa Monica", "Beverly Hills", "West Hollywood", "Pasadena", "Gardena"}  # neighborhoods that are their own city


def area(t):
    return GEO.get(t["id"], ("Elsewhere",))[0]


def theater_order(theaters):
    """Theaters grouped by area, then by name, so neighbors sit together."""
    rank = {a: i for i, a in enumerate(AREAS)}
    return sorted(theaters, key=lambda t: (rank.get(area(t), len(AREAS)), t["name"].lower().removeprefix("the ")))


def festival_name(screening):
    m = re.search(FEST_NAME, screening["title"]) or re.match(r"([A-Z]{2,}I?FF)\b", screening["title"])
    if m:
        name = m.group(1)
    else:
        b = FEST_IN_BLURB.search(screening.get("blurb") or "")
        name = b and (b.group(1) or b.group(2))
    if not name:
        return None
    name = re.sub(r"^(\d{4} |The |A |An )+", "", name.strip())
    return name if len(name.split()) >= 2 or name.endswith("FF") else None


def guest_line(screening):
    """The sentence naming who'll be there ("Q&A with writer-director James Gray"), trimmed to fit a card."""
    title = screening["title"]
    parts = re.split(r"(?<=[.!?])\s+|\s+/\s+|\n+", screening.get("blurb") or "")
    cued = [p.strip() for p in parts if GUEST_CUE.search(p) and p.strip().lower() not in title.lower()]
    if not cued:
        return None
    line = next((p for p in cued if PERSON_NAME.search(p)), cued[0])
    line = re.sub(r"^(\d{1,2}/\d{1,2}\s*[-–]\s*|w/\s*)", "", line)
    line = re.sub(r"\s+", " ", line).strip(" ,;")
    if len(line) > 170:
        line = line[:170].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return line


def genres(screening):
    out = []
    for g in (screening.get("tmdb") or {}).get("genres") or screening["genres"]:
        name = GENRE_NAMES.get(g.lower(), g.title() if g.islower() else g)
        if name and name not in out:
            out.append(name)
    return out


def short_id(*parts):
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]


def event_label(label):
    """A theater's own event label (Alamo's), cleaned up for use as a tag."""
    label = (label or "").strip()
    if label.startswith("+"):
        return "Double feature"  # "+ SECOND FILM" marks the second half of a double bill
    if not label or label.lower() == "special event" or re.fullmatch(r"[A-Z][a-z]+ \d{4}", label):
        return "Special event"  # e.g. "November 2026", a series month rather than a description
    return label


def tag(screening):
    text = f'{screening["title"]} {screening.get("blurb") or ""}'
    events = [name for name, pat in EVENT_TAGS if re.search(pat, text, re.I)]
    screening["festival"] = festival_name(screening)
    if screening["festival"] or re.match(r"cybercon", screening["title"], re.I):
        events.insert(0, "Festival")
    if "Recorded Q&A" in events and "Guests in person" in events:
        events.remove("Guests in person")  # "Pre-Recorded Q&A" also matches the in-person pattern
    if len(events) > 1 and "Special screening" in events:
        events.remove("Special screening")  # the generic tag only when nothing more specific applies
    if screening["special_event"] and not events:
        events.append(event_label(screening.get("event_label")))
    screening["event_tags"] = events
    screening["format_tags"] = [name for name, pat in FORMAT_TAGS if re.search(pat, text, re.I)]
    screening["is_special"] = bool(events)
    screening["guests"] = guest_line(screening) if "Guests in person" in events else None
    screening["genre_list"] = genres(screening)
    screening["id"] = short_id(screening["theater"], screening["title"], screening["start"])


# ---------- small helpers ----------

def fmt_time(dt):
    return dt.strftime("%-I:%M%p").replace(":00", "").lower()


def day_label(day, today):
    if day == today:
        return "Today"
    if day == today + timedelta(days=1):
        return "Tomorrow"
    return day.strftime("%A")


def link(url, text):
    return f'<a href="{escape(url)}" target="_blank" rel="noopener">{text}</a>' if url else text


def times_html(times):
    return "".join(
        (f'<a class="time sold-out" title="Sold out" ' if s["sold_out"] else '<a class="time" ')
        + f'href="{escape(s["ticket_url"])}" target="_blank" rel="noopener">{fmt_time(start)}</a>'
        for start, s in times)


def tags_html(film, links=True):
    """The tag row. links=False inside something that is already a link (a link can't hold another)."""
    tags = [f'<a class="tag" href="/festivals/{slug(film["festival"])}/">{t}</a>'
            if t == "Festival" and film.get("festival") and links else f'<span class="tag">{t}</span>'
            for t in film["event_tags"]]
    tags += [f'<span class="tag format">{t}</span>' for t in film["format_tags"]]
    return f'<span class="tags">{"".join(tags)}</span>' if tags else ""


def meta_html(film):
    info = film.get("tmdb") or {}
    parts = [film["year"] or info.get("year"), escape(film["director"]) if film["director"] else None,
             f'{film["runtime"]} min' if film["runtime"] else None,
             " / ".join(film["genre_list"][:2]) or None,
             f'<a class="rating" href="{info["url"]}" target="_blank" rel="noopener" title="TMDB user score">'
             f'★ {info["rating"]}</a>' if info.get("rating") else None]
    parts = " · ".join(p for p in parts if p)
    return f'<p class="meta">{parts}</p>' if parts else ""


def guests_html(film):
    return f'<p class="guests">{escape(film["guests"])}</p>' if film.get("guests") else ""


def poster_html(film, size="small"):
    # TMDB's poster when the film matched; otherwise the image the theater publishes with its listing.
    src = (film.get("tmdb") or {}).get("poster") or film.get("image")
    if not src:
        return ""
    # A poster that fails to load is removed by COMMON_SCRIPT, so the row falls back to its no-poster layout.
    return (f'<img class="poster {size}" src="{escape(src)}" alt="" loading="lazy" decoding="async" '
            f'referrerpolicy="no-referrer">')


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def event_id(f):
    """One film at one theater on one day: the unit people share."""
    return short_id(f["theater"], f["title"], f["times"][0][0].date().isoformat())


def share_title(f, tmap):
    when = f["times"][0][0]
    return f'{f["title"]} at {tmap[f["theater"]]["name"]}, {when.strftime("%a %b %-d")}'


def actions_html(f, tmap):
    """Trailer, add to calendar and share, under each film."""
    acts = []
    trailer = (f.get("tmdb") or {}).get("trailer")
    if trailer:
        acts.append(f'<a class="act" href="{escape(trailer)}" target="_blank" rel="noopener">Trailer</a>')
    if len(f["times"]) == 1:
        acts.append(f'<a class="act" href="/cal/s/{f["times"][0][1]["id"]}.ics">Add to calendar</a>')
    else:
        items = "".join(f'<a href="/cal/s/{s["id"]}.ics">{start.strftime("%a %b %-d")}, {fmt_time(start)}</a>'
                        for start, s in f["times"])
        acts.append(f'<details class="act-menu"><summary class="act">Add to calendar</summary>'
                    f'<div class="menu">{items}</div></details>')
    acts.append(f'<button class="act share" type="button" data-url="{SITE_URL}/e/{event_id(f)}/" '
                f'data-title="{escape(share_title(f, tmap))}">Share</button>')
    return f'<div class="actions">{"".join(acts)}</div>'


LOGO = ROOT / "logo" / "goodtimes.svg"


ICON = ROOT / "logo" / "goodtimes-icon.svg"


def favicon_uri():
    """The tab icon as a data URI, for share.html (which has no neighboring files to load it from)."""
    if not ICON.exists():
        return ""
    svg = re.sub(r"<!--.*?-->", "", ICON.read_text(), flags=re.S)
    return "data:image/svg+xml," + urllib.parse.quote(" ".join(svg.split()))


def logo_html():
    """The wordmark, inlined so it ships inside each page (share.html has no neighbors to load it from)."""
    if not LOGO.exists():
        return f'<span class="logo-text">{NAME}</span>'
    svg = LOGO.read_text()
    svg = re.sub(r'<rect [^>]*fill="#FFFFFF"\s*/>', "", svg)   # drop the white backdrop
    return re.sub(r"<svg ", '<svg class="logo-svg" focusable="false" ', svg, count=1)


def json_ld(data):
    """A schema.org block. Escapes "</" so a title can't close the script tag."""
    return ('<script type="application/ld+json">'
            + json.dumps({"@context": "https://schema.org", **data}, ensure_ascii=False, separators=(",", ":"))
            .replace("</", "<\\/")
            + "</script>")


def site_graph():
    """Who publishes the site, for the homepage."""
    org, site = f"{SITE_URL}/#organization", f"{SITE_URL}/#website"
    return {"@graph": [
        {"@type": "Organization", "@id": org, "name": SITE_NAME, "alternateName": NAME, "url": f"{SITE_URL}/",
         "logo": {"@type": "ImageObject", "url": f"{SITE_URL}/icon-512.png", "width": 512, "height": 512},
         **({"sameAs": SAME_AS} if SAME_AS else {})},
        {"@type": "WebSite", "@id": site, "name": SITE_NAME, "alternateName": NAME, "url": f"{SITE_URL}/",
         "description": DEFAULT_DESCRIPTION, "inLanguage": "en-US", "publisher": {"@id": org}},
    ]}


SAME_AS = []  # the site's own profiles (Instagram, Letterboxd, Bluesky...), so search engines tie them together
DEFAULT_DESCRIPTION = "Repertory, indie and one-night-only film across Los Angeles, gathered daily from each theater's own site."
NAV = (("home", "/", "Today&rsquo;s Showings"), ("weekend", "/this-weekend/", "This Weekend"),
       ("listings", "/listings/", "All Listings"), ("about", "/about/", "About"))
# Every page's footer links to the collection pages, so search engines (and people) can find them from anywhere.
BROWSE = (("/this-weekend/", "This weekend"), ("/special-events/", "Special events"), ("/theaters/", "All theaters"), ("/35mm/", "35mm"), ("/70mm/", "70mm"),
          ("/q-and-a/", "Q&amp;As and guests"), ("/double-features/", "Double features"), ("/picks/", "Weekly picks"), ("/dates/", "By date"))
USES_TMDB = False  # set in main() when any film has TMDB data, which means the footer must credit TMDB


def page(title, description, path, active, body, updated, script="", head="", indexable=True, share=False, image=None):
    """A full HTML page. path is its address on the site ("/", "/listings/"), used for the canonical link.
    image is a link-preview picture (a poster) in place of the site's card."""
    nav = "".join(f'<a href="{href}"{" aria-current=page" if key == active else ""}>{label}</a>'
                  for key, href, label in NAV)
    url = SITE_URL + path
    title, description = escape(title), escape(description)
    if share:  # claude.ai shows this page itself, so it gets the embedded icon and none of the search tags
        meta = f'<link rel="icon" type="image/svg+xml" href="{favicon_uri()}">'
    else:
        robots = '<meta name="robots" content="noindex, nofollow">' if PREVIEW or not indexable else ""
        meta = f"""<meta name="description" content="{description}">
{robots}
{f'<link rel="canonical" href="{url}">' if indexable else ""}
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#FFFFFF">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{url}">
{f'<meta property="og:image" content="{escape(image)}">' if image else f'''<meta property="og:image" content="{SITE_URL}/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{NAME}: {TAGLINE}">'''}
<meta property="og:locale" content="en_US">
<meta name="twitter:card" content="{"summary" if image else "summary_large_image"}">
<link rel="preload" href="/fonts/inter-latin.woff2" as="font" type="font/woff2" crossorigin>
{head}"""
    return f"""<!doctype html>
<html lang="en-US">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<meta name="claude:viewport-fit-sides" content="cover">
{meta}
<style>
{(ROOT / "style.css").read_text()}
</style>
</head>
<body>
<header class="mast"><div class="wrap">
  <div class="brand">
    <a class="logo" href="/">{logo_html()}</a>
    <p class="tagline">{TAGLINE}</p>
  </div>
  <nav class="site-nav">{nav}</nav>
</div></header>
{body}
<footer><div class="wrap">
  <nav class="browse" aria-label="Browse">{"".join(f'<a href="{h}">{label}</a>' for h, label in BROWSE)}{"".join(
      f'<a href="/{area_slug(a)}/">{AREA_TITLES.get(a, a)}</a>' for a in AREAS if a in AREA_PAGES)}</nav>
  <span><b>{NAME}</b> · Every indie and one-off film showings in L.A.</span>
  <span>Updated {updated}. Tickets are sold by each theater.</span>
  {TMDB_CREDIT if USES_TMDB else ""}
</div></footer>
{COMMON_SCRIPT}
{script}
</body>
</html>
"""


# ---------- data shaping ----------

SMALL_WORDS = {"a", "an", "and", "at", "for", "in", "of", "on", "or", "the", "to", "vs", "with"}


def display_title(title):
    """Some theaters write titles in all caps; set those in title case."""
    if not title.isupper():
        return title
    words = title.lower().split(" ")
    return " ".join(w if i and w in SMALL_WORDS else w[:1].upper() + w[1:] for i, w in enumerate(words))


def upcoming(data, now):
    specials_only = {t["id"] for t in data["theaters"] if t.get("specials_only")}
    out = []
    for s in data["screenings"]:
        start = datetime.fromisoformat(s["start"])
        if start < now - timedelta(minutes=30) or s["cancelled"]:
            continue
        s["title"] = display_title(s["title"])
        tag(s)
        if s["theater"] in specials_only and not s["is_special"]:
            continue
        out.append((start, s))
    return out


def by_day(screenings, theaters):
    """day -> theater id -> film title -> {film info, times[]}"""
    days = OrderedDict()
    for start, s in screenings:
        venues = days.setdefault(start.date(), OrderedDict((t["id"], OrderedDict()) for t in theaters))
        venues[s["theater"]].setdefault(s["title"], {**s, "times": []})["times"].append((start, s))
    return days


def special_events(screenings):
    """Special screenings grouped by film and day, in date order."""
    films = OrderedDict()
    for start, s in screenings:
        if s["is_special"]:
            films.setdefault((s["theater"], s["title"], start.date()), {**s, "times": []})["times"].append((start, s))
    return list(films.values())


# ---------- pages ----------

BLURB_CHARS = 220


def clip(text, n):
    """text cut at a word boundary to about n characters, with an ellipsis if anything was cut."""
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0].rstrip(",;:.—–- ") + "…"


def film_row(f, tmap):
    words = [f["title"], f["director"] or "", f.get("guests") or "", f.get("festival") or ""]
    search = escape(" ".join(words + f["event_tags"] + f["format_tags"] + f["genre_list"]).lower())
    # The guest line often is the whole blurb; don't print it twice.
    # Cards show two lines, so a long blurb is cut to about that; the screening's own page (/e/) has all of it.
    blurb = (f'<p class="blurb">{escape(clip(f["blurb"], BLURB_CHARS))}</p>'
             if f.get("blurb") and f["blurb"].strip().rstrip(".!") != (f.get("guests") or "").rstrip(".!") else "")
    poster = poster_html(f)
    return (f'<li class="film{" has-poster" if poster else ""}" id="f-{event_id(f)}" data-special="{int(f["is_special"])}" '
            f'data-search="{search}" data-genres="{escape("|".join(f["genre_list"]))}">{poster}'
            f'<div class="film-body">{tags_html(f)}<h4>{film_link(f)}</h4>'
            f'{meta_html(f)}{guests_html(f)}{blurb}{actions_html(f, tmap)}</div>'
            f'<div class="times">{times_html(f["times"])}</div></li>')


def venue_link(t):
    """A theater's name, linked to its page on this site (or to its own site when it has no page here)."""
    return f'<a href="{theater_path(t)}">{escape(t["name"])}</a>' if has_page(t) else link(t["url"], escape(t["name"]))


def operator_html(t):
    """The company that runs a theater (Landmark, American Cinematheque), as a small line under its name."""
    return f'<p class="venue-op">{escape(t["operator"])}</p>' if t.get("operator") else ""


def day_section(day, venues, tmap, today, heading=True):
    """One day's screenings grouped by theater. Returns (html, screening count, has special event)."""
    blocks, n, special = [], 0, False
    for tid, films in venues.items():
        if not films:
            continue
        t = tmap[tid]
        n += sum(len(f["times"]) for f in films.values())
        special |= any(f["is_special"] for f in films.values())
        geo = GEO.get(tid)
        coords = f' data-lat="{geo[1]}" data-lng="{geo[2]}"' if geo else ""
        blocks.append(
            f'<div class="venue" data-theater="{tid}"{coords}>'
            f'<header class="venue-head"><h3 class="venue-name">{venue_link(t)}</h3>'
            f'{operator_html(t)}'
            f'<p class="venue-meta"><span class="hood">{escape(t["neighborhood"])}</span>'
            f'<span class="dist" hidden></span></p></header>'
            f'<ul>{"".join(film_row(f, tmap) for f in films.values())}</ul></div>')
    head = (f'<div class="day-head"><h2>{day_label(day, today)}<span class="date">{day.strftime("%b %-d")}</span></h2>'
            f'<span class="count">{n} screening{"s" if n != 1 else ""}</span></div>') if heading else ""
    return f'<section class="day" id="d{day.isoformat()}">{head}{"".join(blocks)}</section>', n, special


def more_dates(n):
    return f'<br>+{n} more date{"s" if n > 1 else ""}' if n else ""


# ---------- weekly picks ----------
# Written by hand in picks.md; see the comments at the top of that file. The newest week whose start date has
# come shows for 7 days on the homepage and at /picks/. With no current week, the section is left out.

PICKS = ROOT / "picks.md"
PICK_LINE = re.compile(r"^[-*]\s+(?:\*\*(.+?)\*\*|(.+?))(?:\s+@\s+(.+?))?\s+[—–]\s+(.+)$")
WEEK_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%Y-%m-%d", "%B %d", "%b %d")


def parse_week(text, today):
    text = re.sub(r"^week of\s+", "", text.strip(), flags=re.I)
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text).replace(".", "")
    for fmt in WEEK_FORMATS:
        try:
            day = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if "%Y" not in fmt:  # no year written: the one that puts the date nearest today
            day = min((day.replace(year=today.year + d) for d in (-1, 0, 1)), key=lambda x: abs((x - today).days))
        return day
    return None


def read_picks(today):
    """The current week from picks.md: {start, intro, picks: [{title, at, why}]}, or None."""
    if not PICKS.exists():
        return None
    text = re.sub(r"<!--.*?-->", "", PICKS.read_text(), flags=re.S)
    weeks, week = [], None
    for line in (x.strip() for x in text.splitlines()):
        if line.startswith("## "):
            start = parse_week(line[3:], today)
            if not start:
                print(f"picks.md: couldn't read the date in {line!r}; skipping that week", file=sys.stderr)
            week = {"start": start, "intro": [], "picks": []} if start else None
            weeks += [week] if week else []
        elif not line or week is None or line.startswith("#"):
            continue
        elif PICK_LINE.match(line):
            m = PICK_LINE.match(line)
            week["picks"].append({"title": (m[1] or m[2]).strip(), "at": m[3], "why": m[4].strip()})
        elif week["picks"]:
            week["picks"][-1]["why"] += " " + line  # a reason that runs onto the next line
        else:
            week["intro"].append(line)
    live = [w for w in weeks if w["picks"] and w["start"] <= today < w["start"] + timedelta(days=7)]
    return max(live, key=lambda w: w["start"]) if live else None


def pick_showings(pick, films, tmap, end):
    """This week's screenings of a pick: exact title matches first, then titles that contain it."""
    want, at = tmdb.norm(pick["title"]), tmdb.norm(pick["at"] or "")
    films = [f for f in films if f["times"][0][0].date() < end
             and (not at or at in tmdb.norm(tmap[f["theater"]]["name"]))]
    names = lambda f: {tmdb.norm(tmdb.core_title(f["title"])), tmdb.norm((f.get("tmdb") or {}).get("title"))}
    exact = [f for f in films if want in names(f)]
    return exact or [f for f in films if len(want) >= 4 and want in tmdb.norm(f["title"])]


def prose(text):
    """Escaped text, with *asterisks* for italic film titles."""
    return re.sub(r"\*(.+?)\*", r"<i>\1</i>", escape(text))


def render_picks(week, days, tmap, today, home=True):
    films = [f for venues in days.values() for fs in venues.values() for f in fs.values()]
    end = week["start"] + timedelta(days=7)
    items = []
    for p in week["picks"]:
        shows = sorted(pick_showings(p, films, tmap, end), key=lambda f: f["times"][0][0])
        poster = poster_html(shows[0]) if shows else ""
        title = escape(display_title(p["title"]))
        title = f'<a href="/e/{event_id(shows[0])}/">{title}</a>' if shows else title
        when = "".join(
            f'<li><a href="/e/{event_id(f)}/">{day_label(f["times"][0][0].date(), today)} '
            f'{f["times"][0][0].strftime("%b %-d")}</a> · {escape(tmap[f["theater"]]["name"])} · '
            f'{", ".join(fmt_time(t) for t, _ in f["times"])}</li>' for f in shows[:4])
        more = f'<li class="muted">+{len(shows) - 4} more</li>' if len(shows) > 4 else ""
        when = (f'<ul class="pick-when">{when}{more}</ul>' if shows
                else '<p class="pick-when muted">No showings left this week.</p>')
        items.append(f'<li class="pick{" has-poster" if poster else ""}">{poster}<div><h3>{title}</h3>'
                     f'<p class="why">{prose(p["why"])}</p>{when}</div></li>')
    intro = "".join(f'<p class="pick-intro">{prose(x)}</p>' for x in week["intro"])
    label = f'Week of {week["start"].strftime("%b %-d")}'
    foot = '<p class="upcoming-foot"><a class="more" href="/picks/">This week&rsquo;s picks, to share →</a></p>' if home else ""
    heading = (f'<div class="day-head"><h2>Worth leaving the house for</h2><span class="count">{label}</span></div>'
               if home else "")
    return f'<section class="picks">{heading}{intro}<ol class="pick-list">{"".join(items)}</ol>{foot}</section>'


def render_picks_page(week, days, tmap, today):
    body = (render_picks(week, days, tmap, today, home=False) if week
            else '<p class="note">No picks this week yet. <a class="more" href="/special-events/">See every special event →</a></p>')
    label = f'Week of {week["start"].strftime("%B %-d")}' if week else "This week"
    return f"""
<main><div class="wrap">
  <header class="page-head">
    <p class="eyebrow">{label}</p>
    <h1>Worth leaving the house for</h1>
  </header>
  {body}
</div></main>"""


def render_home(data, screenings, now):
    today = now.date()
    tmap = {t["id"]: t for t in data["theaters"]}
    days = by_day(screenings, theater_order(data["theaters"]))
    week = read_picks(today)
    picks_html = render_picks(week, days, tmap, today) if week else ""

    if today in days:
        # With picks between the page title and today's list, the list needs its own "Today" heading.
        today_html, n, _ = day_section(today, days[today], tmap, today, heading=bool(week))
    else:
        n, nxt = 0, next(iter(days), None)
        today_html = '<p class="note">Nothing else on screen today.' + (
            f' Next up: {day_label(nxt, today)}, {nxt.strftime("%b %-d")}. '
            f'<a class="more" href="/listings/">See listings →</a>' if nxt else "") + '</p>'

    # One row per film: its next special showing after today, plus how many other dates it has.
    films = OrderedDict()
    for ev in special_events(screenings):
        if ev["times"][0][0].date() != today:
            films.setdefault((ev["theater"], ev["title"]), []).append(ev)
    events = [(evs[0], len(evs) - 1) for evs in films.values()]
    rows = "".join(
        # Each event opens its own page on the theater's site (ticket page when there's no event page).
        f'<li><a href="{escape(ev["film_url"] or ev["ticket_url"])}" target="_blank" rel="noopener">'
        f'<span class="when">{ev["times"][0][0].strftime("%a %b %-d")}</span>'
        f'<div>{tags_html(ev, links=False)}<h3>{escape(ev["title"])}</h3></div>'
        f'<span class="where">{escape(tmap[ev["theater"]]["name"])}'
        f'{more_dates(more)}{"<br><span class=sold-note>Sold out</span>" if all(x["sold_out"] for _, x in ev["times"]) else ""}'
        f'</span></a></li>'
        for ev, more in events[:10])

    venues = sum(1 for v in days.get(today, {}).values() if v)
    return f"""
<main><div class="wrap">
  <header class="page-head">
    <p class="eyebrow">{today.strftime("%A, %B %-d")} · {n} screening{"s" if n != 1 else ""} at {venues} theater{"s" if venues != 1 else ""}</p>
    <h1>Showing today in Los Angeles</h1>
    <form class="home-search" action="/listings/" role="search">
      <input class="search" type="search" name="q" placeholder="Search every listing: films, directors, guests, 35mm…" aria-label="Search every listing">
      <button class="chip" type="submit">Search</button>
    </form>
  </header>
  {picks_html}
  {today_html}
  <section class="upcoming">
    <div class="day-head"><h2>Upcoming special events</h2></div>
    <ul class="upcoming-list">{rows or '<li class="note">No special events posted right now.</li>'}</ul>
    <p class="upcoming-foot"><a class="more" href="/special-events/">See every special event →</a></p>
  </section>
</div></main>"""


def render_listings(data, screenings, now):
    today = now.date()
    theaters = theater_order(data["theaters"])
    tmap = {t["id"]: t for t in theaters}

    screenings = [x for x in screenings if x[0].date() < today + timedelta(days=LISTINGS_DAYS)]
    sections, nav = [], []
    for day, venues in by_day(screenings, theaters).items():
        html, _, special = day_section(day, venues, tmap, today)
        sections.append(html)
        nav.append(f'<a href="#d{day.isoformat()}"{" class=has-special" if special else ""}>'
                   f'<span>{day.strftime("%a")}</span>{day.strftime("%-d")}</a>')

    listed = {s["theater"] for _, s in screenings}
    groups = OrderedDict()
    for t in theaters:
        if t["id"] in listed:
            groups.setdefault(area(t), []).append(t)
    options = "".join(
        f'<div class="menu-group"><button type="button" class="group-head" data-area="{escape(a)}">{escape(a)}</button>'
        + "".join(
            f'<label class="option"><input type="checkbox" value="{t["id"]}" data-area="{escape(a)}">'
            f'<span>{escape(t["name"])}</span>'
            f'<span class="hood">{escape(" · ".join(x for x in (t.get("operator"), t["neighborhood"]) if x))}</span></label>'
            for t in ts) + "</div>"
        for a, ts in groups.items())
    counts = OrderedDict()
    for _, s in screenings:
        for g in s["genre_list"]:
            counts[g] = counts.get(g, 0) + 1
    genre_options = "".join(
        f'<label class="option"><input type="checkbox" value="{escape(g)}"><span>{escape(g)}</span></label>'
        for g in sorted(g for g, n in counts.items() if n >= 3))
    return f"""
<h1 class="visually-hidden">Indie and repertory film listings in Los Angeles</h1>
<nav class="controls" aria-label="Filter listings"><div class="wrap">
  <div class="control-row">
    <details class="picker" id="theaters" data-all="All theaters" data-unit="theaters">
      <summary class="select">All theaters</summary>
      <div class="menu" role="group" aria-label="Theaters">
        {options}
        <div class="menu-foot"><button type="button" class="link-button clear">Show all theaters</button></div>
      </div>
    </details>
    <details class="picker" id="genres" data-all="All genres" data-unit="genres">
      <summary class="select">All genres</summary>
      <div class="menu" role="group" aria-label="Genres">
        {genre_options}
        <div class="menu-foot"><button type="button" class="link-button clear">Show all genres</button></div>
      </div>
    </details>
    <button class="chip" id="special" type="button" aria-pressed="false">Special events</button>
    <button class="chip" id="near" type="button" aria-pressed="false">Near me</button>
    <input class="search" id="search" type="search" placeholder="Search films, directors, guests, 35mm…" aria-label="Search listings">
  </div>
  <p class="near-status" id="near-status" hidden></p>
  <div class="days">{"".join(nav)}<a class="later" href="/dates/"><span>Later</span>→</a></div>
</div></nav>
<main class="listings"><div class="wrap">
  {"".join(sections) or '<p class="empty">No upcoming screenings found.</p>'}
  <p class="empty" id="no-results" hidden>Nothing matches in the next week. Try another search or filter, or
    look through <a href="/dates/">later dates</a>.</p>
  <p class="upcoming-foot"><a class="more" href="/dates/">Later dates →</a></p>
  <button class="to-top" id="to-top" type="button" hidden>↑ Back to top</button>
</div></main>"""


LISTINGS_SCRIPT = """<script>
  const pickers = ["theaters", "genres"].map(id => {
    const el = document.getElementById(id);
    return { el, boxes: [...el.querySelectorAll("input[type=checkbox]")] };
  });
  const [theaterPicker, genrePicker] = pickers;
  const special = document.getElementById("special");
  const near = document.getElementById("near");
  const search = document.getElementById("search");
  const pressed = b => b.getAttribute("aria-pressed") === "true";
  const press = (b, on) => { b.setAttribute("aria-pressed", on ? "true" : "false"); b.classList.toggle("on", on); };

  function label(p) {
    const picked = p.boxes.filter(b => b.checked);
    p.el.querySelector("summary").textContent =
      picked.length === 0 ? p.el.dataset.all
      : picked.length === 1 ? picked[0].nextElementSibling.textContent
      : `${picked.length} ${p.el.dataset.unit}`;
    p.el.classList.toggle("on", picked.length > 0);
    return new Set(picked.map(b => b.value));
  }

  function apply() {
    const q = search.value.trim().toLowerCase();
    const chosen = label(theaterPicker), genres = label(genrePicker);
    const onlySpecial = pressed(special);
    let any = false;
    document.querySelectorAll(".day").forEach(day => {
      let dayVisible = false;
      day.querySelectorAll(".venue").forEach(v => {
        let venueVisible = false;
        v.querySelectorAll(".film").forEach(f => {
          const ok = (chosen.size === 0 || chosen.has(v.dataset.theater))
            && (genres.size === 0 || f.dataset.genres.split("|").some(g => genres.has(g)))
            && (!onlySpecial || f.dataset.special === "1")
            && (!q || f.dataset.search.includes(q));
          f.hidden = !ok;
          venueVisible ||= ok;
        });
        v.hidden = !venueVisible;
        dayVisible ||= venueVisible;
      });
      day.hidden = !dayVisible;
      const n = [...day.querySelectorAll(".film")].filter(f => !f.hidden && !f.closest(".venue").hidden)
        .reduce((sum, f) => sum + f.querySelectorAll(".time").length, 0);
      const count = day.querySelector(".count");
      if (count) count.textContent = `${n} screening${n === 1 ? "" : "s"}`;
      const link = document.querySelector(`.days a[href="#${day.id}"]`);
      if (link) link.hidden = !dayVisible;
      any ||= dayVisible;
    });
    document.getElementById("no-results").hidden = any;
  }

  for (const p of pickers) {
    p.boxes.forEach(b => b.addEventListener("change", apply));
    p.el.querySelector(".clear").addEventListener("click", () => { p.boxes.forEach(b => { b.checked = false; }); apply(); });
  }
  // An area heading in the theater menu picks every theater in that area (or clears them if all are picked).
  theaterPicker.el.querySelectorAll(".group-head").forEach(h => h.addEventListener("click", () => {
    const inArea = theaterPicker.boxes.filter(b => b.dataset.area === h.dataset.area);
    const all = inArea.every(b => b.checked);
    theaterPicker.boxes.forEach(b => { if (!all) b.checked = inArea.includes(b); else if (inArea.includes(b)) b.checked = false; });
    apply();
  }));
  // Close a menu on an outside click or Escape.
  document.addEventListener("click", e => pickers.forEach(p => { if (!p.el.contains(e.target)) p.el.open = false; }));
  document.addEventListener("keydown", e => { if (e.key === "Escape") pickers.forEach(p => { p.el.open = false; }); });
  special.addEventListener("click", () => { press(special, !pressed(special)); apply(); });
  search.addEventListener("input", apply);

  // Near me: sorts each day's theaters by distance. Asks for location only when tapped.
  const nearStatus = document.getElementById("near-status");
  const venues = [...document.querySelectorAll(".venue")];
  venues.forEach((v, i) => { v.dataset.order = i; });
  function miles(lat1, lng1, lat2, lng2) {
    const r = Math.PI / 180, a = Math.sin((lat2 - lat1) * r / 2) ** 2
      + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin((lng2 - lng1) * r / 2) ** 2;
    return 3959 * 2 * Math.asin(Math.sqrt(a));
  }
  function sortVenues(key) {
    document.querySelectorAll(".day").forEach(day => {
      [...day.querySelectorAll(".venue")].sort((a, b) => key(a) - key(b)).forEach(v => day.appendChild(v));
    });
  }
  near.addEventListener("click", () => {
    if (pressed(near)) {
      press(near, false);
      venues.forEach(v => { v.querySelector(".dist").hidden = true; });
      sortVenues(v => +v.dataset.order);
      nearStatus.hidden = true;
      return;
    }
    if (!navigator.geolocation) { nearStatus.hidden = false; nearStatus.textContent = "This browser can't share your location."; return; }
    nearStatus.hidden = false;
    nearStatus.textContent = "Finding you…";
    navigator.geolocation.getCurrentPosition(pos => {
      const { latitude, longitude } = pos.coords;
      venues.forEach(v => {
        const d = v.dataset.lat ? miles(latitude, longitude, +v.dataset.lat, +v.dataset.lng) : Infinity;
        v.dataset.dist = d;
        const out = v.querySelector(".dist");
        out.hidden = d === Infinity;
        out.textContent = d < 10 ? `${d.toFixed(1)} mi` : `${Math.round(d)} mi`;
      });
      sortVenues(v => +v.dataset.dist);
      press(near, true);
      nearStatus.hidden = true;
    }, () => {
      nearStatus.textContent = "Couldn't get your location. Check that this site is allowed to use it.";
    }, { maximumAge: 600000, timeout: 15000 });
  });

  try { localStorage.removeItem("watchlist"); } catch {}  // from the old Letterboxd watchlist filter

  // Back to top: appears once you've scrolled a couple of screens down.
  const toTop = document.getElementById("to-top");
  const onScroll = () => { toTop.hidden = scrollY < innerHeight * 1.5; };
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();
  toTop.addEventListener("click", () => {
    const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;
    scrollTo({ top: 0, behavior: smooth ? "smooth" : "instant" });
  });

  // /listings/?q=… searches (the homepage search box sends people here). /listings/#special turns the
  // special events filter on; /listings/#<theater id> picks a theater; /listings/#f-<id> is one film.
  const q = new URLSearchParams(location.search).get("q");
  if (q) search.value = q;
  function fromHash() {
    const hash = location.hash.slice(1);
    if (hash === "special") press(special, true);
    else if (theaterPicker.boxes.some(b => b.value === hash)) theaterPicker.boxes.forEach(b => { b.checked = b.value === hash; });
    apply();
  }
  window.addEventListener("hashchange", fromHash);
  fromHash();
</script>"""


TMDB_CREDIT = ('<span>Posters, ratings and trailers from <a href="https://www.themoviedb.org/" target="_blank" '
               'rel="noopener">TMDB</a>. This product uses the TMDB API but is not endorsed or certified by TMDB.</span>')

# Share buttons and the small "Add to calendar" menus, on every page.
COMMON_SCRIPT = """<script>
  // A poster that fails to load (errors don't bubble, so this listens on the way down).
  document.addEventListener("error", e => {
    const img = e.target;
    if (img.tagName === "IMG" && img.classList.contains("poster")) {
      img.closest(".has-poster")?.classList.remove("has-poster");
      img.remove();
    }
  }, true);
  function flash(button, text) {
    const old = button.textContent;
    button.textContent = text;
    setTimeout(() => { button.textContent = old; }, 2000);
  }
  document.addEventListener("click", async e => {
    document.querySelectorAll(".act-menu[open]").forEach(m => { if (!m.contains(e.target)) m.open = false; });
    const b = e.target.closest(".share");
    if (!b) return;
    // The phone's share sheet where there is one; otherwise copy the link.
    if (navigator.share) {
      try { await navigator.share({ title: b.dataset.title, url: b.dataset.url }); } catch {}
      return;
    }
    try { await navigator.clipboard.writeText(b.dataset.url); flash(b, "Link copied"); }
    catch { prompt("Copy this link:", b.dataset.url); }
  });
</script>"""

# Who to write to about a missing theater or a wrong listing, shown on the About page. Leave empty to hide.
CONTACT_EMAIL = ""


# ---------- calendars ----------

def ics_text(value):
    return (value or "").replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,").replace("\n", "\\n")


def ics_fold(line):
    """Calendar lines wrap at 75 bytes, continued with a leading space, without splitting a character."""
    out, cur = [], b""
    for ch in line:
        enc = ch.encode()
        if len(cur) + len(enc) > (75 if not out else 74):
            out.append(cur.decode())
            cur = b""
        cur += enc
    out.append(cur.decode())
    return "\r\n ".join(out)


def ics_utc(dt):
    return dt.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")


def location(t):
    if t["address"].lower().startswith("various"):
        return t["name"]
    city = t["neighborhood"] if t["neighborhood"] in CITIES else "Los Angeles"
    return f'{t["name"]}, {t["address"]}, {city}, CA'


def vevent(start, s, t, stamp):
    end = start + timedelta(minutes=s["runtime"] or 120)
    desc = "\n\n".join(x for x in (s.get("guests"), f'Tickets: {s["ticket_url"]}',
                                   f"Found on {SITE_NAME}: {SITE_URL}/") if x)
    lines = ["BEGIN:VEVENT", f'UID:{s["id"]}@goodtimes', f"DTSTAMP:{stamp}", f"DTSTART:{ics_utc(start)}",
             f"DTEND:{ics_utc(end)}", f'SUMMARY:{ics_text(s["title"] + (" (sold out)" if s["sold_out"] else ""))}',
             f"LOCATION:{ics_text(location(t))}", f"DESCRIPTION:{ics_text(desc)}", f'URL:{s["ticket_url"]}',
             "END:VEVENT"]
    return lines


def calendar(name, screenings, tmap, stamp, feed=False):
    """An .ics file. A feed (one people subscribe to) also says how often to check for new screenings."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{NAME}//LA listings//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{ics_text(name)}", "X-WR-TIMEZONE:America/Los_Angeles"]
    if feed:
        lines += ["REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    for start, s in screenings:
        lines += vevent(start, s, tmap[s["theater"]], stamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(ics_fold(x) for x in lines) + "\r\n"


def feed_links(path):
    """Subscribe (webcal://, which calendar apps open) and the plain address (for Google Calendar's "From URL")."""
    url = SITE_URL + path
    webcal = re.sub(r"^https?://", "webcal://", url)
    return (f'<a class="more" href="{escape(webcal)}">Subscribe</a> '
            f'<span class="feed-url">{escape(url)}</span>')


# ---------- screening, festival and about pages ----------

def render_event(f, tmap, today):
    """The page a shared link opens: one film at one theater on one day."""
    t = tmap[f["theater"]]
    day = f["times"][0][0].date()
    poster = poster_html(f, "large")
    blurb = f'<p class="blurb full">{escape(f["blurb"])}</p>' if f.get("blurb") else ""
    return f"""
<main><div class="wrap">
  <article class="event{" has-poster" if poster else ""}">
    {poster}
    <div class="event-body">
      <p class="eyebrow">{day_label(day, today)}, {day.strftime("%b %-d")} · {link(t["url"], escape(t["name"]))} · {escape(t["neighborhood"])}</p>
      {tags_html(f)}
      <h1>{link(f["film_url"], escape(f["title"]))}</h1>
      {meta_html(f)}{guests_html(f)}
      <div class="times">{times_html(f["times"])}</div>
      {actions_html(f, tmap)}
      {blurb}
      <p class="event-foot"><a class="more" href="/dates/{day.isoformat()}/">Everything playing {day.strftime("%a %b %-d")} →</a></p>
    </div>
  </article>
</div></main>"""


def render_festival(name, screenings, tmap, today):
    days = by_day(screenings, theater_order(tmap.values()))
    sections = "".join(day_section(day, venues, tmap, today)[0] for day, venues in days.items())
    venues = sorted({tmap[s["theater"]]["name"] for _, s in screenings})
    return f"""
<main><div class="wrap">
  <header class="page-head">
    <p class="eyebrow">Festival · {len(screenings)} screening{"s" if len(screenings) != 1 else ""} at {escape(", ".join(venues))}</p>
    <h1>{escape(name)}</h1>
  </header>
  {sections}
  <p class="upcoming-foot"><a class="more" href="/special-events/">Every special event →</a></p>
</div></main>"""


# ---------- theater and collection pages ----------
# Pages for what people search for: one theater's schedule, this weekend, 35mm, Q&As, an area of town. Every
# screening on them is also described as a schema.org ScreeningEvent, so search engines and AI answer engines
# can read the film, time, place and ticket link as facts instead of guessing from the text.

THEATER_DAYS = 30     # how far ahead a theater's page lists
LISTINGS_DAYS = 7     # /listings/ covers this many days; every date also has its own page under /dates/
INDEX_DAYS = 14       # date pages this far ahead are in search; later ones (often a single screening) aren't
AREA_DAYS = 7
COLLECTION_DAYS = 60
# A sentence or two about a theater in your own words, shown at the top of its page. Keyed by theater id.
THEATER_NOTES = {}


def has_page(t):
    """Theaters with an address of their own get a page (not a series that screens at other venues)."""
    return bool(t.get("address")) and not t["address"].lower().startswith("various")


def theater_path(t):
    return f"/theaters/{slug(t['name'])}/"


def city(t):
    return t["neighborhood"] if t["neighborhood"] in CITIES else "Los Angeles"


def postal_address(t):
    return {"@type": "PostalAddress", "streetAddress": t["address"], "addressLocality": city(t),
            "addressRegion": "CA", "addressCountry": "US"}


def theater_ld(t):
    geo = GEO.get(t["id"])
    return {"@type": "MovieTheater", "@id": SITE_URL + theater_path(t) + "#theater", "name": t["name"],
            "url": SITE_URL + theater_path(t), "sameAs": [t["url"]], "address": postal_address(t),
            **({"geo": {"@type": "GeoCoordinates", "latitude": geo[1], "longitude": geo[2]}} if geo else {}),
            **({"parentOrganization": {"@type": "Organization", "name": t["operator"]}} if t.get("operator") else {})}


def screening_ld(start, s, t, path):
    """One showing as a ScreeningEvent. path is the page it's listed on; the event links to its row there."""
    info = s.get("tmdb") or {}
    image = info.get("poster") or s.get("image")
    year = s["year"] or info.get("year")
    movie = {"@type": "Movie", "name": info.get("title") or s["title"],
             **({"dateCreated": str(year)} if year else {}),
             **({"director": {"@type": "Person", "name": s["director"]}} if s["director"] else {}),
             **({"sameAs": info["url"]} if info.get("url") else {})}
    row = short_id(s["theater"], s["title"], start.date().isoformat())  # the film row's id, as in event_id()
    return {
        "@type": "ScreeningEvent", "name": s["title"], "url": f"{SITE_URL}{path}#f-{row}",
        "startDate": start.isoformat(),
        **({"endDate": (start + timedelta(minutes=s["runtime"])).isoformat()} if s["runtime"] else {}),
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": {"@type": "MovieTheater", "@id": SITE_URL + theater_path(t) + "#theater", "name": t["name"],
                     "address": postal_address(t)},
        "organizer": {"@type": "Organization", "name": t["name"], "url": t["url"]},
        "workPresented": movie,
        **({"image": image} if image else {}),
        **({"description": clip(s["blurb"], 160)} if s.get("blurb") else {}),
        **({"videoFormat": s["format_tags"][0]} if s["format_tags"] else {}),
        "offers": {"@type": "Offer", "url": s["ticket_url"],
                   "availability": "https://schema.org/" + ("SoldOut" if s["sold_out"] else "InStock")},
    }


def events_ld(shows, tmap, path):
    return [screening_ld(start, s, tmap[s["theater"]], path) for start, s in shows if has_page(tmap[s["theater"]])]


def breadcrumbs(*crumbs):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": name, "item": SITE_URL + path}
        for i, (name, path) in enumerate((("Home", "/"),) + crumbs, 1)]}


def schedule_html(shows, tmap, today, solo=False):
    """Day-by-day sections. solo: one theater's page, so its name isn't repeated beside every film."""
    days = by_day(shows, theater_order(tmap.values()))
    if not solo:
        return "".join(day_section(day, venues, tmap, today)[0] for day, venues in days.items())
    out = []
    for day, venues in days.items():
        films = [f for fs in venues.values() for f in fs.values()]
        n = sum(len(f["times"]) for f in films)
        out.append(f'<section class="day" id="d{day.isoformat()}"><div class="day-head"><h2>{day_label(day, today)}'
                   f'<span class="date">{day.strftime("%b %-d")}</span></h2>'
                   f'<span class="count">{n} screening{"s" if n != 1 else ""}</span></div>'
                   f'<ul class="solo-list">{"".join(film_row(f, tmap) for f in films)}</ul></section>')
    return "".join(out)


def plural(n, word, many=None):
    return f'{n} {word if n == 1 else many or word + "s"}'


def next_up(shows, tmap, today, at=True):
    """ "Next: Title at Theater, tonight at 7:30pm." The first showing, said the way a person would."""
    start, s = shows[0]
    day = start.date()
    when = ("tonight" if start.hour >= 17 else "today") if day == today else (
        "tomorrow" if day == today + timedelta(days=1) else start.strftime("%A, %B %-d"))
    where = f' at {escape(tmap[s["theater"]]["name"])}' if at else ""
    return f'Next: <i>{escape(s["title"])}</i>{where}, {when} at {fmt_time(start)}.'


def lede(shows, tmap, today, counted, at=True):
    """The page's answer in one or two sentences: how many, where, and what's next."""
    if not shows:
        return ""
    return f'<p class="lede">{counted} {next_up(shows, tmap, today, at)}</p>'


def weekend(today):
    """This Friday to Sunday; on a weekend day, from today to Sunday."""
    wd = today.weekday()
    start = today if wd >= 4 else today + timedelta(days=4 - wd)
    return start, today + timedelta(days=6 - wd) if wd >= 4 else start + timedelta(days=2)


def is_double(s):
    return ("Double feature" in s["event_tags"] or " / " in s["title"] or " + " in s["title"]
            or bool(re.search(r"double (feature|bill)", f'{s["title"]} {s.get("blurb") or ""}', re.I)))


# path, page title, eyebrow, heading, what the count is of (one, many), an evergreen sentence, which screenings
COLLECTIONS = [
    ("special-events", "Special Film Screenings & Events in Los Angeles", "One night only", "Special events in LA",
     ("special event", "special events"), "Q&amp;As, premieres, festivals, live scores, sing-alongs, double features and "
     "other one-off screenings at LA's indie and repertory theaters.", lambda s: s["is_special"]),
    ("35mm", "35mm Film Screenings in Los Angeles", "Shown on film", "35mm screenings in LA", ("screening on 35mm", "screenings on 35mm"),
     "Showings the theater itself lists as a 35mm print, across every LA indie and repertory theater "
     f"{NAME} follows.", lambda s: "35mm" in s["format_tags"]),
    ("70mm", "70mm Film Screenings in Los Angeles", "Shown on film", "70mm screenings in LA", ("screening in 70mm", "screenings in 70mm"),
     "Large-format 70mm prints, which only a few LA projection booths can run.",
     lambda s: "70mm" in s["format_tags"]),
    ("q-and-a", "Film Q&As and Filmmakers in Person in LA", "Guests in person", "Q&As and guests in person in LA",
     ("screening with a guest in person", "screenings with a guest in person"),
     "Screenings where a director, actor or other guest is scheduled to appear, usually for a Q&A or an introduction. "
     "Guests are named when the theater says who's coming; plans change, so check the theater's page before you go.",
     lambda s: "Guests in person" in s["event_tags"]),
    ("double-features", "Double Features in Los Angeles", "Two films, one bill", "Double features in LA",
     ("double bill", "double bills"), "Two films programmed together on one bill at LA's repertory theaters.", is_double),
]
AREA_TITLES = {"Downtown": "Downtown LA", "Valley": "San Fernando Valley"}
AREA_IN = {"Eastside": "on the Eastside", "Westside": "on the Westside", "Valley": "in the Valley"}  # otherwise "in <area>"


def collection_page(heading, eyebrow, shows, tmap, today, counted, about, empty, solo=False, extra=""):
    lead = lede(shows, tmap, today, counted, at=not solo)
    body = schedule_html(shows, tmap, today, solo) or f'<p class="note">{empty}</p>'
    return f"""
<main><div class="wrap">
  <header class="page-head">
    <p class="eyebrow">{eyebrow}</p>
    <h1>{heading}</h1>
  </header>
  <section class="intro">{lead}<p class="about-page">{about}</p>{extra}</section>
  {body}
  <p class="upcoming-foot"><a class="more" href="/listings/">Everything playing in LA →</a></p>
</div></main>"""


def render_theater(t, shows, tmap, today):
    n, fmt = len(shows), sum(1 for _, s in shows if "35mm" in s["format_tags"] or "70mm" in s["format_tags"])
    special = sum(1 for _, s in shows if s["is_special"])
    extras = [f"{fmt} on film" if fmt else "", plural(special, "special event") if special else ""]
    extras = " and ".join(x for x in extras if x)
    counted = (f'{plural(n, "screening")} at {escape(t["name"])} in the next {THEATER_DAYS} days'
               f'{", including " + extras if extras else ""}.')
    maps = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(location(t))
    facts = (f'<p class="theater-facts">{escape(t["address"])}, {escape(city(t))}, CA · '
             f'<a href="{escape(maps)}" target="_blank" rel="noopener">Map</a> · '
             f'{link(t["url"], "Theater website")} · <a href="/cal/{t["id"]}.ics">Calendar feed</a></p>')
    note = f'<p>{escape(THEATER_NOTES[t["id"]])}</p>' if t["id"] in THEATER_NOTES else ""
    eyebrow = " · ".join(escape(x) for x in (t.get("operator"), t["neighborhood"], area(t)) if x)
    return collection_page(escape(t["name"]), eyebrow, shows, tmap, today, counted,
                           f'Showtimes for {escape(t["name"])}, gathered every morning from the theater&rsquo;s own '
                           f'site. Tickets are sold by the theater.', f'Nothing listed at {escape(t["name"])} in the '
                           f'next {THEATER_DAYS} days. Check the theater&rsquo;s own site for later dates.',
                           solo=True, extra=note + facts)


def render_theater_index(theaters, shows, today):
    week = today + timedelta(days=AREA_DAYS)
    counts = {}
    for start, s in shows:
        if start.date() < week:
            counts[s["theater"]] = counts.get(s["theater"], 0) + 1
    groups = OrderedDict()
    for t in theater_order(theaters):
        if has_page(t):
            groups.setdefault(area(t), []).append(t)
    rows = "".join(
        f'<h2 class="area-head">{area_link(a)}</h2><ul class="theater-list">' + "".join(
            f'<li><a href="{theater_path(t)}">{escape(t["name"])}</a>'
            f'<span class="hood">{escape(" · ".join(x for x in (t.get("operator"), t["neighborhood"]) if x))}</span>'
            f'<span class="count">{plural(counts.get(t["id"], 0), "screening")} this week</span></li>' for t in ts)
        + "</ul>" for a, ts in groups.items())
    return f"""
<main><div class="wrap">
  <header class="page-head">
    <p class="eyebrow">{plural(sum(len(ts) for ts in groups.values()), "theater")}</p>
    <h1>LA&rsquo;s indie and repertory movie theaters</h1>
  </header>
  <section class="intro"><p class="about-page">Every theater {NAME} lists, by area of town, with what each has on
    over the next week. Each page has the full schedule, the address and a calendar feed.</p></section>
  {rows}
</div></main>"""


def area_slug(a):
    return slug(a)


def area_link(a):
    """An area's name, linked to its page when it has one."""
    return f'<a href="/{area_slug(a)}/">{escape(a)}</a>' if a in AREA_PAGES else escape(a)


AREA_PAGES = set()  # areas with two or more theaters; filled in by main()
UNLISTED = set()    # generated pages kept out of the sitemap (dates more than INDEX_DAYS ahead)


def render_dates_index(days, today):
    months = OrderedDict()
    for day, n in days.items():
        months.setdefault(day.strftime("%B %Y"), []).append(
            f'<li><a href="/dates/{day.isoformat()}/">{day_label(day, today)}, {day.strftime("%b %-d")}</a>'
            f'<span class="count">{plural(n, "screening")}</span></li>')
    rows = "".join(f'<h2 class="area-head">{m}</h2><ul class="theater-list">{"".join(items)}</ul>'
                   for m, items in months.items())
    return f"""
<main><div class="wrap">
  <header class="page-head">
    <p class="eyebrow">{plural(len(days), "date")} with screenings</p>
    <h1>Every date</h1>
  </header>
  <section class="intro"><p class="about-page">What&rsquo;s playing at LA&rsquo;s indie and repertory theaters on any
    day theaters have announced so far. <a href="/listings/">The listings</a> cover the next week with filters.</p></section>
  {rows}
</div></main>"""


def collection_pages(data, screenings, tmap, today, updated):
    """{path: html} for the theater, area and collection pages."""
    pages = {}
    soon = lambda days: [x for x in screenings if x[0].date() < today + timedelta(days=days)]
    theaters = [t for t in data["theaters"] if has_page(t)]

    for t in theaters:
        shows = [x for x in soon(THEATER_DAYS) if x[1]["theater"] == t["id"]]
        path = theater_path(t)
        hood = f'{t["neighborhood"]}, {city(t)}' if city(t) != t["neighborhood"] else t["neighborhood"]
        desc = (f'What\'s playing at {t["name"]} ({t["address"]}, {hood}): {plural(len(shows), "upcoming screening")}'
                f', with showtimes and tickets. Updated every morning.')
        graph = [theater_ld(t), breadcrumbs(("Theaters", "/theaters/"), (t["name"], path))] + events_ld(shows, tmap, path)
        pages[path] = page(f'{t["name"]} Showtimes & Schedule | {SITE_NAME}', desc, path, None,
                           render_theater(t, shows, tmap, today), updated, head=json_ld({"@graph": graph}))

    graph = [breadcrumbs(("Theaters", "/theaters/")),
             {"@type": "ItemList", "itemListElement": [
                 {"@type": "ListItem", "position": i, "item": theater_ld(t)} for i, t in enumerate(theater_order(theaters), 1)]}]
    pages["/theaters/"] = page(f"LA Indie & Repertory Movie Theaters | {SITE_NAME}",
                               f"All {len(theaters)} Los Angeles indie and repertory movie theaters {NAME} lists, by "
                               "area, with addresses, schedules and calendar feeds.", "/theaters/", None,
                               render_theater_index(theaters, screenings, today), updated, head=json_ld({"@graph": graph}))

    # This weekend
    fri, sun = weekend(today)
    shows = [x for x in screenings if fri <= x[0].date() <= sun]
    dates = f'{fri.strftime("%b %-d")}–{sun.strftime("%-d") if fri.month == sun.month else sun.strftime("%b %-d")}'
    k = len({s["theater"] for _, s in shows})
    special = sum(1 for _, s in shows if s["is_special"])
    counted = (f'{plural(len(shows), "screening")} at {k} LA indie and repertory theater{"" if k == 1 else "s"} this weekend, '
               f'{fri.strftime("%A, %B %-d")} to {sun.strftime("%A, %B %-d")}'
               f'{", including " + plural(special, "special event") if special else ""}.')
    path = "/this-weekend/"
    pages[path] = page(f"LA Movies This Weekend, {dates}: Indie & Repertory Screenings | {SITE_NAME}",
                       re.sub(r"<[^>]+>", "", counted) + " Times and tickets for every one.", path, "weekend",
                       collection_page(f"This weekend in LA", dates, shows, tmap, today, counted,
                                       "Everything playing Friday through Sunday at the theaters "
                                       f'{NAME} follows. <a href="/q-and-a/">Q&amp;As</a>, '
                                       '<a href="/35mm/">35mm</a> and other special screenings are tagged.',
                                       "Nothing is listed for this weekend yet."),
                       updated, head=json_ld({"@graph": [breadcrumbs(("This weekend", path))] + events_ld(shows, tmap, path)}))

    for key, title, eyebrow, heading, what, about, test in COLLECTIONS:
        shows = [x for x in soon(COLLECTION_DAYS) if test(x[1])]
        k = len({s["theater"] for _, s in shows})
        counted = (f'{plural(len(shows), *what)} coming up at {plural(k, "LA theater")} over the next two months.'
                   if shows else "")
        path = f"/{key}/"
        desc = (f'{plural(len(shows), *what)} at {plural(k, "Los Angeles theater")}, with dates, times and tickets. '
                'Updated every morning.') if shows else f"{about[:150]}"
        pages[path] = page(f"{title} | {SITE_NAME}", desc, path, None,
                           collection_page(heading, eyebrow, shows, tmap, today, counted, about,
                                           f"Nothing is listed right now. New screenings are added every morning."),
                           updated, head=json_ld({"@graph": [breadcrumbs((heading, path))] + events_ld(shows, tmap, path)}))

    # A page per date, and an index of them
    by_date = OrderedDict()
    for x in screenings:
        by_date.setdefault(x[0].date(), []).append(x)
    for day, shows in by_date.items():
        path = f"/dates/{day.isoformat()}/"
        k = len({s["theater"] for _, s in shows})
        nice = day.strftime("%A, %B %-d")
        counted = f'{plural(len(shows), "screening")} at {k} LA indie and repertory theater{"" if k == 1 else "s"} on {nice}.'
        near = day < today + timedelta(days=INDEX_DAYS)
        if not near:
            UNLISTED.add(path)
        pages[path] = page(f"What's Playing in LA on {day.strftime('%A, %b %-d')}: Indie & Repertory Showtimes | {SITE_NAME}",
                           re.sub(r"<[^>]+>", "", counted) + " Times and tickets for every one.", path, None,
                           collection_page(f"Showing in LA on {nice}", day_label(day, today), shows, tmap, today, counted,
                                           f'<a href="/dates/">Every date</a> · <a href="/this-weekend/">This weekend</a>',
                                           "Nothing listed."),
                           updated, indexable=near,
                           head=json_ld({"@graph": [breadcrumbs(("Dates", "/dates/"), (nice, path))] + events_ld(shows, tmap, path)}))
    pages["/dates/"] = page(f"LA Indie & Repertory Screenings by Date | {SITE_NAME}",
                            f"Every date with screenings announced at LA's indie and repertory theaters, "
                            f"{plural(len(by_date), 'day')} ahead.", "/dates/", None,
                            render_dates_index(OrderedDict((d, len(x)) for d, x in by_date.items()), today), updated)

    for a in AREA_PAGES:
        ids = {t["id"] for t in theaters if area(t) == a}
        names = [t["name"] for t in theater_order(theaters) if t["id"] in ids]
        shows = [x for x in soon(AREA_DAYS) if x[1]["theater"] in ids]
        label = AREA_TITLES.get(a, a)
        counted = (f'{plural(len(shows), "screening")} at {plural(len(ids), "theater")} '
                   f'{escape(AREA_IN.get(a, "in " + label))} this week.')
        path = f"/{area_slug(a)}/"
        about = f'Indie and repertory showtimes for the next {AREA_DAYS} days at ' + ", ".join(
            f'<a href="{theater_path(t)}">{escape(t["name"])}</a>' for t in theater_order(theaters) if t["id"] in ids) + "."
        pages[path] = page(f"{label} Movie Theaters: Indie & Repertory Showtimes This Week | {SITE_NAME}",
                           f'{plural(len(shows), "screening")} this week at {", ".join(names)}'[:155], path, None,
                           collection_page(f"Showing in {escape(label)}", "This week", shows, tmap, today, counted,
                                           about, "Nothing listed in this area this week."),
                           updated, head=json_ld({"@graph": [breadcrumbs((label, path))] + events_ld(shows, tmap, path)}))
    return pages


# ---------- film pages ----------
# A page per film (/films/<title>-<year>/) with every upcoming screening across theaters. They're built from the
# archive (archive.py), so a film's page stays up after its run, saying when and where it last screened. Pages of
# films with nothing coming up stay out of search.

FILM_PATHS = {}  # film key -> its page; filled in by main() so film titles everywhere can link to it


def title_key(s):
    return f'title:{tmdb.norm(tmdb.core_title(s["title"]))}:{s["year"] or ""}'


def film_key(s):
    """One film however theaters write its title: its TMDB id when matched, otherwise its core title and year."""
    info = s.get("tmdb") or {}
    return f'tmdb:{info["id"]}' if info.get("id") else title_key(s)


def film_link(f):
    """A film's title, linked to its page here (or to the theater's page for it when it has none)."""
    path = FILM_PATHS.get(film_key(f))
    return f'<a href="{path}">{escape(f["title"])}</a>' if path else link(f["film_url"], escape(f["title"]))


def film_slug(film):
    return slug(film["title"]) + (f'-{film["year"]}' if film.get("year") else "") or "film"


def film_records(screenings):
    """This build's films for the archive: what's known about each and where it's shown."""
    films = {}
    for start, s in screenings:
        info = s.get("tmdb") or {}
        seen = {"title": info.get("title") or tmdb.core_title(s["title"]), "year": s["year"] or info.get("year"),
                "director": s["director"], "runtime": s["runtime"], "genres": s["genre_list"],
                "poster": info.get("poster") or s.get("image"), "tmdb": info.get("url")}
        f = films.setdefault(film_key(s), {**seen, "title_key": title_key(s), "shown": set()})
        for k, v in seen.items():
            f[k] = f[k] or v  # fill gaps from other theaters' listings of the same film
        f["shown"].add((start.date(), s["theater"]))
    return films


def render_film(film, shows, tmap, today):
    poster = (f'<img class="poster large" src="{escape(film["poster"])}" alt="" decoding="async" '
              f'referrerpolicy="no-referrer">' if film.get("poster") else "")
    meta = " · ".join(x for x in (film.get("year"), escape(film["director"]) if film.get("director") else None,
                                  f'{film["runtime"]} min' if film.get("runtime") else None,
                                  " / ".join((film.get("genres") or [])[:2]) or None) if x)
    title = escape(film["title"])
    if shows:
        k = len({s["theater"] for _, s in shows})
        intro = lede(shows, tmap, today, f'{plural(len(shows), "screening")} of <i>{title}</i> coming up at '
                                         f'{plural(k, "LA theater")}.')
        body = schedule_html(shows, tmap, today)
    else:
        last = archive.last_shown(film, today)
        intro = (f'<p class="lede">Not playing in LA right now. Last screened at '
                 f'{escape(tmap[last[1]]["name"]) if last[1] in tmap else "an LA theater"} on '
                 f'{last[0].strftime("%B %-d, %Y")}.</p>' if last else '<p class="lede">Not playing in LA right now.</p>')
        past = sorted((x for x in film["shown"] if x[0] <= today.isoformat()), reverse=True)[:10]
        body = ('<section class="intro"><h2 class="area-head">Where it played</h2><ul class="theater-list">' + "".join(
            f'<li>{datetime.fromisoformat(d).strftime("%b %-d, %Y")}<span class="hood">'
            f'{venue_link(tmap[t]) if t in tmap else ""}</span></li>' for d, t in past) + "</ul></section>") if past else ""
    tmdb_link = (f'<p class="theater-facts">{link(film["tmdb"], "More on TMDB")} · '
                 f'<a href="/listings/">Everything playing in LA</a></p>') if film.get("tmdb") else ""
    return f"""
<main><div class="wrap">
  <article class="event{" has-poster" if poster else ""}">
    {poster}
    <div class="event-body">
      <p class="eyebrow">Film</p>
      <h1>{title}</h1>
      {f'<p class="meta">{meta}</p>' if meta else ""}
      {intro}
      {tmdb_link}
    </div>
  </article>
  {body}
  <p class="upcoming-foot"><a class="more" href="/listings/">Everything playing in LA →</a></p>
</div></main>"""


def film_pages(arch, screenings, tmap, today, updated):
    """{path: html} for every film in the archive."""
    upcoming_by = OrderedDict()
    for x in screenings:
        upcoming_by.setdefault(film_key(x[1]), []).append(x)
    pages = {}
    for key, film in arch["films"].items():
        path = f'/films/{film["slug"]}/'
        shows = upcoming_by.get(key, [])
        label = f'{film["title"]} ({film["year"]})' if film.get("year") else film["title"]
        names = list(OrderedDict.fromkeys(tmap[s["theater"]]["name"] for _, s in shows))
        by = f', dir. {film["director"]}' if film.get("director") else ""
        desc = (f'Where to see {label} in Los Angeles{by}: {plural(len(shows), "screening")} at {", ".join(names[:3])}'
                f'{" and more" if len(names) > 3 else ""}. Times and tickets.' if shows
                else f'{label}{by}: not playing in LA right now. When and where it last screened.')
        movie = {"@type": "Movie", "@id": SITE_URL + path + "#film", "name": film["title"],
                 **({"dateCreated": str(film["year"])} if film.get("year") else {}),
                 **({"director": {"@type": "Person", "name": film["director"]}} if film.get("director") else {}),
                 **({"image": film["poster"]} if film.get("poster") else {}),
                 **({"sameAs": film["tmdb"]} if film.get("tmdb") else {})}
        if not shows:
            UNLISTED.add(path)
        pages[path] = page(f'{label} Showtimes in Los Angeles | {SITE_NAME}' if shows else f'{label} in Los Angeles | {SITE_NAME}',
                           desc, path, None, render_film(film, shows, tmap, today), updated, indexable=bool(shows),
                           image=film.get("poster"),
                           head=json_ld({"@graph": [movie, breadcrumbs((label, path))] + events_ld(shows, tmap, path)}))
    return pages


# ---------- for answer engines and other tools ----------

def listings_json(data, screenings, tmap, scraped):
    """Every upcoming screening as plain JSON at /listings.json, for anyone (or any AI tool) to read."""
    theaters = [t for t in theater_order(data["theaters"]) if has_page(t)]
    return json.dumps({
        "name": SITE_NAME, "url": f"{SITE_URL}/", "updated": scraped.isoformat(timespec="seconds"),
        "about": "Upcoming screenings at Los Angeles indie and repertory theaters, gathered from each theater's own "
                 "site. Tickets are sold by the theaters; times are America/Los_Angeles.",
        "theaters": [{"id": t["id"], "name": t["name"], "address": f'{t["address"]}, {city(t)}, CA',
                      "neighborhood": t["neighborhood"], "area": area(t), "website": t["url"],
                      "page": SITE_URL + theater_path(t), "calendar": f'{SITE_URL}/cal/{t["id"]}.ics'} for t in theaters],
        "screenings": [{
            "title": s["title"], "theater": s["theater"], "start": start.isoformat(),
            **({"end": (start + timedelta(minutes=s["runtime"])).isoformat()} if s["runtime"] else {}),
            "year": s["year"] or (s.get("tmdb") or {}).get("year"), "director": s["director"],
            "runtime_minutes": s["runtime"], "genres": s["genre_list"], "formats": s["format_tags"],
            "tags": s["event_tags"], "guests": s.get("guests"), "festival": s.get("festival"),
            "sold_out": s["sold_out"], "tickets": s["ticket_url"],
            "page": f'{SITE_URL}/dates/{start.date().isoformat()}/#f-{short_id(s["theater"], s["title"], start.date().isoformat())}',
            **({"film_page": SITE_URL + FILM_PATHS[film_key(s)]} if film_key(s) in FILM_PATHS else {}),
        } for start, s in screenings if has_page(tmap[s["theater"]])],
    }, ensure_ascii=False, separators=(",", ":")) + "\n"


def llms_txt(data, collections):
    """/llms.txt: a plain-text map of the site for AI tools (the llmstxt.org format)."""
    theaters = [t for t in theater_order(data["theaters"]) if has_page(t)]
    pages = [(p, re.sub(r"<[^>]+>", "", re.search(r"<title>(.*?) \| ", html).group(1)).replace("&amp;", "&").replace("&#x27;", "'"))
             for p, html in collections.items() if not p.startswith(("/theaters/", "/dates/2")) and p not in UNLISTED]
    return "\n".join([
        f"# {SITE_NAME}", "",
        f"> {TAGLINE}. What's playing at {len(theaters)} Los Angeles independent and repertory movie theaters: "
        "revivals, new indies, 35mm and 70mm prints, Q&As, festivals and one-night-only screenings. Rebuilt twice a "
        "day (7am and 3pm Pacific) from each theater's own website; tickets are sold by the theaters.", "",
        "Every listing page marks up its screenings as schema.org ScreeningEvent. Times are America/Los_Angeles.", "",
        "## Listings", "",
        f"- [Showing today]({SITE_URL}/): today's screenings, upcoming special events and the weekly picks",
        f"- [All listings]({SITE_URL}/listings/): the next week, day by day, with filters",
        *[f"- [{title}]({SITE_URL}{p})" for p, title in pages],
        f"- [Weekly picks]({SITE_URL}/picks/): a short, hand-written list of screenings worth leaving the house for", "",
        "## Theaters", "",
        *[f'- [{t["name"]}]({SITE_URL}{theater_path(t)}): {t["address"]}, {t["neighborhood"]}' for t in theaters], "",
        "## Data", "",
        f"- [listings.json]({SITE_URL}/listings.json): every upcoming screening as JSON (title, theater, start time, "
        "director, format, guests, sold out, ticket link)",
        f"- [Special events calendar]({SITE_URL}/cal/special-events.ics): iCalendar feed; each theater has one at "
        f"/cal/<theater id>.ics",
        f"- [About]({SITE_URL}/about/)", "",
        "Each film has a page at /films/<title>-<year>/ with every upcoming screening across theaters, or when and "
        "where it last screened.", ""])


def render_about(data):
    groups = OrderedDict()
    for t in theater_order(data["theaters"]):
        groups.setdefault(area(t), []).append(t)
    theaters = "".join(
        f'<h3>{escape(a)}</h3><ul class="about-theaters">' + "".join(
            f'<li>{link(t["url"], escape(t["name"]))} <span class="hood">{escape(t["neighborhood"])}</span>'
            f'<span class="feed">{feed_links("/cal/" + t["id"] + ".ics")}</span></li>' for t in ts) + "</ul>"
        for a, ts in groups.items())
    contact = (f'<p>Missing a theater, or spotted a wrong time? Write to '
               f'<a href="mailto:{escape(CONTACT_EMAIL)}">{escape(CONTACT_EMAIL)}</a>.</p>') if CONTACT_EMAIL else ""
    return f"""
<main><div class="wrap about">
  <header class="page-head">
    <p class="eyebrow">About</p>
    <h1>To live and watch movies in LA</h1>
  </header>
  <section class="prose">
    <p>I love movies. I love cinema. And I love film. If you have a special moving image playing somewhere
      &ndash; let me know! I&rsquo;m <a href="https://www.instagram.com/spacemania/" target="_blank"
      rel="noopener">@spacemania</a> on Instagram.</p>
    {contact}
  </section>
  <section class="prose">
    <h2>What is a goodtime?</h2>
    <p>{NAME} is an aggregate of what&rsquo;s playing at Los Angeles&rsquo;s independent and repertory cinemas:
      revivals, new indies, 35mm and 70mm prints, Q&amp;As, festivals and the one-night-only things. I built this
      because I feel like I constantly miss out on sick films.</p>
    <p>Updated every morning at 7am from each theater&rsquo;s own website and puts the day&rsquo;s screenings in
      one place. Tickets are always sold by the theater, so the times link straight to them.</p>
  </section>
  <section class="prose">
    <h2>Put it in your calendar</h2>
    <p>Every film has an <b>Add to calendar</b> link. You can also subscribe to a calendar that fills in on its
      own: every special event, or everything at one theater. In Apple Calendar or Outlook, use Subscribe. In
      Google Calendar, choose Other calendars → From URL and paste the address.</p>
    <p class="feed-row"><b>Every special event</b> {feed_links("/cal/special-events.ics")}</p>
  </section>
  <section class="prose">
    <h2>The theaters</h2>
    {theaters}
  </section>
</div></main>"""


def strip_wrapper(html):
    return re.sub(r"<!doctype html>|</?html[^>]*>|<head>|</head>|</?body>|<meta (charset|name=\"viewport\")[^>]*>", "", html).strip() + "\n"


NOT_FOUND = """
<main><div class="wrap">
  <header class="page-head">
    <p class="eyebrow">Page not found</p>
    <h1>That one&rsquo;s not playing</h1>
  </header>
  <p class="note">The page may have moved, or the screening has come and gone.
    <a class="more" href="/">See what&rsquo;s showing today →</a> or <a class="more" href="/listings/">browse every listing →</a></p>
</div></main>"""


def robots_txt():
    if PREVIEW:
        return "User-agent: *\nDisallow: /\n"
    # Everyone may crawl, including the AI search crawlers (OAI-SearchBot, ChatGPT-User, PerplexityBot,
    # ClaudeBot, Google-Extended); a separate group for any of them would replace these rules, not add to them.
    return f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n"


def sitemap(paths, lastmod):
    urls = "".join(f"<url><loc>{escape(SITE_URL + p)}</loc><lastmod>{lastmod}</lastmod></url>" for p in paths)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'


def favicon_ico(png):
    """favicon.ico holding the 48px PNG, for browsers and crawlers that only ask for /favicon.ico."""
    return struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 48, 48, 0, 0, 1, 32, len(png), 22) + png


def redirects():
    rules = ["/listings.html  /listings/  301"]
    # Once a custom domain is the primary one, send the netlify.app copy of the site there.
    netlify_host = f'{os.environ["SITE_NAME"]}.netlify.app' if os.environ.get("SITE_NAME") else None
    if netlify_host and urllib.parse.urlsplit(SITE_URL).hostname != netlify_host:
        rules.append(f"https://{netlify_host}/*  {SITE_URL}/:splat  301!")
    return "\n".join(rules) + "\n"


def headers():
    out = "/fonts/*\n  Cache-Control: public, max-age=31536000, immutable\n"
    out += "/cal/*\n  Content-Type: text/calendar; charset=utf-8\n  Cache-Control: public, max-age=3600\n"
    out += "/e/*\n  X-Robots-Tag: noindex\n"
    out += "/listings.json\n  Access-Control-Allow-Origin: *\n  Cache-Control: public, max-age=3600\n"
    out += "/llms.txt\n  Content-Type: text/plain; charset=utf-8\n"
    out += "/archive.json\n  X-Robots-Tag: noindex\n"  # the build's memory of past films (see archive.py)  # screening pages are for sharing; they expire after the day
    if PREVIEW:  # keep images and other files out of search too, not just the pages
        out += "/*\n  X-Robots-Tag: noindex, nofollow\n"
    return out


def manifest():
    return json.dumps({
        "name": SITE_NAME, "short_name": NAME, "description": DEFAULT_DESCRIPTION, "start_url": "/",
        "display": "browser", "background_color": "#FFFFFF", "theme_color": "#FFFFFF",
        "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}],
    }, indent=2) + "\n"


def main():
    global USES_TMDB
    data = json.loads((ROOT / "data" / "listings.json").read_text())
    now = datetime.now(LA)
    today = now.date()
    screenings = upcoming(data, now)
    USES_TMDB = any(s.get("tmdb") for _, s in screenings)
    arch = archive.record(archive.load(SITE_URL), film_records(screenings), today, film_slug)
    FILM_PATHS.update({k: f'/films/{f["slug"]}/' for k, f in arch["films"].items()})
    tmap = {t["id"]: t for t in data["theaters"]}
    places = [area(t) for t in data["theaters"] if has_page(t)]
    AREA_PAGES.update(a for a in AREAS if places.count(a) >= 2)
    scraped = datetime.fromisoformat(data["scraped_at"])
    updated = scraped.astimezone(LA).strftime("%b %-d, %-I:%M%p").lower().capitalize()

    tonight = [s for start, s in screenings if start.date() == today]
    venues = len({s["theater"] for s in tonight})
    listed = len({s["theater"] for _, s in screenings})
    home_description = (
        f"{len(tonight)} screenings at {venues} LA indie and repertory theaters today ({today.strftime('%A, %b %-d')}), "
        "plus upcoming Q&As, 35mm prints and one-night-only events."
        if tonight else DEFAULT_DESCRIPTION)
    listings_description = (
        f"Every upcoming screening at {listed} Los Angeles indie and repertory cinemas, day by day: "
        "the New Beverly, the Aero and Egyptian, Vidiots, Brain Dead Studios and more. "
        "Filter by theater, area, genre and special events.")
    stamp = ics_utc(scraped)

    home_body = render_home(data, screenings, now)
    graph = site_graph()
    graph["@graph"] += events_ld([x for x in screenings if x[0].date() == today], tmap, "/")
    home = page(f"LA Indie & Repertory Movie Showtimes Today | {SITE_NAME}", home_description, "/", "home",
                home_body, updated, head=json_ld(graph))
    listings = page(f"All Upcoming Indie & Repertory Screenings in LA | {SITE_NAME}", listings_description,
                    "/listings/", "listings", render_listings(data, screenings, now), updated, LISTINGS_SCRIPT)
    not_found = page(f"Page not found | {SITE_NAME}", DEFAULT_DESCRIPTION, "/404.html", None, NOT_FOUND, updated,
                     indexable=False)
    share = page(NAME, DEFAULT_DESCRIPTION, "/", "home", home_body, updated, share=True)
    about = page(f"About | {SITE_NAME}", "How GOODTIMES gathers LA's indie and repertory screenings, the theaters it "
                 "covers, and calendars you can subscribe to.", "/about/", "about", render_about(data), updated)

    week = read_picks(today)
    picks_desc = (f'This week\'s LA screenings worth leaving the house for: '
                  + ", ".join(display_title(p["title"]) for p in week["picks"])[:150] if week
                  else "A short weekly list of LA screenings worth leaving the house for.")
    picks = page(f"Worth Leaving the House For: This Week's LA Screenings | {SITE_NAME}", picks_desc, "/picks/", None,
                 render_picks_page(week, by_day(screenings, theater_order(data["theaters"])), tmap, today), updated,
                 indexable=bool(week))

    # Generated per screening, film and festival; cleared each build so past ones don't linger locally.
    generated = {}
    for day, venues in by_day(screenings, theater_order(data["theaters"])).items():
        for films in venues.values():
            for f in films.values():
                eid = event_id(f)
                desc = f.get("guests") or (f.get("blurb") or DEFAULT_DESCRIPTION)[:180]
                generated[f"e/{eid}/index.html"] = page(
                    f"{share_title(f, tmap)} | {SITE_NAME}", desc, f"/e/{eid}/", None,
                    render_event(f, tmap, today), updated, indexable=False, image=(f.get("tmdb") or {}).get("poster"))
    for start, s in screenings:
        generated[f'cal/s/{s["id"]}.ics'] = calendar(s["title"], [(start, s)], tmap, stamp)
    for t in data["theaters"]:
        generated[f'cal/{t["id"]}.ics'] = calendar(f'{t["name"]} · {NAME}',
                                                    [x for x in screenings if x[1]["theater"] == t["id"]], tmap, stamp, feed=True)
    generated["cal/special-events.ics"] = calendar(f"LA special screenings · {NAME}",
                                                   [x for x in screenings if x[1]["is_special"]], tmap, stamp, feed=True)
    festivals = OrderedDict()
    for start, s in screenings:
        if s.get("festival"):
            festivals.setdefault(s["festival"], []).append((start, s))
    for name, shows in festivals.items():
        generated[f"festivals/{slug(name)}/index.html"] = page(
            f"{name} in Los Angeles | {SITE_NAME}", f"Every {name} screening listed at LA theaters, with times and tickets.",
            f"/festivals/{slug(name)}/", None, render_festival(name, shows, tmap, today), updated)

    collections = collection_pages(data, screenings, tmap, today, updated)
    films = film_pages(arch, screenings, tmap, today, updated)
    for path, html in {**collections, **films}.items():
        generated[path.strip("/") + "/index.html"] = html

    files = {
        "index.html": home,
        "listings/index.html": listings,
        "about/index.html": about,
        "picks/index.html": picks,
        "404.html": not_found,
        "robots.txt": robots_txt(),
        "sitemap.xml": sitemap(["/", "/listings/", "/this-weekend/", "/theaters/", "/about/"] + (["/picks/"] if week else [])
                               + [p for p in collections if p not in ("/this-weekend/", "/theaters/") and p not in UNLISTED]
                               + [p for p in films if p not in UNLISTED]
                               + [f"/festivals/{slug(n)}/" for n in festivals],
                               scraped.isoformat(timespec="seconds")),
        "site.webmanifest": manifest(),
        "_redirects": redirects(),
        "_headers": headers(),
        "listings.json": listings_json(data, screenings, tmap, scraped),
        "llms.txt": llms_txt(data, collections),
        "archive.json": archive.dump(arch),
        f"{INDEXNOW_KEY}.txt": INDEXNOW_KEY + "\n",
    }
    copies = {
        "favicon.svg": ICON,
        "favicon-48.png": ROOT / "logo" / "favicon-48.png",
        "apple-touch-icon.png": ROOT / "logo" / "apple-touch-icon.png",
        "icon-192.png": ROOT / "logo" / "icon-192.png",
        "icon-512.png": ROOT / "logo" / "icon-512.png",
        "og-image.png": ROOT / "logo" / "og-image.png",
        "fonts/inter-latin.woff2": ROOT / "fonts" / "inter-latin.woff2",
        "fonts/inter-latin-ext.woff2": ROOT / "fonts" / "inter-latin-ext.woff2",
        "fonts/OFL.txt": ROOT / "fonts" / "OFL.txt",
    }
    ico = favicon_ico((ROOT / "logo" / "favicon-48.png").read_bytes())
    for out in (SITE, NETLIFY):
        (out / "listings.html").unlink(missing_ok=True)  # replaced by listings/index.html
        for folder in ["e", "cal", "festivals", "theaters", "dates", "films"] + [p.strip("/") for p in collections]:
            shutil.rmtree(out / folder, ignore_errors=True)
        for name, text in {**files, **generated}.items():
            (out / name).parent.mkdir(parents=True, exist_ok=True)
            (out / name).write_text(text)
        for name, src in copies.items():
            (out / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, out / name)
        (out / "favicon.ico").write_bytes(ico)
    (SITE / "share.html").write_text(strip_wrapper(share))
    print(f"Wrote the site ({len(generated)} screening, calendar and festival files) to {SITE} and {NETLIFY} "
          f"for {SITE_URL}" + (" (preview: not indexed)" if PREVIEW else ""))


if __name__ == "__main__":
    main()
