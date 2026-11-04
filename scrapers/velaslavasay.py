"""Velaslavasay Panorama (University Park): a panorama museum; we list its film screenings only.

panoramaonview.org is Drupal. Its upcoming-events view lists each event with a title, a subtitle, a
body and a machine-readable start (content="2026-11-05T19:00:00-08:00"). Most events are talks,
music, tours or installations, so we keep one only when its title or subtitle says screening, film,
cinema, microcinema, 16mm/35mm or moving image, or its body says screening, microcinema or "16mm/35mm
film/print" (the body alone isn't enough for "film" or "cinema": artist bios use those words for
everything, and "35mm" alone is often slides, as in a magic-lantern lecture).
Events the Panorama presents elsewhere ("**At the Philosophical Research Society**") are skipped.
"""

import re

from .common import blurb, clean, fetch, https_url, screening

BASE = "https://www.panoramaonview.org"

THEATERS = [
    {
        "id": "velaslavasay",
        "name": "Velaslavasay Panorama",
        "neighborhood": "University Park",
        "address": "1122 W 24th St",
        "url": BASE + "/upcoming-events",
    },
]

ROW = re.compile(r'<div class="views-row[^"]*">(.*?)(?=<div class="views-row|\Z)', re.S)
TITLE = re.compile(r'views-field-title">.*?<a href="([^"]+)">(.*?)</a>', re.S)
SUBTITLE = re.compile(r'views-field-field-sub-title">\s*<div class="field-content">(.*?)</div>', re.S)
START = re.compile(r'views-field-field-date">.*?content="(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[-+]\d\d:\d\d)"', re.S)
BODY = re.compile(r'views-field-body">\s*<div class="field-content">(.*)', re.S)
IMG = re.compile(r'<img[^>]*?\ssrc="([^"]+)"')
FILM_HEAD = re.compile(r"\bscreenings?\b|\bfilms?\b|\bcinemas?\b|microcinema|\b(?:16|35|8)\s?mm\b|moving[- ]image", re.I)
FILM_BODY = re.compile(r"\bscreenings?\b|microcinema|\b(?:16|35|8)\s?mm (?:films?|prints?|screenings?)\b", re.I)
ELSEWHERE = re.compile(r"\*\*\s*At (?:the )?(?!Velaslavasay|Panorama)", re.I)


def _text(fragment):
    return clean(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment or "")))


def scrape(theater):
    out = []
    for row in ROW.findall(fetch(theater["url"])):
        title, start = TITLE.search(row), START.search(row)
        if not title or not start:
            continue
        name = _text(title.group(2))
        subtitle = SUBTITLE.search(row)
        sub = _text(subtitle.group(1)) if subtitle else ""
        body_html = BODY.search(row)
        body = _text(body_html.group(1)) if body_html else ""
        if ELSEWHERE.search(body):
            continue
        if not (FILM_HEAD.search(f"{name} {sub}") or FILM_BODY.search(body)):
            continue
        image = IMG.search(body_html.group(1)) if body_html else None
        url = BASE + title.group(1)
        out.append(screening(
            theater, name, start.group(1), url, film_url=url,
            blurb=blurb(f"{sub}. {body}" if sub else body),
            image=https_url(clean(image.group(1))) if image else None,
        ))
    return out
