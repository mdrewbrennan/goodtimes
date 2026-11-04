"""Fine Arts Theatre (Beverly Hills): 70mm and 35mm revivals, double features.

Sessions come from Veezi, the theater's ticketing, whose public sessions page lists every session with
its purchase link and a sold-out marker. Veezi titles are rough: they carry the print format ("Batman
(1989) 70mm"), are sometimes in capitals, and double features are squeezed into one cut-off name
("KIKI'S DELIVERY/ONLY"). So we also read the theater's own page (fineartstheatrebh.com, a GoDaddy
site with no structured data), which spells out each double feature film by film under its date:

    Sunday, Dec 20th / Ghibli Double Feature III /
    Kiki's Delivery Service (Subtitled) 7:00 PM (103 minutes) & Only Yesterday (Subtitled) 9:09 PM ...

A Veezi double-feature session becomes one listing per film, each with its own title, start time and
runtime and the same ticket link, so each film gets its own poster. When the page and Veezi disagree
on a name and one is a prefix of the other (the page's "Nausica", Veezi's "NAUSICAA"), the longer one
wins. The page's "<title> in 70mm" headings also fill in formats Veezi leaves out. If the page can't be
read or parsed, Veezi's titles are used as before.
"""

import re
from datetime import date, datetime

from . import veezi
from .common import clean, fetch, screening
from .la_offset import la_iso
from .titlecase import SMALL, smart_case

SITE_TOKEN = "tez3prscsvfbagchhkxbevjwk8"
TICKETS = f"https://ticketing.uswest.veezi.com/sessions/?siteToken={SITE_TOKEN}"
SITE = "https://fineartstheatrebh.com/"

THEATERS = [
    {
        "id": "finearts",
        "name": "Fine Arts Theatre",
        "neighborhood": "Beverly Hills",
        "address": "8556 Wilshire Blvd",
        "url": SITE,
    },
]

FORMAT = re.compile(r"\s+(?:in\s+)?(16mm|35mm|70mm)\b\s*$", re.I)
YEAR = re.compile(r"\s*\((\d{4})\)\s*$")
SITE_DATE = re.compile(r"^\w+day,\s+([A-Z][a-z]{2})\w*\.?\s+(\d{1,2})(?:st|nd|rd|th)?$")
SITE_FILM = re.compile(r"^&?\s*(.+?)\s*(?:\((Subtitled|Dubbed)\))?\s+(\d{1,2}:\d{2}\s*[AP]M)\s*\(?\s*(\d+)\s*minutes",
                       re.I)
SITE_PROGRAM = re.compile(r"^(.*Double Feature\s+[IVXL]+)$", re.I)
SITE_FORMAT = re.compile(r"^(.+?)\s+in\s+(16mm|35mm|70mm)$", re.I)
MONTHS = {name[:3]: number for name, number in veezi.MONTHS.items()}


def _norm(title):
    return re.sub(r"[^a-z0-9]", "", title.lower())


def _parse(raw):
    title, fmt, year = raw.strip(), None, None
    m = FORMAT.search(title)
    if m:
        fmt, title = m.group(1).lower(), title[:m.start()]
    m = YEAR.search(title)
    if m:
        year, title = m.group(1), title[:m.start()]
    title = re.sub(r"\s*/\s*", " / ", title)
    return smart_case(title.strip()), fmt, year


def _site(today):
    """From the theater's page: {date: (program name, [film dicts])} and {normalized title: format}."""
    page = re.sub(r"<script.*?</script>|<style.*?</style>", "", fetch(SITE), flags=re.S)
    lines = [clean(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", chunk)))
             for chunk in re.split(r"</(?:p|h\d|div|li|span)>|<br\s*/?>", page)]
    programs, formats, day, program = {}, {}, None, None
    for line in filter(None, lines):
        m = SITE_FORMAT.match(line)
        if m:
            formats.setdefault(_norm(YEAR.sub("", m.group(1))), m.group(2).lower())
        m = SITE_DATE.match(line)
        if m and m.group(1).title() in MONTHS:
            day, program = veezi.infer_date(MONTHS[m.group(1).title()], int(m.group(2)), today), None
            continue
        m = SITE_PROGRAM.match(line)
        if m and day:
            program = m.group(1)
            continue
        m = SITE_FILM.match(line)
        if m and day and program:
            hm = veezi.parse_time(m.group(3))
            films = programs.setdefault(day, (program, []))[1]
            if hm and all(f["title"] != m.group(1) for f in films):
                films.append({"title": m.group(1).strip(" &"), "hm": hm, "runtime": int(m.group(4)),
                              "lang": (m.group(2) or "").title()})
    return programs, formats


def _small_words(title):
    """'Castle In The Sky' -> 'Castle in the Sky': the page capitalizes every word."""
    words = title.split(" ")
    return " ".join(w.lower() if i and w.lower() in SMALL and not words[i - 1].endswith(":") else w
                    for i, w in enumerate(words))


def _best_name(site_name, veezi_parts):
    """The site's name, unless a Veezi part extends it (or vice versa); then the longer, tidied."""
    key = _norm(site_name)
    for part in veezi_parts:
        other = _norm(part)
        if other and key and (other.startswith(key) or key.startswith(other)):
            return _small_words(smart_case(part) if len(other) > len(key) else site_name)
    return _small_words(site_name)


def scrape(theater):
    today = date.today()
    try:
        programs, formats = _site(today)
    except Exception:  # the page is a bonus; Veezi alone still makes a listing
        programs, formats = {}, {}
    out = []
    for s in veezi.sessions(SITE_TOKEN, today):
        title, fmt, year = _parse(s["title"])
        fmt = fmt or formats.get(_norm(title))
        url = s["url"] or TICKETS
        program = programs.get(s["date"])
        double = re.search(r"double feature| / ", title, re.I)
        if double and program and len(program[1]) >= 2:
            name, films = program
            parts = [re.sub(r"\s*double feature\s*$", "", p, flags=re.I).strip()
                     for p in re.split(r"\s*/\s*", s["title"])]
            lineup = ", then ".join(f"{_best_name(f['title'], parts)} at "
                                    f"{datetime(2000, 1, 1, *f['hm']):%-I:%M %p}" for f in films)
            for f in films:
                start = datetime(s["date"].year, s["date"].month, s["date"].day, *f["hm"])
                note = f"{name}: one ticket for both films ({lineup}). Double feature."
                if f["lang"]:
                    note += f" {f['lang']}."
                out.append(screening(
                    theater, _best_name(f["title"], parts), la_iso(start), url, runtime=f["runtime"],
                    blurb=note, sold_out=s["sold_out"],
                ))
            continue
        extra = [f"Presented in {fmt}." if fmt else "", "Double feature." if double else ""]
        out.append(screening(
            theater, title, veezi.iso(s["date"], s["hm"]), url,
            year=year, blurb=" ".join(x for x in extra if x) or None, sold_out=s["sold_out"],
        ))
    return out
