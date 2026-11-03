"""Render data/listings.json into the GOODTIMES site.

  site/index.html     homepage: special events, tonight, the theaters
  site/listings.html  every upcoming screening, by day
  site/share.html     the homepage without its document wrapper, for the claude.ai share link

To use a real logo, drop logo.svg or logo.png into site/ and rebuild.

Standard library only: python3 build.py
"""

import json
import re
import urllib.parse
from collections import OrderedDict
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
SITE = ROOT / "site"
LA = ZoneInfo("America/Los_Angeles")  # handles daylight saving; used for "today" and the Updated time
NAME = "GOODTIMES"
TAGLINE = "To Live and Watch Movies in LA"
# While friends test the site, ask search engines not to list it. Set to False at launch.
PREVIEW = True
NETLIFY = ROOT / "netlify"  # drag this folder onto app.netlify.com/drop

# Tags read from each screening's title and blurb. EVENT tags make a screening a special event.
EVENT_TAGS = [
    ("Live score", r"live score"),
    ("Recorded Q&A", r"(pre-recorded|livestream) q&a"),
    ("Guests in person", r"in person|followed by a (conversation|q&a)|\bq&a\b|special guests|"
                         r"(thrilled|electrified|excited) to welcome|with (director|writer)s?\b"),
    ("Festival", r"festival|^cybercon"),
    ("Premiere", r"\bpremiere\b"),
    ("Special screening", r"special (free )?(advance )?screening|presented by|\bpresents\b|birthday"),
    ("Advance screening", r"advance screening"),
    ("Sing-along", r"sing[ -]?along"),
    ("Workshop", r"workshop"),
    ("Book launch", r"book launch"),
    ("Mystery screening", r"surprise screening|mystery screening"),
]
FORMAT_TAGS = [("35mm", r"\b35mm\b"), ("16mm", r"\b16mm\b"), ("70mm", r"\b70mm\b")]


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
    if "Recorded Q&A" in events and "Guests in person" in events:
        events.remove("Guests in person")  # "Pre-Recorded Q&A" also matches the in-person pattern
    if len(events) > 1 and "Special screening" in events:
        events.remove("Special screening")  # the generic tag only when nothing more specific applies
    if screening["special_event"] and not events:
        events.append(event_label(screening.get("event_label")))
    screening["event_tags"] = events
    screening["format_tags"] = [name for name, pat in FORMAT_TAGS if re.search(pat, text, re.I)]
    screening["is_special"] = bool(events)


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


def tags_html(film):
    tags = [f'<span class="tag">{t}</span>' for t in film["event_tags"]]
    tags += [f'<span class="tag format">{t}</span>' for t in film["format_tags"]]
    return f'<span class="tags">{"".join(tags)}</span>' if tags else ""


def meta_html(film):
    parts = [film["year"], escape(film["director"]) if film["director"] else None,
             f'{film["runtime"]} min' if film["runtime"] else None,
             " / ".join(film["genres"][:2]) or None]
    parts = " · ".join(p for p in parts if p)
    return f'<p class="meta">{parts}</p>' if parts else ""


LOGO = ROOT / "logo" / "goodtimes.svg"


ICON = ROOT / "logo" / "goodtimes-icon.svg"


def favicon_uri():
    """The tab icon, embedded as a data URI so it works anywhere the page is served."""
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


def page(title, active, body, updated, script=""):
    nav = "".join(
        f'<a href="{href}"{" aria-current=page" if key == active else ""}>{label}</a>'
        for key, href, label in (("home", "index.html", "Today&rsquo;s Showings"), ("listings", "listings.html", "All Listings")))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<link rel="icon" type="image/svg+xml" href="{favicon_uri()}">
<meta name="claude:viewport-fit-sides" content="cover">
<meta name="description" content="Repertory, indie and one-night-only film across Los Angeles.">
{'<meta name="robots" content="noindex, nofollow">' if PREVIEW else ""}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
{(ROOT / "style.css").read_text()}
</style>
</head>
<body>
<header class="mast"><div class="wrap">
  <div class="brand">
    <a class="logo" href="index.html">{logo_html()}</a>
    <p class="tagline">{TAGLINE}</p>
  </div>
  <nav class="site-nav">{nav}</nav>
</div></header>
{body}
<footer><div class="wrap">
  <span><b>{NAME}</b> · An Aggregate of Almost Every Indie and One-Night-Only Film Playing in L.A. Tonight</span>
  <span>Updated {updated}. Tickets are sold by each theater.</span>
</div></footer>
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

