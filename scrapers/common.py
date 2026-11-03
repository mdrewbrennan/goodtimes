"""Helpers shared by every theater scraper.

Every scraper module exposes:
  THEATERS: list of dicts with id, name, neighborhood, address, url (plus any keys the module needs)
  scrape(theater) -> list of screening dicts built with screening()
"""

import html
import json
import re
import urllib.request

# Says who's asking, so a theater can see what the requests are for and how to reach us.
USER_AGENT = ("Mozilla/5.0 (compatible; GOODTIMES-LA/1.0; daily LA screening listings; "
              "+https://github.com/mdrewbrennan/goodtimes)")
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


META_TAG = re.compile(r'<meta\s[^>]*>', re.I)
META_ATTR = re.compile(r'([\w:-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')


def og_image(page_html, base=None):
    """og:image (else twitter:image) URL from a page's <meta> tags, as an absolute https URL, or None."""
    found = {}
    for tag in META_TAG.findall(page_html or ""):
        attrs = {k.lower(): html.unescape(a or b) for k, a, b in META_ATTR.findall(tag)}
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key in ("og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src"):
            found.setdefault(key.split(":")[0], attrs.get("content", "").strip())
    for key in ("og", "twitter"):
        url = found.get(key)
        if url:
            return https_url(url, base)
    return None


def https_url(url, base=None):
    """Absolute https URL, or None if it can't be made into one."""
    url = (url or "").strip()
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/") and base:
        url = base.rstrip("/") + url
    elif url.startswith("http://"):
        url = "https://" + url[7:]
    return url if url.startswith("https://") else None


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
              runtime=None, genres=None, blurb=None, sold_out=False, cancelled=False, special_event=False,
              image=None):
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
        "image": image,  # poster URL from the theater's own data (absolute https), a fallback for TMDB
    }
