"""WHAMMY! Analog Media (Echo Park VHS store + microcinema, 1200 N Alvarado St).

whammyanalog.com is a Webflow site. /whammy-events is a server-rendered collection list of event cards
(day, date like "11/2", time, title, sold-out flags) and every card links to an /events/<slug> page with
the description. Tickets are sold through an embedded Shopify buy button (needs a storefront token in
page JS, which we don't touch), so ticket_url is the event page itself.

Non-screening events (workshops, residencies, live podcasts) are dropped. The monthly TALKIES live
comedy + shorts night is kept as a special_event.
"""

import re
from datetime import date, datetime

from .common import clean, fetch, og_image, screening
from .la_offset import la_iso

BASE = "https://www.whammyanalog.com"

THEATERS = [
    {
        "id": "whammy",
        "name": "Whammy! Analog Media",
        "neighborhood": "Echo Park",
        "address": "1200 N Alvarado St, Unit D",
        "url": BASE + "/",
        "events_url": BASE + "/whammy-events",
    },
]

CARD = re.compile(r'<a href="(/events/[^"]+)" class="eventcardlink.*?</a>', re.S)
NOT_FILM = re.compile(r"workshop|petting zoo|digital preservation|podcast|residency|video processing", re.I)
LIVE = re.compile(r"live comedy|live score|\blive\b", re.I)


def field(block, cls):
    m = re.search(r'class="%s[^"]*">(.*?)</' % cls, block, re.S)
    return clean(re.sub(r"<[^>]+>", "", m.group(1))) if m else ""


def card_date(label, today):
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", label.strip())
    if not m:
        return None  # ranges like "3-30" are residencies, not showtimes
    month, day = int(m.group(1)), int(m.group(2))
    d = date(today.year, month, day)
    return d if (today - d).days < 60 else date(today.year + 1, month, day)


def card_time(label):
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([AP]M)", label.strip().upper())
    if not m:
        return None
    return datetime.strptime(f"{m.group(1)}:{m.group(2) or '00'}{m.group(3)}", "%I:%M%p").time()


def description(page):
    """Paragraph texts of the event page body (the first rich-text block)."""
    body = page[page.find("<body"):]
    m = re.search(r'<div class="rtf w-richtext">(.*?)(?=<div class="shopifybuttoncontainer|<div class="w-embed|</div></div>)', body, re.S)
    if not m:
        return []
    chunks = re.split(r"</p>|<br\s*/?>|</h\d>|</li>", m.group(1))
    paras = [re.sub(r"\s+", " ", clean(re.sub(r"<[^>]+>", " ", c)).replace("‍", " ")).strip() for c in chunks]
    return [p for p in paras if p]


def scrape(theater):
    today = date.today()
    listing = fetch(theater["events_url"])
    out = []
    for m in CARD.finditer(listing):
        card, href = m.group(0), m.group(1)
        raw_title = field(card, "calendareventtitle")
        day = card_date(field(card, "date"), today)
        time = card_time(field(card, "calendar-time"))
        if not raw_title or not day or not time or day < today:
            continue
        if NOT_FILM.search(raw_title):
            continue

        url = BASE + href
        event_page = fetch(url)
        paras = description(event_page)
        text = " ".join(paras)
        if re.search(r"\bworkshop\b", text[:500], re.I):
            continue

        sold_out = bool(re.search(r"\*\s*sold out\s*\*", raw_title, re.I)) or "presale-closed" in card and "sold out" in text.lower()
        title = re.sub(r"^\s*\*\s*sold out\s*\*\s*", "", raw_title, flags=re.I)
        title = re.sub(r",?\s*pres\. by .*$", "", title).strip()

        year = re.search(r"\((\d{4})(?:-\d+)?\)", title)
        director = re.search(r"[Dd]ir(?:ected by|\.)\s+([A-Z][\w'’.\- ]+?)(?:,|\.|;| \d{4}|\s+and\s|$)", text)
        runtimes = re.findall(r"(\d{2,3})\s*min", text)
        total = re.search(r"Total (?:Program|Running Time)[: ]+(\d+)\s*min", text, re.I)
        runtime = int(total.group(1)) if total else (int(runtimes[0]) if len(runtimes) == 1 else None)
        blurb_paras = [p for p in paras if not re.search(r"sold out|stand-by|pre-sale", p, re.I)]
        blurb = " ".join(blurb_paras[:2])[:500] or None
        film_url = None if LIVE.search(title) else url

        out.append(screening(
            theater, title, la_iso(datetime.combine(day, time)), url,
            film_url=film_url, year=year.group(1) if year else None,
            director=director.group(1).strip() if director else None,
            runtime=runtime, blurb=blurb, sold_out=sold_out,
            special_event=bool(LIVE.search(title)),
            image=og_image(event_page)))
    return out