def film_row(f):
    search = escape(f'{f["title"]} {f["director"] or ""} {" ".join(f["event_tags"] + f["format_tags"])}'.lower())
    blurb = f'<p class="blurb">{escape(f["blurb"])}</p>' if f.get("blurb") else ""
    return (f'<li class="film" data-special="{int(f["is_special"])}" data-search="{search}">'
            f'<div class="film-body">{tags_html(f)}<h3>{link(f["film_url"], escape(f["title"]))}</h3>'
            f'{meta_html(f)}{blurb}</div>'
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
        blocks.append(
            f'<div class="venue" data-theater="{tid}">'
            f'<header class="venue-head"><h3 class="venue-name">{link(t["url"], escape(t["name"]))}</h3>'
            f'{operator_html(t)}'
            f'<p class="venue-meta"><span class="hood">{escape(t["neighborhood"])}</span></p></header>'
            f'<ul>{"".join(film_row(f) for f in films.values())}</ul></div>')
    head = (f'<div class="day-head"><h2>{day_label(day, today)}<span class="date">{day.strftime("%b %-d")}</span></h2>'
            f'<span class="count">{n} screening{"s" if n != 1 else ""}</span></div>') if heading else ""
    return f'<section class="day" id="d{day.isoformat()}">{head}{"".join(blocks)}</section>', n, special


def more_dates(n):
    return f'<br>+{n} more date{"s" if n > 1 else ""}' if n else ""


def render_home(data, screenings, now):
    today = now.date()
    tmap = {t["id"]: t for t in data["theaters"]}
    days = by_day(screenings, data["theaters"])

    if today in days:
        today_html, n, _ = day_section(today, days[today], tmap, today, heading=False)
    else:
        n, nxt = 0, next(iter(days), None)
        today_html = '<p class="note">Nothing else on screen today.' + (
            f' Next up: {day_label(nxt, today)}, {nxt.strftime("%b %-d")}. '
            f'<a class="more" href="listings.html">See listings →</a>' if nxt else "") + '</p>'

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
        f'<div>{tags_html(ev)}<h3>{escape(ev["title"])}</h3></div>'
        f'<span class="where">{escape(tmap[ev["theater"]]["name"])}'
        f'{more_dates(more)}{"<br><span class=sold-note>Sold out</span>" if all(x["sold_out"] for _, x in ev["times"]) else ""}'
        f'</span></a></li>'
        for ev, more in events[:10])

    venues = sum(1 for v in days.get(today, {}).values() if v)
    return f"""
<main><div class="wrap">
  <header class="page-head">
    <p class="eyebrow">{today.strftime("%A, %B %-d")} · {n} screening{"s" if n != 1 else ""} at {venues} theater{"s" if venues != 1 else ""}</p>
    <h1>Showing today</h1>
  </header>
  {today_html}
  <section class="upcoming">
    <div class="day-head"><h2>Upcoming special events</h2></div>
    <ul class="upcoming-list">{rows or '<li class="note">No special events posted right now.</li>'}</ul>
    <p class="upcoming-foot"><a class="more" href="listings.html#special">See every special event in the listings →</a></p>
  </section>
</div></main>"""


def render_listings(data, screenings, now):
    today = now.date()
    theaters = data["theaters"]
    tmap = {t["id"]: t for t in theaters}

    sections, nav = [], []
    for day, venues in by_day(screenings, theaters).items():
        html, _, special = day_section(day, venues, tmap, today)
        sections.append(html)
        nav.append(f'<a href="#d{day.isoformat()}"{" class=has-special" if special else ""}>'
                   f'<span>{day.strftime("%a")}</span>{day.strftime("%-d")}</a>')

    listed = {s["theater"] for _, s in screenings}
    options = "".join(
        f'<label class="option"><input type="checkbox" value="{t["id"]}">'
        f'<span>{escape(t["name"])}</span>'
        f'<span class="hood">{escape(" · ".join(x for x in (t.get("operator"), t["neighborhood"]) if x))}</span></label>'
        for t in sorted(theaters, key=lambda t: t["name"].lower().removeprefix("the ")) if t["id"] in listed)
    return f"""
<nav class="controls" aria-label="Filter listings"><div class="wrap">
  <div class="control-row">
    <details class="picker" id="theaters">
      <summary class="select" id="theaters-label">All theaters</summary>
      <div class="menu" role="group" aria-label="Theaters">
        {options}
        <div class="menu-foot"><button type="button" class="link-button" id="clear-theaters">Show all theaters</button></div>
      </div>
    </details>
    <button class="chip" id="special" type="button" aria-pressed="false">Special events</button>
    <input class="search" id="search" type="search" placeholder="Search films, directors, 35mm…" aria-label="Search listings">
  </div>
  <div class="days">{"".join(nav)}</div>
</div></nav>
<main class="listings"><div class="wrap">
  {"".join(sections) or '<p class="empty">No upcoming screenings found.</p>'}
  <p class="empty" id="no-results" hidden>Nothing matches. Try another search or filter.</p>
  <button class="to-top" id="to-top" type="button" hidden>↑ Back to top</button>
</div></main>"""


