# GOODTIMES backlog

Built from the #so-good feedback thread (Tim, Brannon, Alaina, Nov 3 2026) and a look through
revivalhub.com the same day. Each item says who asked for it, roughly how big it is (S = an afternoon,
M = a few days, L = a week or more) and what "done" looks like.

**Goals this list assumes** (correct these and the order changes): GOODTIMES should be the LA listing a
film buff *chooses* over Revival Hub, grow mostly through people sharing it and through search, and stay
something one person can run on a daily scrape.

## Where we stand against Revival Hub

Revival Hub has been running since 2017 and has a team (founder, lead developer, social media manager).
It is far ahead on breadth:

- About 83 venues, including museums (Academy Museum, Hammer, Getty), rooftops, USC/CSUN, the Laemmle
  chain and chain anniversary screenings. GOODTIMES scrapes 20. Nearly every small venue GOODTIMES has
  (Whammy, PRS, 2220 Arts, Now Instant, Lumiere) is already on Revival Hub; Muscle Distribution is the
  one exception seen.
- A page per film (TMDB poster, cast and crew, trailer, "more like this", IMDb and Letterboxd links),
  per venue and per presenting organization.
- Filters by genre, venue, organization, format, category and indoor/outdoor; distance from your
  location; full or condensed view; a month calendar; a newsletter.
- Event notes that name the guests ("Q&A with writer-director James Gray").

Where it is weak, which is where GOODTIMES can win:

- It looks like a generic dark database, with a large Patreon banner on top and a location prompt.
  Nothing on it has taste or a voice.
- No add-to-calendar or share button was visible on the listings or film pages.
- It lists everything with equal weight, so it never tells you what is worth leaving the house for.

**The takeaway:** GOODTIMES will not beat Revival Hub on coverage, so it shouldn't try to match it
venue for venue. Match the basics people would miss on switching over (posters, guest names, genre,
neighborhood), then win on point of view, design and how easy it is to make plans with friends.

## Now: the basics

1. **Posters from TMDB** ✅ built Nov 3 (M). Brannon: posters "go super far" at breaking up the wall of text. Match
   each screening to TMDB by title, year and director during the build, cache the results in the repo
   so the daily build doesn't hit TMDB for every film, and show a text-only card when nothing matches.
   Credit TMDB in the footer as their terms require. *Done when* most screenings on a normal day show
   the right poster and no wrong ones.

2. **Name the guests** ✅ built Nov 3 (S–M). Alaina: for "Guests in person", say who, and say when there's a live
   Q&A. The theaters' blurbs usually already say it; pull the sentence that names them ("Q&A with
   writer-director James Gray") onto the card. *Done when* most Guests in person cards name someone.

3. **Add to calendar** ✅ built Nov 3 (S). Alaina. One `.ics` file per screening (title, theater address, start time,
   runtime, ticket link), built with the static site. Revival Hub doesn't seem to have this.

4. **Share** ✅ built Nov 3 (S). Alaina. A link to each screening (an anchor or a small page of its own) and a share
   button that opens the phone's share sheet, falling back to copy-link. The shared link should get a
   proper preview card. This is the main way the site spreads.

## Next: catch up on exploring

5. **Visual identity pass** (M). Tim and Brannon both said it reads as vibe-coded, and LA film buffs
   will notice. Commit to a direction: use the green as a surface (deep-green sections, header or a
   dark mode) rather than only as text color, set a real type scale and layout, and add a hero at the
   top of the homepage. Waiting on a designer. *Done when* someone seeing a screenshot couldn't mistake it for a template.
   The posters are already in, so the designer can lay the cards out around them.
6. **Each special event type gets its own look** (S). Alaina: give each category a color, icon or type
   treatment so Festival, Guests in person, Live score and 35mm read at a glance. Part of the designer's
   visual identity work.
7. **Genre filter** ✅ built Nov 3 (S). Alaina. Most scrapers already collect genres; add a genre menu next to the
   theater picker and fill gaps from TMDB once item 1 lands.
