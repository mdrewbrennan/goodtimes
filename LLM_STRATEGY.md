# GOODTIMES LLM strategy

Written Nov 8 2026 from a read of `build.py` and the built site. Sizes follow `BACKLOG.md`: S = an afternoon,
M = a few days, L = a week or more.

## The goal

More and more people ask a chatbot instead of a search box: "anything playing in 35mm in LA this weekend?",
"what's on at the New Beverly tonight?", "where can I see a Q&A with a director this week?". The **winning
outcome** is that ChatGPT, Claude, Perplexity, Gemini and Google's AI Mode answer those questions
**correctly, from GOODTIMES, with a link back**, and that an AI agent planning someone's night can read the
listings and go straight to the theater's ticket page.

Revival Hub has more venues, but answer engines don't reward the biggest directory. They reward the source
that is easiest to read, fresh, consistent and trusted. One person with a good build script can win that.

The strategy rests on four pillars, in priority order:

1. **Be readable.** Every fact an AI tool needs is easy to pull out in one or two fetches.
2. **Be trusted.** GOODTIMES is a known entity that other sites mention and the web agrees on.
3. **Be usable by agents.** Tools can query the listings directly, not only scrape pages.
4. **Use LLMs inside the build**, only where they make the data better and never as the source of a time
   or a place.

## Where it stands

The foundations are already better than most sites:

- `/llms.txt` maps the site, and `/listings.json` has every upcoming screening, open to any origin (CORS).
- Every listing page marks up its screenings as schema.org `ScreeningEvent`, with `MovieTheater`, `Movie`,
  `Offer` and breadcrumbs.
- `robots.txt` lets every crawler in, AI crawlers included. IndexNow pings Bing, and Bing's index feeds
  ChatGPT search and Copilot.
- The pages are static HTML, so the content is in the page without running JavaScript.
- Page titles and descriptions are written for search: the uncommitted `film_search_text` change in
  `build.py` leads with when and where.

## What's holding it back

Most important first:

1. **The site says different things about how often it updates.** The build runs at 7am and 3pm, but the
   About page ([build.py:1777](build.py:1777)), theater pages ([build.py:1307](build.py:1307)) and area
   pages ([build.py:1431](build.py:1431), [build.py:1471](build.py:1471)) say "every morning". When the
   sources disagree, a model either picks one at random or treats the site as less reliable.
   **Fix:** one `UPDATE_SCHEDULE` constant, used everywhere.
