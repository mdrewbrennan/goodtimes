"""Shared helpers for theaters that sell through Veezi (New Beverly, Vista).

Not a scraper module itself (no THEATERS). The public Veezi sessions page lists every session with its
purchase link and a SOLD OUT marker, which the theaters' own sites only partly expose.
"""

import re
from urllib.parse import urljoin
from datetime import date, datetime, timedelta

from .common import clean, fetch

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
     "November", "December"], 1)}

TIME = re.compile(r"(\d{1,2}):(\d{2})\s*([ap])m", re.I)
DATE_BLOCK = re.compile(r'<h3 class="date-title[^>]*>\s*(?:\w+)\s+(\d+),\s*(\w+)\s*</h3>(.*?)(?=<h3 class="date-title|\Z)', re.S)
FILM_BLOCK = re.compile(r'<h3 class="title">\s*(.*?)\s*</h3>(.*?)(?=<h3 class="title">|\Z)', re.S)
SESSIONS_URL = "https://ticketing.uswest.veezi.com/sessions/"
SESSION = re.compile(r"<li>(.*?)</li>", re.S)


def la_offset(d, hour=12):
    """UTC offset string for a Los Angeles local date/time (DST: 2nd Sun of March to 1st Sun of Nov, 2am)."""
    march = date(d.year, 3, 1)
    dst_start = march + timedelta(days=(6 - march.weekday()) % 7 + 7)
    nov = date(d.year, 11, 1)
    dst_end = nov + timedelta(days=(6 - nov.weekday()) % 7)
    local = datetime(d.year, d.month, d.day, hour)
    dst = datetime(dst_start.year, dst_start.month, dst_start.day, 2) <= local < \
        datetime(dst_end.year, dst_end.month, dst_end.day, 2)
    return "-07:00" if dst else "-08:00"


def parse_time(text):
    m = TIME.search(text or "")
    if not m:
        return None
    h, mi, ap = int(m.group(1)) % 12, int(m.group(2)), m.group(3).lower()
    return h + (12 if ap == "p" else 0), mi


def iso(d, hm):
    return f"{d.isoformat()}T{hm[0]:02d}:{hm[1]:02d}:00{la_offset(d, hm[0])}"


def infer_date(month, day, today=None):
    today = today or date.today()
    d = date(today.year, month, day)
    return d if d >= today - timedelta(days=60) else date(today.year + 1, month, day)


def sessions(site_token, today=None):
    """All sessions on a Veezi sessions page: dicts with date, hm (hour, minute), title, url (None if sold out), sold_out."""
    page = fetch(f"https://ticketing.uswest.veezi.com/sessions/?siteToken={site_token}")
    out = []
    for day, month, body in DATE_BLOCK.findall(page):
        d = infer_date(MONTHS[month], int(day), today)
        for title, rest in FILM_BLOCK.findall(body):
            for li in SESSION.findall(rest):
                hm = parse_time(li)
                if not hm:
                    continue
                url = re.search(r'href="([^"]*purchase[^"]*)"', li)
                out.append({
                    "date": d, "hm": hm, "title": clean(re.sub(r"<[^>]+>", "", title)),
                    "url": urljoin(SESSIONS_URL, clean(url.group(1))) if url else None,
                    "sold_out": "sold-out" in li,
                })
    return out