8. **Group or filter by neighborhood** ✅ built Nov 3 (S). Tim. Every theater already has a neighborhood; let people
   pick "Eastside / Westside / Valley…" or sort venues by neighborhood.
9. **Closest to me** ✅ built Nov 3 (M). Tim. Store each theater's coordinates and sort by distance using the
   browser's location, only when the person taps it. No location prompt on load (that's one of the
   annoying things about Revival Hub).
10. **Search on the homepage too** ✅ built Nov 3 (S). Tim asked for text search; the listings page has it, the
    homepage doesn't, so it's easy to miss. Put the search box (or a clear link to it) on the homepage.
11. **Trailers** ✅ built Nov 3 (S, after item 1). Alaina. TMDB returns trailer links for most films; add a "Trailer"
    link on the card.
12. **About page** ✅ built Nov 3 (S). Brannon: give the human element a place to live. Who runs it, why, how the
    listings are gathered, how to suggest a theater. Also helps the site look legitimate to search
    engines.
13. **Festival pages** ✅ built Nov 3 (M). Alaina: the Festival tag should link to the full lineup. Group screenings
    tagged Festival by festival name and theater into a page per festival.
14. **More venues, picked by where the special events are** (L, ongoing). Not about matching Revival
    Hub's count. Add the venues that carry the most events cinephiles care about: Academy Museum,
    USC Cinematic Arts, Hammer Museum, Alex Theatre, Fine Arts,
    Laemmle's other houses. One scraper at a time, each with the same failure checks as the existing ones.

## Later: what makes it ours

15. **"Worth leaving the house for" picks** (M). ✅ Homepage section and /picks/ page built Nov 3; waiting on the first week's picks. Newsletter still to do. A short weekly list with a sentence of why for each
    pick, on the homepage and as a newsletter. This is the thing Revival Hub structurally can't do, and
    it's the clearest answer to "how is this different."
16. **Letterboxd watchlist match** ✅ built Nov 3 (M). Alaina suggested Letterboxd; their API is hard to get (Brannon
    was rejected, still worth applying). Without the API, people can export their watchlist CSV from
    Letterboxd and drop it on the page; the browser matches it against upcoming screenings and nothing
    is uploaded. "4 films from your watchlist are screening this week" is a strong reason to come back.
17. **Calendar feeds** ✅ built Nov 3 (S–M). Subscribe-able `.ics` feeds per theater and for all special events, so
    new screenings appear in someone's calendar app on their own.
18. **Ratings** ✅ built Nov 3 (S). Alaina mentioned Rotten Tomatoes. RT has no open API and is a less natural fit
    for this audience; use the TMDB score or link to Letterboxd instead.
19. **Month calendar view** (M). Alaina mentioned Revival Hub's calendar and then saw GOODTIMES' day
    strip already covers much of it. Only build a month grid if people ask for it after the above.

## Parked

- **NYC version.** Tim would use it. Not until LA is clearly better than Revival Hub; then the scraper
  setup carries over city by city.
- **Copying every Revival Hub feature.** Brannon's point that people expect what competitors offer is
  why the Now and Next lists exist. Past those, venue and organization directories, indoor/outdoor and
  condensed view stay parked unless people ask.

## How this list was checked

The first draft followed the thread's order and put parity first. Checking it against the goals above
changed four things:

- **Design moved to the top**, since two of the three people opened with how the site looks. It then
  moved to Next on Nov 3: there is no visual identity yet and it needs a designer.
- **Coverage moved down and was narrowed.** Revival Hub has four times the venues and a team; chasing
  that count is a losing race for one person. Only the venues with the most special events stay in.
- **Rotten Tomatoes and the month calendar went to Later**, because there is no RT API and the day strip
  already does most of what a calendar does.
- **Letterboxd went from "apply for the API" to the CSV import**, which works today without anyone's
  permission.

Separate thread, not repeated here: Maggie's "how do I make it SEO-friendly?" with Brannon. The README's
launch checklist (custom domain, `PREVIEW = False`, Search Console) covers the technical side; posters,
an About page and festival pages also help.
