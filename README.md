# GOODTIMES

To Live and Watch Movies in LA: today's showings and upcoming special events from Los Angeles
independent and repertory cinemas, gathered from each theater's own website.

## Run it

Needs Python 3.9 or newer. There's nothing to install.

```sh
./run.sh            # scrape every theater, build the pages, serve them at localhost:8765
```

Or step by step:

```sh
python3 scrape.py   # writes data/listings.json
python3 build.py    # writes site/ (local preview) and netlify/ (folder to deploy)
python3 -m http.server 8765 -d site   # the pages use site-root links, so serve them rather than open the files
```

## How it's organized

- `scrapers/`: one module per theater or ticketing platform. Each exposes `THEATERS` and `scrape(theater)`.
- `scrape.py`: runs every scraper, removes duplicates, and writes `data/listings.json`.
- `build.py`, `style.css`: turn the data into the homepage, the listings page and the 404 page, plus the
  search-engine files: canonical links and link-preview tags, `robots.txt`, `sitemap.xml`, the web app
  manifest and Netlify's `_redirects` and `_headers`.
- `logo/`: the GOODTIMES wordmark and tab icon (`build_goodtimes.py` redraws the wordmark). The PNG icons and
  the link-preview card (`og-image.png`) are drawn from them by `render_images.sh`; rerun it after changing them.
- `fonts/`: Inter, served from the site itself (SIL Open Font License, in `fonts/OFL.txt`).
- `indexnow.py`: tells Bing and the search engines that share its index which pages changed.
- `picks.md`: the weekly "Worth leaving the house for" picks, written by hand (see below).
- `tmdb.py`: matches each film to The Movie Database for its poster, score, trailer and genres (see below).

Besides the homepage and listings, the build writes an About page (`/about/`), a page per festival
(`/festivals/<name>/`), a page per film per day for share links (`/e/<id>/`), an `.ics` file per screening
(`/cal/s/<id>.ics`) and calendar feeds people can subscribe to: one per theater (`/cal/<theater>.ics`) and one
for every special event (`/cal/special-events.ics`). Theater areas and map coordinates (for the theater menu
and "Near me") are in `GEO` in `build.py`; add a new theater there too.

`data/`, `site/` and `netlify/` are generated on every run, so they aren't stored in Git.

## Posters (TMDB)

Posters, scores, trailers and extra genres come from TMDB and need a free key: make an account at
themoviedb.org, then Settings → API. Set it as `TMDB_API_KEY` (or the longer read access token as `TMDB_TOKEN`)
in your shell for local runs and in Netlify (Site configuration → Environment variables) for the daily build.
Without it the site still builds, with text-only cards. A film only gets a poster when TMDB agrees on its
title and on its director or year; `data/tmdb.json` caches the matches.

## Weekly picks

Write each week's picks in `picks.md`: a `## Week of November 9, 2026` heading, then one line per film, like
`- **The Black Cat** — why it's worth it.` The instructions are at the top of that file. Commit and push it, and
the next build shows the picks on the homepage and at `/picks/` for 7 days from that date. The build fills in
each film's dates, theaters, times and poster. With no current week, the section is hidden.

## Deploying

Publish the `netlify/` folder. For automatic builds, use `python3 scrape.py && python3 build.py` as the
build command and `netlify` as the publish directory.

While the site is a preview, `PREVIEW = True` in `build.py` asks search engines not to list it.

Canonical links, the sitemap and link previews use the site's address: Netlify's `URL` (the primary domain)
during its builds, or `SITE_URL` if it's set. Once a custom domain is primary, the build also redirects the
`netlify.app` address to it.

### Launch checklist

1. Make the custom domain primary in Netlify (Domain management).
2. Set `PREVIEW = False` in `build.py` and deploy.
3. Add the domain to Google Search Console and Bing Webmaster Tools, and submit `/sitemap.xml` to each.
4. Add a repository variable `SITE_URL` (Settings → Secrets and variables → Actions → Variables) so the
   daily refresh pings IndexNow.
5. Add the site's social profiles to `SAME_AS` in `build.py`.

## Daily refresh

`.github/workflows/daily-refresh.yml` asks Netlify to rebuild every day at 7:00 a.m. Los Angeles time,
including across daylight saving. It needs a repository secret named `NETLIFY_BUILD_HOOK` (Netlify →
Site configuration → Build & deploy → Build hooks). To test it, use **Actions → Daily refresh → Run workflow**.
With a `SITE_URL` repository variable set, it then waits for the new build to go live and runs `indexnow.py`.

If most theaters can't be reached, `scrape.py` exits with an error so the build fails and Netlify keeps
the last good version live.
