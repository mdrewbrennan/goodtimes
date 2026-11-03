"""Helpers shared by every theater scraper.

Every scraper module exposes:
  THEATERS: list of dicts with id, name, neighborhood, address, url (plus any keys the module needs)
  scrape(theater) -> list of screening dicts built with screening()
"""

import html
import json
import re
import urllib.request

USER_AGENT = "Mozilla/5.0 (compatible; LeftOnScene/0.1; proof of concept)"
LD_JSON = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
DURATION = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?")


def fetch(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_json(url, headers=None):
    return json.loads(fetch(url, {"Accept": "application/json", **(headers or {})}))


def json_ld_nodes(page):
    nodes = []
    for block in LD_JSON.findall(page):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            nodes.extend(data)
        elif "@graph" in data:
            nodes.extend(data["@graph"])
        else:
            nodes.append(data)
    return nodes


def clean(text):
    return html.unescape(text or "").strip()


def blurb(description):
    text = re.sub(r"<[^>]+>", " ", html.unescape(description or ""))
    return re.sub(r"\s+", " ", text).strip() or None


def runtime_minutes(duration):
    m = DURATION.fullmatch(duration or "")
    if not m or not any(m.groups()):
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


def screening(theater, title, start, ticket_url, *, film_url=None, year=None, director=None,
              runtime=None, genres=None, blurb=None, sold_out=False, cancelled=False, special_event=False):
    """One showing. start is an ISO 8601 string with the LA offset, e.g. 2026-11-03T19:30:00-08:00."""
    return {
        "theater": theater["id"],
        "special_event": special_event,  # live events, parties, etc. (not tied to one film)
        "title": clean(title),
        "start": start,
        "ticket_url": ticket_url,
        "film_url": film_url,
        "year": str(year)[:4] if year else None,
        "director": director or None,
        "runtime": runtime,
        "genres": genres or [],
        "blurb": blurb,
        "sold_out": sold_out,
        "cancelled": cancelled,
    }