LISTINGS_SCRIPT = """<script>
  const picker = document.getElementById("theaters");
  const boxes = [...picker.querySelectorAll("input[type=checkbox]")];
  const special = document.getElementById("special");
  const search = document.getElementById("search");
  function apply() {
    const q = search.value.trim().toLowerCase();
    const picked = boxes.filter(b => b.checked);
    const chosen = new Set(picked.map(b => b.value));
    document.getElementById("theaters-label").textContent =
      picked.length === 0 ? "All theaters"
      : picked.length === 1 ? picked[0].nextElementSibling.textContent
      : `${picked.length} theaters`;
    picker.classList.toggle("on", picked.length > 0);
    const onlySpecial = special.getAttribute("aria-pressed") === "true";
    special.classList.toggle("on", onlySpecial);
    let any = false;
    document.querySelectorAll(".day").forEach(day => {
      let dayVisible = false;
      day.querySelectorAll(".venue").forEach(v => {
        let venueVisible = false;
        v.querySelectorAll(".film").forEach(f => {
          const ok = (chosen.size === 0 || chosen.has(v.dataset.theater))
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
  special.addEventListener("click", () => {
    special.setAttribute("aria-pressed", special.getAttribute("aria-pressed") === "true" ? "false" : "true");
    apply();
  });
  boxes.forEach(b => b.addEventListener("change", apply));
  document.getElementById("clear-theaters").addEventListener("click", () => {
    boxes.forEach(b => { b.checked = false; });
    apply();
  });
  // Close the theater menu on an outside click or Escape.
  document.addEventListener("click", e => { if (!picker.contains(e.target)) picker.open = false; });
  document.addEventListener("keydown", e => { if (e.key === "Escape") picker.open = false; });
  search.addEventListener("input", apply);
  // listings.html#special turns the special events filter on; listings.html#<theater id> picks a theater.
  // Back to top: appears once you've scrolled a couple of screens down.
  const toTop = document.getElementById("to-top");
  const onScroll = () => { toTop.hidden = scrollY < innerHeight * 1.5; };
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();
  toTop.addEventListener("click", () => {
    const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;
    scrollTo({ top: 0, behavior: smooth ? "smooth" : "instant" });
  });

  function fromHash() {
    const hash = location.hash.slice(1);
    if (hash === "special") special.setAttribute("aria-pressed", "true");
    else if (boxes.some(b => b.value === hash)) boxes.forEach(b => { b.checked = b.value === hash; });
    apply();
  }
  window.addEventListener("hashchange", fromHash);
  fromHash();
</script>"""


def strip_wrapper(html):
    return re.sub(r"<!doctype html>|</?html[^>]*>|<head>|</head>|</?body>|<meta (charset|name=\"viewport\")[^>]*>", "", html).strip() + "\n"


def main():
    data = json.loads((ROOT / "data" / "listings.json").read_text())
    now = datetime.now(LA)
    screenings = upcoming(data, now)
    updated = datetime.fromisoformat(data["scraped_at"]).astimezone(LA).strftime("%b %-d, %-I:%M%p").lower().capitalize()

    home = page(NAME, "home", render_home(data, screenings, now), updated)
    listings = page(f"Listings · {NAME}", "listings", render_listings(data, screenings, now), updated, LISTINGS_SCRIPT)
    SITE.mkdir(exist_ok=True)
    (SITE / "index.html").write_text(home)
    (SITE / "listings.html").write_text(listings)
    (SITE / "share.html").write_text(strip_wrapper(home))

    NETLIFY.mkdir(exist_ok=True)
    (NETLIFY / "index.html").write_text(home)
    (NETLIFY / "listings.html").write_text(listings)
    (NETLIFY / "robots.txt").write_text("User-agent: *\nDisallow: /\n" if PREVIEW else "User-agent: *\nAllow: /\n")
    print(f"Wrote index.html, listings.html and share.html to {SITE}")


if __name__ == "__main__":
    main()
