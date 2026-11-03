# GOODTIMES

To Live and Watch Movies in LA: today's showings and upcoming special events from Los Angeles
independent and repertory cinemas, gathered from each theater's own website.

## Run it

Needs Python 3.9 or newer. There's nothing to install.

```sh
./run.sh            # scrape every theater, build the pages, open the homepage
```

Or step by step:

```sh
python3 scrape.py   # writes data/listings.json
python3 build.py    # writes site/ (local preview) and netlify/ (folder to deploy)
```

## How it's organized

- `scrapers/`: one module per theater or ticketing platform. Each exposes `THEATERS` and `scrape(theater)`.
- `scrape.py`: runs every scraper, removes duplicates, and writes `data/listings.json`.
- `build.py`, `style.css`: turn the data into the homepage and the listings page.
- `logo/`: the GOODTIMES wordmark and tab icon (`build_goodtimes.py` redraws the wordmark).

`data/`, `site/` and `netlify/` are generated on every run, so they aren't stored in Git.

## Deploying

Publish the `netlify/` folder. For automatic builds, use `python3 scrape.py && python3 build.py` as the
build command and `netlify` as the publish directory.

While the site is a preview, `PREVIEW = True` in `build.py` asks search engines not to list it.
