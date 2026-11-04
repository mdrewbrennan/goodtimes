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

import tmdb

ROOT = Path(__file__).parent
SITE = ROOT / "site"
LA = ZoneInfo("America/Los_Angeles")  # handles daylight saving; used for "today" and the Updated time
NAME = "GOODTIMES"        # the wordmark
SITE_NAME = "GOODTIMES LA"  # the name search engines, link previews and titles use
TAGLINE = "To Live and Watch Movies in LA"
# While friends test the site, ask search engines not to list it. Set to False at launch.
PREVIEW = True
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
    # A theater image that fails to load is removed, so the row falls back to its no-poster layout.
    return (f'<img class="poster {size}" src="{escape(src)}" alt="" loading="lazy" decoding="async" '
            f'referrerpolicy="no-referrer" onerror="this.closest(\'.has-poster\')?.classList.remove(\'has-poster\');this.remove()">')


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
            + json.dumps({"@context": "https://schema.org", **data}, ensure_ascii=False).replace("</", "<\\/")
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
NAV = (("home", "/", "Today&rsquo;s Showings"), ("listings", "/listings/", "All Listings"), ("about", "/about/", "About"))
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

def watch_keys(f):
    """Normalized titles a Letterboxd watchlist entry can match, plus the film's year."""
    info = f.get("tmdb") or {}
    keys = {tmdb.norm(t) for t in (tmdb.core_title(f["title"]), info.get("title")) if t}
    return "|".join(sorted(k for k in keys if k)), info.get("year") or f["year"] or ""


def film_row(f, tmap):
    words = [f["title"], f["director"] or "", f.get("guests") or "", f.get("festival") or ""]
    search = escape(" ".join(words + f["event_tags"] + f["format_tags"] + f["genre_list"]).lower())
    # The guest line often is the whole blurb; don't print it twice.
    blurb = (f'<p class="blurb">{escape(f["blurb"])}</p>'
             if f.get("blurb") and f["blurb"].strip().rstrip(".!") != (f.get("guests") or "").rstrip(".!") else "")
    keys, year = watch_keys(f)
    poster = poster_html(f)
    return (f'<li class="film{" has-poster" if poster else ""}" id="f-{event_id(f)}" data-special="{int(f["is_special"])}" '
            f'data-search="{search}" data-genres="{escape("|".join(f["genre_list"]))}" '
            f'data-keys="{escape(keys)}" data-year="{year}">{poster}'
            f'<div class="film-body">{tags_html(f)}<h4>{link(f["film_url"], escape(f["title"]))}</h4>'
            f'{meta_html(f)}{guests_html(f)}{blurb}{actions_html(f, tmap)}</div>'
            f'<div class="times">{times_html(f["times"])}</div></li>')


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
            f'<header class="venue-head"><h3 class="venue-name">{link(t["url"], escape(t["name"]))}</h3>'
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
            else '<p class="note">No picks this week yet. <a class="more" href="/listings/#special">See every special event →</a></p>')
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
    <p class="upcoming-foot"><a class="more" href="/listings/#special">See every special event in the listings →</a></p>
  </section>
