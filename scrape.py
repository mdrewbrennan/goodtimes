"""Fetch upcoming screenings from every theater and write data/listings.json.

Each platform has its own module in scrapers/. Add a theater by adding its module to MODULES.

Standard library only: python3 scrape.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import tmdb
from scrapers import (academy, alamo, alex, arts2220, cinemasaloon, cinematheque, filmbot, finearts, gardena,
                      hammer, laemmle, landmark, lumiere, muscle, newbev, nowinstant, prs, usc, veggiecloud,
                      vista, whammy)

# A theater with "specials_only": True (Alamo) is scraped in full, but the site shows only its special
# screenings. Remove that flag in its scraper module to show everything it plays.
MODULES = [filmbot, cinematheque, newbev, vista, laemmle, lumiere, landmark, alamo, gardena, nowinstant,
           whammy, prs, arts2220, muscle, academy, usc, hammer, alex, finearts,
           veggiecloud, cinemasaloon]

# Series that screen at other theaters. Their listings are dropped when the host theater already
# lists the same film on the same day.
SERIES = {"muscle"}


def norm(title):
    return "".join(c for c in title.lower() if c.isalnum())


def dedupe(screenings, partial):
    seen, out = set(), []
    # A host theater that only shows its specials may hide the film, so there only its specials count.
    hosted = {(norm(s["title"]), s["start"][:10]) for s in screenings
              if s["theater"] not in SERIES and (s["theater"] not in partial or s["special_event"])}
    for s in screenings:
        key = (s["theater"], norm(s["title"]), s["start"])
        if key in seen or (s["theater"] in SERIES and (norm(s["title"]), s["start"][:10]) in hosted):
            continue
        seen.add(key)
        out.append(s)
    return out


def main():
    theaters, screenings, errors = [], [], []
    for module in MODULES:
        for theater in module.THEATERS:
            try:
                found = module.scrape(theater)
                print(f"{theater['name']}: {len(found)} screenings")
                screenings.extend(found)
                theaters.append(theater)
            except Exception as e:  # one broken theater shouldn't take down the site
                errors.append(theater["id"])
                print(f"{theater['name']}: FAILED ({e})", file=sys.stderr)

    # If most theaters failed (say, the build server lost its connection), stop with an error instead of
    # publishing a nearly empty site. A failed Netlify build leaves the last good version live.
    total = len(theaters) + len(errors)
    if not screenings or len(errors) > total // 2:
        sys.exit(f"Only {len(theaters)} of {total} theaters scraped; not publishing this update.")

    screenings = dedupe(screenings, {t["id"] for t in theaters if t.get("specials_only")})
    screenings.sort(key=lambda s: (s["start"], s["theater"], s["title"]))
    tmdb.enrich(screenings)  # posters, ratings, trailers and genres, when a TMDB key is set
    out = Path(__file__).parent / "data" / "listings.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "theaters": [{**{k: theater[k] for k in ("id", "name", "neighborhood", "address", "url")},
                      "operator": theater.get("operator"),  # e.g. "Landmark", shown under the name
                      "specials_only": theater.get("specials_only", False)} for theater in theaters],
        "screenings": screenings,
        "errors": errors,
    }, indent=2))
    print(f"Wrote {len(screenings)} screenings to {out}")


if __name__ == "__main__":
    main()
