"""The film archive: every film GOODTIMES has listed, kept from one build to the next.

Each build's listings are thrown away, so this is what lets a film's page stay up after its last screening
("Last screened at New Beverly Cinema on Oct 2") instead of disappearing and breaking links to it. The copy
that counts is the one on the live site, /archive.json: a production build on Netlify downloads it, adds
today's screenings and publishes the new one. Local builds use data/archive.json instead.

Standard library only. build.py calls load(), record() and dump().
"""

import json
import os
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
LOCAL = ROOT / "data" / "archive.json"
KEEP_DAYS = 365   # a film nobody has screened for this long drops out (its page goes with it)
HISTORY = 40      # past screening dates kept per film


def load(site_url):
    """The archive so far: {"films": {key: film}}.

    On a Netlify production build a failed download stops the build, so Netlify keeps the last good version
    of the site, history included, instead of publishing one that has forgotten every past film."""
    if os.environ.get("CONTEXT") == "production" and site_url.startswith("https://"):
        url = f"{site_url}/archive.json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GOODTIMES-LA build", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print("archive: none published yet; starting a new one")
                return {"films": {}}
            raise SystemExit(f"archive: couldn't download {url} ({e}); not publishing this build.")
        except Exception as e:  # network trouble, or a damaged file
            raise SystemExit(f"archive: couldn't read {url} ({e}); not publishing this build.")
    return json.loads(LOCAL.read_text()) if LOCAL.exists() else {"films": {}}


def record(archive, films, today, slug_for):
    """Add this build's films. films: {key: {"title", "year", "director", "runtime", "genres", "poster", "tmdb",
    "title_key", "shown": [(date, theater id)]}}. A film first seen without a TMDB match and later matched is
    merged into its TMDB entry. slug_for(film) makes the page address for a new film."""
    known = archive["films"]
    slugs = {f["slug"] for f in known.values()}
    for key, film in films.items():
        old = known.get(key)
        if old is None and key != film["title_key"] and film["title_key"] in known:
            old = known.pop(film["title_key"])  # the same film, now matched to TMDB: keep its page and history
        if old is None:
            base = slug = slug_for(film)
            n = 2
            while slug in slugs:
                slug, n = f"{base}-{n}", n + 1
            slugs.add(slug)
            old = {"slug": slug, "first_seen": today.isoformat(), "shown": []}
        shown = {tuple(x) for x in old["shown"]} | {(d.isoformat(), t) for d, t in film["shown"] if d <= today}
        known[key] = {**old, **{k: v for k, v in film.items() if k not in ("shown", "title_key") and v},
                      "shown": sorted(shown)[-HISTORY:], "last_listed": today.isoformat()}
    cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
    for key in [k for k, f in known.items() if f["last_listed"] < cutoff]:
        del known[key]
    return archive


def last_shown(film, today):
    """(date, theater id) of the latest screening on or before today, or None."""
    past = [(date.fromisoformat(d), t) for d, t in film["shown"] if d <= today.isoformat()]
    return max(past) if past else None


def dump(archive):
    text = json.dumps(archive, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    LOCAL.parent.mkdir(exist_ok=True)
    LOCAL.write_text(text)
    return text
