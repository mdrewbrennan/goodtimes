"""Match screenings to The Movie Database (TMDB) for posters, ratings, trailers and genres.

Needs a TMDB key in the environment: TMDB_API_KEY (the v3 "API Key") or TMDB_TOKEN (the "API Read Access
Token"), both on themoviedb.org → Settings → API. Without one, enrich() does nothing and the site shows
text-only cards.

A wrong poster is worse than none, so a film only counts as matched when TMDB agrees on the title and on
either its director or its year. Results (misses included) are cached in data/tmdb.json, so a rerun only
asks TMDB about films it hasn't seen.

Standard library only. scrape.py calls enrich(); run python3 tmdb.py to re-match data/listings.json alone.
"""

import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parent
CACHE = ROOT / "data" / "tmdb.json"
API = "https://api.themoviedb.org/3"
POSTER = "https://image.tmdb.org/t/p/w342"
MIN_VOTES = 50  # below this, TMDB's score is too noisy to show


def norm(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"^(the|a|an) ", "", text.replace("&", "and"))
    return re.sub(r"[^a-z0-9]", "", text)


# What theaters add to a film's title: "in 35mm", "(2025)", "– Early Access Preview", "with Tommy Wiseau In Person"
NOISE = re.compile(r"\s*(\(\d{4}\)|\b(in|on) (35|16|70)mm\b|\b(35|16|70)mm\b|\b4k( restoration)?\b"
                   r"|\s+with\s+.+\bin person\b.*|\s+[-–—|]\s+.*$|\s+screening\s*(&|and)\s*q&a$)", re.I)


TITLE_YEAR = re.compile(r"\((\d{4})\)")


def core_title(title):
    """The film's own title, without the theater's additions."""
    core = re.sub(r"^.{0,40}?\bpresents?\s+", "", title)  # "AFTER presents THE CELL"
    core = NOISE.sub("", core).strip(" -–—:\"'“”")
    return core or title


def film_facts(s):
    """(title, year, director) to look up. A year in the title ("Body Snatchers (1993)") counts."""
    year = s.get("year") or (TITLE_YEAR.search(s["title"]) or [None, None])[1]
    return core_title(s["title"]), year, s.get("director")


def film_key(s):
    title, year, director = film_facts(s)
    return f'{norm(title)}|{year or ""}|{norm(director or "")}'


def _get(path, **params):
    token, key = os.environ.get("TMDB_TOKEN"), os.environ.get("TMDB_API_KEY")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        params["api_key"] = key
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as resp:
        return json.loads(resp.read())


def _directors(details):
    return {norm(c["name"]) for c in details.get("credits", {}).get("crew", []) if c.get("job") == "Director"}


def _trailer(details):
    videos = [v for v in details.get("videos", {}).get("results", [])
              if v.get("site") == "YouTube" and v.get("type") == "Trailer"]
    videos.sort(key=lambda v: (not v.get("official"), v.get("iso_639_1") != "en"))
    return f'https://www.youtube.com/watch?v={videos[0]["key"]}' if videos else None


def lookup(title, year, director):
    """The TMDB facts for one film, or None when no result is a confident match."""
    if not year and not director:
        return None  # a bare title (often a live event or a shorts program) is too easy to mismatch
    want, want_dir = norm(title), norm(director)
    params = {"query": title, "include_adult": "false"}
    if year and not director:
        params["year"] = year
    results = _get("/search/movie", **params).get("results", [])[:6]
    for r in results:
        if want not in (norm(r.get("title")), norm(r.get("original_title"))):
            continue
        r_year = (r.get("release_date") or "")[:4]
        if year and r_year and abs(int(r_year) - int(year)) > 1 and not director:
            continue
        details = _get(f'/movie/{r["id"]}', append_to_response="credits,videos")
        dirs = _directors(details)
        if director and not any(d and (d in want_dir or want_dir in d) for d in dirs):
            continue
        votes = details.get("vote_count") or 0
        return {
            "id": details["id"],
            "url": f'https://www.themoviedb.org/movie/{details["id"]}',
            "poster": POSTER + details["poster_path"] if details.get("poster_path") else None,
            "rating": round(details["vote_average"], 1) if votes >= MIN_VOTES and details.get("vote_average") else None,
            "trailer": _trailer(details),
            "genres": [g["name"] for g in details.get("genres", [])],
            "year": (details.get("release_date") or "")[:4] or None,
            "title": details.get("title"),
        }
    return None


def enrich(screenings):
    """Adds a "tmdb" dict (or None) to each screening. Never raises: TMDB trouble just means no posters."""
    if not (os.environ.get("TMDB_TOKEN") or os.environ.get("TMDB_API_KEY")):
        print("TMDB: no TMDB_API_KEY or TMDB_TOKEN set; skipping posters")
        return
    try:
        cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    except json.JSONDecodeError:
        cache = {}
    films = {}
    for s in screenings:
        if not s.get("special_event"):
            films.setdefault(film_key(s), film_facts(s))
    todo = [k for k in films if k not in cache]

    def one(key):
        try:
            return key, lookup(*films[key])
        except Exception as e:  # leave it out of the cache so the next run tries again
            print(f"TMDB: {films[key][0]}: {e}", file=sys.stderr)
            return key, "error"

    with ThreadPoolExecutor(max_workers=8) as pool:
        for key, found in pool.map(one, todo):
            if found != "error":
                cache[key] = found
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True))
    for s in screenings:
        s["tmdb"] = None if s.get("special_event") else cache.get(film_key(s))
    matched = sum(1 for k in films if cache.get(k))
    print(f"TMDB: matched {matched} of {len(films)} films ({len(todo)} looked up)")


if __name__ == "__main__":
    path = ROOT / "data" / "listings.json"
    data = json.loads(path.read_text())
    enrich(data["screenings"])
    path.write_text(json.dumps(data, indent=2))
