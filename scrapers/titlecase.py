"""Shared helper: tidy ALL-CAPS film titles from ticketing systems (USC, Fine Arts). Not a scraper module."""

import re

SMALL = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}
ROMAN = re.compile(r"[IVXLC]+")


def smart_case(title):
    """Title-case the words that are in all caps ("THE BOYS NEXT DOOR" -> "The Boys Next Door").

    Words already in mixed case, Roman numerals (II, XX) and single letters (except a mid-title A) are left alone.
    """
    words = title.split(" ")
    out = []
    for i, word in enumerate(words):
        core = re.sub(r"[^A-Za-z']", "", word)
        if len(core) > 1 and core.isupper() and not ROMAN.fullmatch(core):
            word = re.sub(r"[A-Za-z][A-Za-z']*", lambda m: m.group(0).capitalize(), word)
            if i and core.lower() in SMALL and not out[-1].endswith(":"):
                word = word.lower()
        elif i and core == "A":
            word = word.replace("A", "a")
        out.append(word)
    return " ".join(out)