2. **Every page starts with decoration.** The marquee ("35mm & 70mm ✳ Repertory classics ✳ … Freaky sexy
   cool man", twice over) comes before the `<h1>` in the page text. `aria-hidden` hides it from screen
   readers, but most text extractors used by AI crawlers ignore that, so the first thing a model reads on
   every page is a list of slogans. **Fix:** draw the marquee from a CSS `content:` or data attribute,
   or move it after `<main>` in the HTML and position it with CSS.
3. **The weekend title breaks on Sundays.** The current `/this-weekend/` title reads "Nov 8–8", and it
   shows up in `llms.txt` and search results. **Fix:** say "Sunday, Nov 8" when the range is one day.
4. **GOODTIMES is barely an entity yet.** `SAME_AS` is empty, the About page doesn't name the person
   behind the site in structured data, and few other sites link here. Models trust what other places
   confirm. **Fix:** see "Be trusted" below.
5. **Answering a question takes many fetches.** `llms.txt` is a list of links, so a model answering "what's
   on this weekend?" has to follow several of them. Many AI tools fetch one or two URLs and then answer.
   **Fix:** `llms-full.txt` (below).
6. **The 655 film pages have no index.** They're reachable only from listing rows, and `llms.txt` gives
   the URL pattern but no list. **Fix:** a `/films/` page of what's screening, A to Z.

## Pillar 1: Be readable

- **`llms-full.txt`** (S). The next 7 days as plain text, grouped by day and then by theater: title, year,
  director, time, format, guests and ticket link, one line per screening. Put an `Updated:` timestamp in the
  first line. This single URL is the biggest lever on the list: a model that fetches it can answer almost
  any "what's playing" question correctly. Link it from `llms.txt` and give it the same headers.
- **Tell models how to read the data** (S). Add a short "Using this data" section to `llms.txt`: times are
  Pacific, listings change, link to the screening page or ticket URL instead of repeating a time without
  its source, and the date of the last update.
- **A Markdown copy of each key page** (S). Following the llms.txt convention, publish `index.md` next to
  `index.html` for the homepage, collections, theaters and this weekend, generated from the same data.
  It's cheap, since the build already has everything.
- **Answer the questions people ask, in a sentence** (S). Each collection and theater page already has an
  intro line ("56 screenings at New Beverly Cinema in the next 30 days, including 3 on film"). Make the
  first sentence on each page a direct answer people would quote: "This weekend, 14 LA theaters are
  showing 9 films on 35mm, including *Destiny* at the New Beverly on Sunday at 7:30pm." Models lift
  passages like that almost word for word.
- **Freshness everywhere** (S). Add `dateModified` to each page's JSON-LD and a visible "Updated
  <time>" on every listing page, not only the homepage. Make the sitemap's `lastmod` change only when a
  page's listings actually change, so crawlers trust it.
- **Fill in the structured data** (S). Add `organizer` for series and festivals, `performer` for named
  guests, `inLanguage` and `subtitleLanguage` when the theater says so, and `isAccessibleForFree` for free
  screenings. Check a sample with Google's Rich Results Test after each change.
- **A films index** (S). `/films/`: everything with an upcoming screening, A to Z, with its next date.
  Add it to the sitemap and `llms.txt`.

## Pillar 2: Be trusted

AI answers lean heavily on what other sites say: Reddit, local press, Letterboxd, Wikipedia and Bing's
index. Technical work alone won't get GOODTIMES cited.

- **Finish the launch checklist** (S). Custom domain, Bing Webmaster Tools and Google Search Console, the
  `SITE_URL` variable for IndexNow. **Bing matters most**, since ChatGPT and Copilot search run on it.
- **Make the entity solid** (S). Fill `SAME_AS` (Instagram, a Letterboxd account, Bluesky). Add `AboutPage`
  and a `Person` for the founder on the About page, with the same name and handle as the Instagram bio.
  Use the same one-line description ("To Live and Watch Movies in LA: what's playing at LA's indie and
  repertory theaters") everywhere the site appears.
- **Get mentioned where models look** (M, ongoing).
  - Reddit: answer "where to see repertory film in LA" threads on r/LosAngeles, r/LAlist and r/TrueFilm,
    as a person and not with a pitch. These threads come up in AI answers all the time.
  - Letterboxd: a GOODTIMES account and lists ("Screening on 35mm in LA this month") that link back.
  - Local press and newsletters: LAist, LA Taco, Air Mail LA, the Movies-in-LA Substacks. The weekly picks
    are the hook, since they're the one thing Revival Hub doesn't do.
  - Theaters and micro-cinemas: ask the small ones (Whammy, Veggie Cloud, Now Instant, PRS) to link to
    their GOODTIMES page as "full schedule".
- **The picks are the moat; keep them human** (ongoing). Models can copy a list of times from anywhere.
  "Worth leaving the house for", in a real person's voice, is what makes a model name GOODTIMES as the
  source of a recommendation. Mark each pick up as a `Review` or `Recommendation` of the screening, with
  an author.

## Pillar 3: Be usable by agents

- **Describe the data** (S). Publish `/openapi.json` (or a JSON Schema) for `listings.json` and add a
  `version` field, so a tool builder or an agent can rely on its shape. Keep field names stable from here
  on.
- **Smaller files** (S). `/listings/today.json` and `/dates/YYYY-MM-DD.json`, so an agent asking about one
  day doesn't download the whole week.
- **A read-only MCP server** (M, after the launch checklist). A small Netlify Function with three
  tools: `whats_playing(date, area?, format?)`, `theater_schedule(theater)` and `find_film(title)`, all
  reading the built JSON. Then people can add GOODTIMES as a connector in Claude or ChatGPT and ask in
  plain English. List it in the MCP registry. Build it only once Pillars 1 and 2 are done; it reaches the
  people who opt in, while Pillar 1 reaches everyone.
- **Leave the rest of the agent work to the theaters' own pages** (no work). Every screening already links
  straight to its ticket URL, which is what an agent booking a night out needs. Don't build ticketing.

## Pillar 4: LLMs inside the build

The rule: **the scrape is the source of truth for titles, times and places. A model may label, sort or
summarize, never invent.** Every model output is checked against the source text before it's used, and
cached by a hash of its input so the daily build costs close to nothing. Use the smallest model that does
the job (Claude Haiku), with a clear fallback when there's no API key, the way TMDB works now.

- **Pull details out of blurbs** (M). Today guests, festivals, formats and double bills come from regexes.
  When a regex finds nothing in a blurb that probably has something (it mentions "in person", "Q&A",
  "print", "festival"), ask the model for structured fields, and keep each one only if its words appear
  in the blurb. Done when most "Guests in person" cards name someone and no card names someone the blurb
  doesn't.
- **Clean up titles before matching TMDB** (S). Theaters write "SUSPIRIA (1977) – 35MM – w/ Q&A". Have
  the model split it into title, year and extras when the existing cleanup can't, so more films get a
  poster and the right film page.
- **Catch broken scrapers** (S, outside the build). When a theater's count drops to zero or swings hard
  from yesterday's, have the GitHub Action open an issue with the page's HTML attached, ready for a
  Claude Code session to fix the scraper. The model diagnoses; you merge.
- **Help with the picks, don't write them** (S). A weekly shortlist of the 15 rarest screenings (35mm,
  one night only, a guest, not shown in LA in a year, from the archive) to choose from. The sentences
  stay yours.
- **No chatbot on the site** (parked). Once Pillars 1 and 3 are done, ChatGPT and Claude become the
  chatbot, for free. A site chatbot costs money, can get times wrong in GOODTIMES' name, and adds
  nothing the listings page doesn't.

## Measuring it

- **A monthly question panel** (S to set up, 30 minutes a month). Twenty fixed questions ("35mm in LA this
  weekend", "what's on at Vidiots tonight", "best repertory theaters in LA", "where to see Q&As in LA"),
  each asked in ChatGPT, Claude, Perplexity and Google AI Mode. Record, per question: does it mention
  GOODTIMES, link to it, and get the facts right? Keep it in a sheet and watch the trend.
- **AI referrals.** Count visits from chatgpt.com, perplexity.ai, claude.ai, gemini.google.com and
  copilot.microsoft.com (ChatGPT also adds `utm_source=chatgpt.com`). Netlify Analytics or Plausible will
  show them.
- **Crawler visits.** From Netlify's logs, count hits by OAI-SearchBot, ChatGPT-User, PerplexityBot,
  Claude-SearchBot, Claude-User and Googlebot to `llms.txt`, `llms-full.txt` and `listings.json`. Fetches
  by the "-User" bots are real people asking about LA movies right now.
- **Quarter-one target:** GOODTIMES cited in at least 5 of the 20 panel questions in at least two of the
  four tools, with no wrong times.

## Order of work

**This week** (all S, mostly `build.py`; ✅ built Nov 8 except `SAME_AS`, which waits on the site's own profiles): the update-schedule wording, the marquee, the Sunday title,
`llms-full.txt`, the "Using this data" section, `dateModified`, `SAME_AS` and the founder's `Person`, the
`/films/` index. Then the launch checklist.

**This month:** Markdown copies of key pages, answer-first intro sentences, the extra structured-data fields,
`openapi.json` and per-day JSON, the question panel and referral tracking, plus starting on Reddit,
Letterboxd and outreach to the small venues.

**Next quarter:** picking details out of blurbs with a model, title cleanup, scraper alerts, the picks
shortlist, then the MCP server.

## One decision for you

**Should AI companies' training crawlers be let in, or only their search crawlers?** Right now every bot
is allowed. This plan recommends keeping it that way: the listings are facts that go stale in a week, and
being part of what models already know about LA cinema ("GOODTIMES is where to look") helps them suggest
the site. The cost is that your picks' writing could end up in training data. If that matters more, block
GPTBot, ClaudeBot, Google-Extended, CCBot and Applebot-Extended by name and keep OAI-SearchBot,
Claude-SearchBot, PerplexityBot and the "-User" fetchers. Note: each bot that gets its own group needs
its own `Allow` and `Disallow` lines (see the comment in `robots_txt()`).