</div></main>"""


def render_listings(data, screenings, now):
    today = now.date()
    theaters = theater_order(data["theaters"])
    tmap = {t["id"]: t for t in theaters}

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
    <button class="chip" id="watch" type="button" aria-pressed="false" aria-controls="watch-panel">Letterboxd watchlist</button>
    <input class="search" id="search" type="search" placeholder="Search films, directors, guests, 35mm…" aria-label="Search listings">
  </div>
  <div class="watch-panel" id="watch-panel" hidden>
    <p id="watch-intro">See which films on your Letterboxd watchlist are playing. On Letterboxd, go to
      Settings → Data → Export your data, unzip the download and choose <b>watchlist.csv</b>.
      It stays in this browser; nothing is uploaded.</p>
    <p id="watch-status" hidden></p>
    <div class="watch-row">
      <label class="chip file"><input type="file" id="watch-file" accept=".csv,text/csv"><span id="watch-choose">Choose watchlist.csv</span></label>
      <button type="button" class="link-button" id="watch-forget" hidden>Forget my watchlist</button>
    </div>
  </div>
  <p class="near-status" id="near-status" hidden></p>
  <div class="days">{"".join(nav)}</div>
</div></nav>
<main class="listings"><div class="wrap">
  {"".join(sections) or '<p class="empty">No upcoming screenings found.</p>'}
  <p class="empty" id="no-results" hidden>Nothing matches. Try another search or filter.</p>
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
  const watch = document.getElementById("watch");
  const search = document.getElementById("search");
  const pressed = b => b.getAttribute("aria-pressed") === "true";
  const press = (b, on) => { b.setAttribute("aria-pressed", on ? "true" : "false"); b.classList.toggle("on", on); };

  // Letterboxd watchlist: a Set of normalized titles, each with the years it was listed under.
  let watchlist = null;
  const norm = t => t.normalize("NFKD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase()
    .replace(/&/g, "and").replace(/^(the|a|an) /, "").replace(/[^a-z0-9]/g, "");
  const onWatchlist = f => {
    if (!watchlist || !f.dataset.keys) return false;
    const year = +f.dataset.year;
    return f.dataset.keys.split("|").some(k => watchlist.has(k)
      && (!year || watchlist.get(k).some(y => !y || Math.abs(y - year) <= 1)));
  };

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
    const onlySpecial = pressed(special), onlyWatch = pressed(watch);
    let any = false, matched = new Set();
    document.querySelectorAll(".day").forEach(day => {
      let dayVisible = false;
      day.querySelectorAll(".venue").forEach(v => {
        let venueVisible = false;
        v.querySelectorAll(".film").forEach(f => {
          const listed = onWatchlist(f);
          if (listed) matched.add(f.dataset.keys);
          const ok = (chosen.size === 0 || chosen.has(v.dataset.theater))
            && (genres.size === 0 || f.dataset.genres.split("|").some(g => genres.has(g)))
            && (!onlySpecial || f.dataset.special === "1")
            && (!onlyWatch || listed)
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
    if (watchlist) {
      watch.textContent = `My watchlist · ${matched.size}`;
      const status = document.getElementById("watch-status");
      status.hidden = false;
      status.textContent = matched.size
        ? `${matched.size} film${matched.size === 1 ? "" : "s"} from your watchlist (${watchlist.size} titles) ${matched.size === 1 ? "is" : "are"} playing.`
        : `None of the ${watchlist.size} films on your watchlist are playing right now.`;
    }
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

  // Letterboxd watchlist
  const panel = document.getElementById("watch-panel");
  const store = { get: () => { try { return localStorage.getItem("watchlist"); } catch { return null; } },
                  set: v => { try { v === null ? localStorage.removeItem("watchlist") : localStorage.setItem("watchlist", v); } catch {} } };
  function parseCsv(text) {
    const rows = [];
    let row = [], cell = "", quoted = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (quoted) {
        if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
        else if (c === '"') quoted = false;
        else cell += c;
      } else if (c === '"') quoted = true;
      else if (c === ",") { row.push(cell); cell = ""; }
      else if (c === "\\n" || c === "\\r") {
        if (c === "\\r" && text[i + 1] === "\\n") i++;
        row.push(cell); rows.push(row); row = []; cell = "";
      } else cell += c;
    }
    if (cell || row.length) { row.push(cell); rows.push(row); }
    return rows;
  }
  function loadWatchlist(entries) {
    watchlist = new Map();
    for (const [name, year] of entries) {
      const k = norm(name);
      if (k) watchlist.set(k, [...(watchlist.get(k) || []), +year || 0]);
    }
    document.getElementById("watch-forget").hidden = false;
    document.getElementById("watch-intro").hidden = true;
    document.getElementById("watch-choose").textContent = "Choose another file";
  }
  document.getElementById("watch-file").addEventListener("change", async e => {
    const file = e.target.files[0];
    if (!file) return;
    const rows = parseCsv(await file.text());
    const head = (rows.shift() || []).map(h => h.trim().toLowerCase());
    const ni = head.indexOf("name"), yi = head.indexOf("year");
    const status = document.getElementById("watch-status");
    if (ni < 0) { status.hidden = false; status.textContent = "That doesn't look like a Letterboxd watchlist.csv (it has no Name column)."; return; }
    const entries = rows.filter(r => r[ni]).map(r => [r[ni], r[yi]]);
    store.set(JSON.stringify(entries));
    loadWatchlist(entries);
    press(watch, true);
    apply();
  });
  document.getElementById("watch-forget").addEventListener("click", () => {
    store.set(null);
    watchlist = null;
    press(watch, false);
    watch.textContent = "Letterboxd watchlist";
    document.getElementById("watch-status").hidden = true;
    document.getElementById("watch-intro").hidden = false;
    document.getElementById("watch-forget").hidden = true;
    document.getElementById("watch-choose").textContent = "Choose watchlist.csv";
    apply();
  });
  watch.addEventListener("click", () => {
    if (!watchlist) { panel.hidden = !panel.hidden; return; }  // nothing loaded yet: show how to load one
    press(watch, !pressed(watch));
    panel.hidden = !pressed(watch);
    apply();
  });
  try { const saved = JSON.parse(store.get()); if (Array.isArray(saved)) loadWatchlist(saved); } catch {}

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
      <p class="event-foot"><a class="more" href="/listings/#d{day.isoformat()}">Everything playing {day.strftime("%a %b %-d")} →</a></p>
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
  <p class="upcoming-foot"><a class="more" href="/listings/#special">Every special event in the listings →</a></p>
</div></main>"""


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
    <p>{NAME} lists what&rsquo;s playing at Los Angeles&rsquo;s independent and repertory cinemas: revivals,
      new indies, 35mm and 70mm prints, Q&amp;As, festivals and the one-night-only things that are easy to miss.</p>
    <p>Every morning it reads each theater&rsquo;s own website and puts the day&rsquo;s screenings in one place.
      Tickets are always sold by the theater, so the times link straight to them. If a theater&rsquo;s site
      changes or goes down, its listings can be missing for a day until it&rsquo;s fixed.</p>
    {contact}
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
    out += "/e/*\n  X-Robots-Tag: noindex\n"  # screening pages are for sharing; they expire after the day
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
    tmap = {t["id"]: t for t in data["theaters"]}
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
    home = page(f"LA Indie & Repertory Movie Showtimes Today | {SITE_NAME}", home_description, "/", "home",
                home_body, updated, head=json_ld(site_graph()))
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

    files = {
        "index.html": home,
        "listings/index.html": listings,
        "about/index.html": about,
        "picks/index.html": picks,
        "404.html": not_found,
        "robots.txt": robots_txt(),
        "sitemap.xml": sitemap(["/", "/listings/", "/about/"] + (["/picks/"] if week else []) + [f"/festivals/{slug(n)}/" for n in festivals],
                               scraped.isoformat(timespec="seconds")),
        "site.webmanifest": manifest(),
        "_redirects": redirects(),
        "_headers": headers(),
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
        for folder in ("e", "cal", "festivals"):
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
