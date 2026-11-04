"""Fine Arts Theatre (Beverly Hills): 70mm and 35mm revivals, double features.

fineartstheatrebh.com is a GoDaddy site builder page with no structured schedule, but the theater sells
through Veezi, whose public sessions page lists every session with its purchase link and a sold-out
marker. Veezi titles carry the print format ("Batman (1989) 70mm") and are sometimes in capitals or cut
short ("KIKI'S DELIVERY/ONLY"); we move the format and year out of the title and tidy the case.
"""

import re
from datetime import date

from . import veezi
from .common import screening
from .titlecase import smart_case

SITE_TOKEN = "tez3prscsvfbagchhkxbevjwk8"
TICKETS = f"https://ticketing.uswest.veezi.com/sessions/?siteToken={SITE_TOKEN}"

THEATERS = [
    {
        "id": "finearts",
        "name": "Fine Arts Theatre",
        "neighborhood": "Beverly Hills",
        "address": "8556 Wilshire Blvd",
        "url": "https://fineartstheatrebh.com/",
    },
]

FORMAT = re.compile(r"\s+(?:in\s+)?(16mm|35mm|70mm)\b\s*$", re.I)
YEAR = re.compile(r"\s*\((\d{4})\)\s*$")


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


def scrape(theater):
    out = []
    for s in veezi.sessions(SITE_TOKEN, date.today()):
        title, fmt, year = _parse(s["title"])
        extra = [f"Presented in {fmt}." if fmt else ""]
        if re.search(r"double feature| / ", title, re.I):
            extra.append("Double feature.")
        out.append(screening(
            theater, title, veezi.iso(s["date"], s["hm"]), s["url"] or TICKETS,
            year=year, blurb=" ".join(x for x in extra if x) or None, sold_out=s["sold_out"],
        ))
    return out
